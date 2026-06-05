"""Workflow Registry — central store for compiled StateGraphs.

Loads workflows from Python registration or YAML files in ``workflows/``.
Implements WORKFLOW_SPEC §5 (WorkflowRegistry).

Dependency: F13 engine (app/workflow/engine.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.core.errors import (
    ERROR_CODE_WORKFLOW_EDGE_INVALID,
    ERROR_CODE_WORKFLOW_NODE_NOT_FOUND,
    make_error,
)
from app.core.logging import get_logger
from app.workflow.engine import StateGraph

logger = get_logger("workflow.registry")

# Sentinel: default fallback workflow ID
_DEFAULT_WORKFLOW_ID = "default_qa"


class WorkflowRegistry:
    """Central store for compiled workflows (programmatic + YAML).

    Usage::

        registry = WorkflowRegistry()
        registry.register("my_flow", graph)
        registry.register_from_yaml("workflows/default.yaml")
        wf = registry.match("qa")   # returns matched graph or default_qa
    """

    def __init__(self) -> None:
        self._workflows: dict[str, StateGraph] = {}

    # -- write ---------------------------------------------------------------

    def register(self, name: str, graph: StateGraph) -> None:
        """Register a :class:`StateGraph` under *name*."""
        self._workflows[name] = graph
        logger.debug("workflow.registry.registered", name=name)

    def register_from_yaml(self, path: str | Path) -> None:
        """Load a YAML workflow file and register it.

        YAML format follows ``workflows/default.yaml`` schema.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise make_error(
                ERROR_CODE_WORKFLOW_NODE_NOT_FOUND,
                f"Workflow YAML not found: {path}",
            )

        with open(file_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, dict):
            raise make_error(
                ERROR_CODE_WORKFLOW_EDGE_INVALID,
                f"Invalid workflow YAML (not a mapping): {path}",
            )

        wf_id: str = data.get("id", file_path.stem)
        description: str = data.get("description", "")
        match_cfg = data.get("match", {})
        intents: list[str] = match_cfg.get("intents", []) if isinstance(match_cfg, dict) else []

        # Build a StateGraph placeholder from YAML steps
        graph = StateGraph(
            name=wf_id,
            description=description,
        )
        graph.match_intents = intents

        steps = data.get("steps", [])
        if steps:
            for i, step in enumerate(steps):
                step_id = step.get("id", f"step_{i}")
                # Store step metadata in graph as node placeholder
                graph.add_node(step_id, _make_yaml_node_fn(step))
                # Chain steps linearly by default (when conditions handled later)
                if i > 0:
                    prev_id = steps[i - 1].get("id", f"step_{i - 1}")
                    graph.add_edge(prev_id, step_id)

        self._workflows[wf_id] = graph
        logger.debug(
            "workflow.registry.yaml_loaded",
            name=wf_id,
            intents=intents,
            steps=len(steps),
        )

    # -- read ----------------------------------------------------------------

    def get(self, name: str) -> StateGraph:
        """Retrieve a registered workflow by name.

        Raises WORKFLOW_NODE_NOT_FOUND if *name* is not registered.
        """
        try:
            return self._workflows[name]
        except KeyError as exc:
            raise make_error(
                ERROR_CODE_WORKFLOW_NODE_NOT_FOUND,
                f"Workflow '{name}' not registered",
            ) from exc

    def get_or_none(self, name: str) -> StateGraph | None:
        """Retrieve by name; return ``None`` if not found."""
        return self._workflows.get(name)

    def match(self, intent: str) -> StateGraph:
        """Match an intent string to a workflow by ``match.intents``.

        Falls back to ``default_qa`` if no match is found.
        If ``default_qa`` is also not registered, raises WORKFLOW_NODE_NOT_FOUND.
        """
        for graph in self._workflows.values():
            if intent in graph.match_intents:
                return graph

        # Fallback
        if _DEFAULT_WORKFLOW_ID in self._workflows:
            return self._workflows[_DEFAULT_WORKFLOW_ID]

        raise make_error(
            ERROR_CODE_WORKFLOW_NODE_NOT_FOUND,
            f"No workflow matched intent '{intent}' and no default_qa registered",
        )

    def list_workflows(self) -> list[str]:
        """Return names of all registered workflows."""
        return list(self._workflows.keys())

    def has(self, name: str) -> bool:
        return name in self._workflows

    def clear(self) -> None:
        """Remove all registered workflows."""
        self._workflows.clear()


# ---------------------------------------------------------------------------
# YAML node factory
# ---------------------------------------------------------------------------


def _make_yaml_node_fn(step: dict[str, Any]) -> Any:
    """Create a placeholder node function for a YAML-defined step.

    The placeholder returns the step metadata as state output,
    allowing downstream orchestration (F14+) to interpret it.
    """

    async def _yaml_node(state: dict[str, Any]) -> dict[str, Any]:
        return {
            f"_step_{step.get('id', 'unknown')}": {
                "agent": step.get("agent", ""),
                "skills": step.get("skills", []),
                "tools": step.get("tools", []),
                "when": step.get("when"),
            }
        }

    _yaml_node.__name__ = f"yaml_step_{step.get('id', 'unknown')}"
    return _yaml_node


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: WorkflowRegistry | None = None


def get_workflow_registry() -> WorkflowRegistry:
    """Get or create the global WorkflowRegistry singleton."""
    global _instance
    if _instance is None:
        _instance = WorkflowRegistry()
    return _instance


def reset_workflow_registry() -> None:
    """Reset the singleton (for tests only)."""
    global _instance
    if _instance is not None:
        _instance.clear()
    _instance = None
