"""Workflow Engine — StateGraph DAG executor with conditional edges.

Implements WORKFLOW_SPEC §3 (StateGraph) + §4 (DAG execution).
Independent of business logic; lives in app/workflow/.

Dependency: F13 (standalone engine; no domain/infra imports).
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.errors import (
    ERROR_CODE_WORKFLOW_CYCLE_DETECTED,
    ERROR_CODE_WORKFLOW_EDGE_INVALID,
    ERROR_CODE_WORKFLOW_EXECUTION_FAILED,
    ERROR_CODE_WORKFLOW_NODE_NOT_FOUND,
    make_error,
)
from app.core.logging import get_logger

logger = get_logger("workflow.engine")

NodeFunction = Callable[[dict[str, Any]], Any]
ConditionFunction = Callable[[dict[str, Any]], str]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Edge:
    """Unconditional edge: source → target."""

    source: str
    target: str


@dataclass(frozen=True, slots=True)
class ConditionalEdge:
    """Conditional edge: source → condition(state) → one of paths."""

    source: str
    condition: ConditionFunction
    paths: dict[str, str]  # route_key → target_node
    default: str | None = None


@dataclass(slots=True)
class NodeExecutionResult:
    """Result of a single node execution."""

    name: str
    status: str = "completed"  # completed | failed | skipped
    duration_ms: float = 0.0
    output: dict[str, Any] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# StateGraph
# ---------------------------------------------------------------------------


class StateGraph:
    """Directed Acyclic Graph where nodes are functions that transform state.

    Edges define execution order (with optional conditions).
    State is a ``dict[str, Any]`` passed between nodes.

    Parameters
    ----------
    name:
        Workflow identifier.
    entry_point:
        Name of the first node to execute.
    description:
        Human-readable description.
    """

    def __init__(
        self,
        name: str,
        *,
        entry_point: str | None = None,
        description: str = "",
    ) -> None:
        self.name = name
        self.description = description
        self.entry_point: str | None = entry_point

        self._nodes: dict[str, NodeFunction] = {}
        self._edges: list[Edge] = []
        self._conditional_edges: list[ConditionalEdge] = []
        self._match_intents: list[str] = []

    # -- builder API ---------------------------------------------------------

    def add_node(self, name: str, fn: NodeFunction) -> StateGraph:
        """Register a node function.  Returns *self* for chaining."""
        self._nodes[name] = fn
        if self.entry_point is None:
            self.entry_point = name
        return self

    def add_edge(self, source: str, target: str) -> StateGraph:
        """Add an unconditional edge."""
        self._edges.append(Edge(source=source, target=target))
        return self

    def add_conditional_edges(
        self,
        source: str,
        condition: ConditionFunction,
        paths: dict[str, str],
        *,
        default: str | None = None,
    ) -> StateGraph:
        """Add a conditional edge from *source*."""
        self._conditional_edges.append(
            ConditionalEdge(
                source=source,
                condition=condition,
                paths=paths,
                default=default,
            )
        )
        return self

    # -- read helpers --------------------------------------------------------

    @property
    def nodes(self) -> dict[str, NodeFunction]:
        return dict(self._nodes)

    @property
    def edges(self) -> list[Edge]:
        return list(self._edges)

    @property
    def conditional_edges(self) -> list[ConditionalEdge]:
        return list(self._conditional_edges)

    @property
    def match_intents(self) -> list[str]:
        return list(self._match_intents)

    @match_intents.setter
    def match_intents(self, intents: list[str]) -> None:
        self._match_intents = list(intents)

    # -- compile (validation) ------------------------------------------------

    def compile(self) -> list[str]:
        """Validate the graph and return topological execution order.

        Raises
        ------
        AppError (8004 WORKFLOW_CYCLE_DETECTED)
            If a cycle is detected.
        AppError (8001 WORKFLOW_NODE_NOT_FOUND)
            If entry_point or an edge references an unknown node.
        """
        _validate_graph(self)
        return _topological_sort(self)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_graph(graph: StateGraph) -> None:
    """Check structural invariants before execution."""
    if not graph._nodes:
        raise make_error(
            ERROR_CODE_WORKFLOW_NODE_NOT_FOUND,
            f"Workflow '{graph.name}' has no nodes",
        )
    if graph.entry_point and graph.entry_point not in graph._nodes:
        raise make_error(
            ERROR_CODE_WORKFLOW_NODE_NOT_FOUND,
            f"Entry point '{graph.entry_point}' not found in workflow '{graph.name}'",
        )

    all_nodes = set(graph._nodes)

    for edge in graph._edges:
        if edge.source not in all_nodes:
            raise make_error(
                ERROR_CODE_WORKFLOW_NODE_NOT_FOUND,
                f"Edge source '{edge.source}' not found in workflow '{graph.name}'",
            )
        if edge.target not in all_nodes:
            raise make_error(
                ERROR_CODE_WORKFLOW_NODE_NOT_FOUND,
                f"Edge target '{edge.target}' not found in workflow '{graph.name}'",
            )

    for cedge in graph._conditional_edges:
        if cedge.source not in all_nodes:
            raise make_error(
                ERROR_CODE_WORKFLOW_NODE_NOT_FOUND,
                f"Conditional edge source '{cedge.source}' not found",
            )
        for target in cedge.paths.values():
            if target not in all_nodes:
                raise make_error(
                    ERROR_CODE_WORKFLOW_EDGE_INVALID,
                    f"Conditional path target '{target}' not found",
                )
        if cedge.default and cedge.default not in all_nodes:
            raise make_error(
                ERROR_CODE_WORKFLOW_EDGE_INVALID,
                f"Conditional default '{cedge.default}' not found",
            )


def _topological_sort(graph: StateGraph) -> list[str]:
    """Kahn's algorithm for topological sort + cycle detection.

    Returns execution order (list of node names).
    Raises WORKFLOW_CYCLE_DETECTED on cycles.
    """
    all_nodes = set(graph._nodes)
    in_degree: dict[str, int] = {n: 0 for n in all_nodes}
    adjacency: dict[str, list[str]] = {n: [] for n in all_nodes}

    for edge in graph._edges:
        adjacency[edge.source].append(edge.target)
        in_degree[edge.target] += 1

    for cedge in graph._conditional_edges:
        for target in cedge.paths.values():
            adjacency[cedge.source].append(target)
            in_degree[target] += 1
        if cedge.default:
            adjacency[cedge.source].append(cedge.default)
            in_degree[cedge.default] += 1

    queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
    order: list[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbour in adjacency[node]:
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    if len(order) != len(all_nodes):
        raise make_error(
            ERROR_CODE_WORKFLOW_CYCLE_DETECTED,
            f"Cycle detected in workflow '{graph.name}'",
        )

    return order


# ---------------------------------------------------------------------------
# WorkflowEngine
# ---------------------------------------------------------------------------


class WorkflowEngine:
    """Executes a compiled :class:`StateGraph`.

    Parameters
    ----------
    max_concurrent_nodes:
        Maximum number of nodes to run concurrently (for fan-out).
    """

    def __init__(self, *, max_concurrent_nodes: int = 5) -> None:
        self._max_concurrent_nodes = max_concurrent_nodes

    async def execute(
        self,
        graph: StateGraph,
        initial_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute *graph* and return the final state.

        Parameters
        ----------
        graph:
            A :class:`StateGraph` (will be compiled/validated first).
        initial_state:
            Seed state dict; defaults to ``{}``.

        Returns
        -------
        dict
            Final state after all reachable nodes have executed.
            Includes ``_node_results`` key with per-node execution details.
        """
        topo_order = graph.compile()

        state: dict[str, Any] = dict(initial_state) if initial_state else {}
        node_results: list[NodeExecutionResult] = []
        visited: set[str] = set()      # nodes that have been executed
        resolved: set[str] = set()     # visited + skipped
        skipped: set[str] = set()      # nodes skipped due to conditional branch

        # Build adjacency + predecessor counts for execution
        all_nodes = set(graph._nodes)
        in_degree: dict[str, int] = {n: 0 for n in all_nodes}
        fixed_adj: dict[str, list[str]] = {n: [] for n in all_nodes}
        cond_map: dict[str, ConditionalEdge] = {}

        for edge in graph._edges:
            fixed_adj[edge.source].append(edge.target)
            in_degree[edge.target] += 1

        for cedge in graph._conditional_edges:
            cond_map[cedge.source] = cedge
            for target in cedge.paths.values():
                in_degree[target] += 1
            if cedge.default:
                in_degree[cedge.default] += 1

        # Track remaining in-degree for execution gating
        remaining_in: dict[str, int] = dict(in_degree)

        # BFS from entry_point
        ready: deque[str] = deque()
        if graph.entry_point and remaining_in.get(graph.entry_point, 0) == 0:
            ready.append(graph.entry_point)

        # Also enqueue any zero-in-degree nodes (isolated / start nodes)
        for n in topo_order:
            if n != graph.entry_point and remaining_in.get(n, 0) == 0:
                ready.append(n)

        while ready:
            node_name = ready.popleft()
            if node_name in visited or node_name in skipped:
                continue

            # Check predecessors resolved
            preds_resolved = self._check_predecessors(
                node_name, graph, resolved, fixed_adj, cond_map
            )
            if not preds_resolved:
                # Re-queue at end (wait for predecessors)
                ready.append(node_name)
                continue

            # Check if this node should be skipped (unselected conditional branch)
            # A node is skipped if ALL its conditional predecessors resolved
            # but routed elsewhere.
            is_skipped = self._is_skipped_branch(
                node_name, resolved, skipped, fixed_adj, cond_map
            )
            if is_skipped:
                skipped.add(node_name)
                resolved.add(node_name)
                node_results.append(
                    NodeExecutionResult(name=node_name, status="skipped")
                )
                # Decrement in-degree of its successors so fan-in works
                for succ in fixed_adj.get(node_name, []):
                    remaining_in[succ] = max(0, remaining_in.get(succ, 1) - 1)
                    if remaining_in[succ] == 0 and succ not in visited and succ not in skipped:
                        ready.append(succ)
                if node_name in cond_map:
                    cedge = cond_map[node_name]
                    for succ in cedge.paths.values():
                        remaining_in[succ] = max(0, remaining_in.get(succ, 1) - 1)
                        if remaining_in[succ] == 0 and succ not in visited and succ not in skipped:
                            ready.append(succ)
                    if cedge.default:
                        remaining_in[cedge.default] = max(0, remaining_in.get(cedge.default, 1) - 1)
                        if remaining_in[cedge.default] == 0 and cedge.default not in visited and cedge.default not in skipped:
                            ready.append(cedge.default)
                continue

            fn = graph._nodes[node_name]
            result = await self._execute_node(node_name, fn, state)
            node_results.append(result)
            visited.add(node_name)
            resolved.add(node_name)

            if result.status == "completed" and result.output:
                state.update(result.output)

            # Determine successors
            successors = self._route_successors(
                node_name, state, graph, fixed_adj, cond_map
            )
            for succ in successors:
                if succ not in visited and succ not in skipped:
                    remaining_in[succ] = max(0, remaining_in.get(succ, 1) - 1)
                    if remaining_in[succ] == 0:
                        ready.append(succ)

            # Mark unselected conditional branches as skipped
            if node_name in cond_map:
                cedge = cond_map[node_name]
                selected = set(successors)
                all_targets = set(cedge.paths.values())
                if cedge.default:
                    all_targets.add(cedge.default)
                for target in all_targets - selected:
                    if target not in skipped and target not in visited:
                        skipped.add(target)
                        resolved.add(target)
                        node_results.append(
                            NodeExecutionResult(name=target, status="skipped")
                        )
                        # Decrement their successors' in-degree
                        for succ in fixed_adj.get(target, []):
                            remaining_in[succ] = max(0, remaining_in.get(succ, 1) - 1)
                            if remaining_in[succ] == 0 and succ not in visited and succ not in skipped:
                                ready.append(succ)

        state["_node_results"] = [
            {
                "name": r.name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "output": r.output,
                "error": r.error,
            }
            for r in node_results
        ]
        return state

    # -- internal ------------------------------------------------------------

    async def _execute_node(
        self,
        name: str,
        fn: NodeFunction,
        state: dict[str, Any],
    ) -> NodeExecutionResult:
        """Execute a single node function with timing and error handling."""
        t0 = time.monotonic()
        try:
            if asyncio.iscoroutinefunction(fn):
                output = await fn(state)
            else:
                loop = asyncio.get_event_loop()
                output = await loop.run_in_executor(None, fn, state)

            duration = (time.monotonic() - t0) * 1000
            logger.debug(
                "workflow.node_completed",
                node=name,
                duration_ms=round(duration, 2),
            )
            return NodeExecutionResult(
                name=name,
                status="completed",
                duration_ms=round(duration, 2),
                output=output if isinstance(output, dict) else None,
            )
        except Exception as exc:
            duration = (time.monotonic() - t0) * 1000
            logger.error(
                "workflow.node_failed",
                node=name,
                error=str(exc),
                duration_ms=round(duration, 2),
            )
            return NodeExecutionResult(
                name=name,
                status="failed",
                duration_ms=round(duration, 2),
                error=str(exc),
            )

    def _route_successors(
        self,
        source: str,
        state: dict[str, Any],
        graph: StateGraph,
        fixed_adj: dict[str, list[str]],
        cond_map: dict[str, ConditionalEdge],
    ) -> list[str]:
        """Determine which successor nodes to activate from *source*."""
        result: list[str] = []

        # Unconditional edges
        result.extend(fixed_adj.get(source, []))

        # Conditional edge
        if source in cond_map:
            cedge = cond_map[source]
            try:
                route_key = cedge.condition(state)
            except Exception as exc:
                raise make_error(
                    ERROR_CODE_WORKFLOW_EXECUTION_FAILED,
                    f"Condition function for '{source}' raised: {exc}",
                ) from exc
            target = cedge.paths.get(route_key, cedge.default)
            if target is None:
                raise make_error(
                    ERROR_CODE_WORKFLOW_EDGE_INVALID,
                    f"Condition returned '{route_key}' with no matching path from '{source}'",
                )
            result.append(target)

        return result

    def _is_skipped_branch(
        self,
        node_name: str,
        resolved: set[str],
        skipped: set[str],
        fixed_adj: dict[str, list[str]],
        cond_map: dict[str, ConditionalEdge],
    ) -> bool:
        """Check if *node_name* is an unselected branch of a conditional edge.

        A node is a skipped branch if:
        - It is a target of a conditional edge from some predecessor
        - That predecessor has been resolved
        - The node itself is already marked as skipped
        """
        if node_name in skipped:
            return True

        # Check conditional predecessors: if a resolved predecessor has a
        # conditional edge that includes this node as a target, but the
        # predecessor has already executed and this node was marked skipped
        # at that time, then it's skipped.
        # Since we mark skipped immediately after routing, this check is
        # mainly for nodes that get enqueued before the skip marking happens.
        for src, cedge in cond_map.items():
            if src not in resolved:
                continue
            all_targets = set(cedge.paths.values())
            if cedge.default:
                all_targets.add(cedge.default)
            if node_name in all_targets and node_name in skipped:
                return True
        return False

    def _check_predecessors(
        self,
        node_name: str,
        graph: StateGraph,
        resolved: set[str],
        fixed_adj: dict[str, list[str]],
        cond_map: dict[str, ConditionalEdge],
    ) -> bool:
        """Check if all predecessors of *node_name* have been resolved."""
        # Collect all possible predecessors
        preds: set[str] = set()
        for src, targets in fixed_adj.items():
            if node_name in targets:
                preds.add(src)
        for src, cedge in cond_map.items():
            if node_name in cedge.paths.values() or node_name == cedge.default:
                preds.add(src)

        # Entry point / zero-in-degree nodes have no predecessors
        if not preds:
            return True

        return preds.issubset(resolved)
