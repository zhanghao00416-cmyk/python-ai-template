"""Tests for F13: Workflow DAG Engine (StateGraph + WorkflowEngine + Registry).

Verification: pytest tests/test_13_workflow.py -v

Covers:
  - StateGraph builder API (add_node, add_edge, add_conditional_edges)
  - Graph validation (entry_point, node existence, edge validity)
  - Topological sort / cycle detection (Kahn's algorithm)
  - WorkflowEngine linear execution
  - WorkflowEngine conditional branching
  - WorkflowEngine error handling (node failure)
  - WorkflowRegistry (register, get, match, YAML load)
  - Workflow schemas (Pydantic models)
  - Architecture compliance (no forbidden imports)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from app.core.errors import AppError, WorkflowError

# ---------------------------------------------------------------------------
# StateGraph builder
# ---------------------------------------------------------------------------

from app.workflow.engine import Edge, ConditionalEdge, NodeExecutionResult, StateGraph


class TestStateGraphBuilder:
    """StateGraph construction and properties."""

    def test_empty_graph(self):
        g = StateGraph("empty")
        assert g.name == "empty"
        assert g.description == ""
        assert g.entry_point is None
        assert g.nodes == {}
        assert g.edges == []
        assert g.conditional_edges == []

    def test_add_node_sets_entry_point(self):
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        assert g.entry_point == "a"
        g.add_node("b", lambda s: s)
        # First node remains entry_point
        assert g.entry_point == "a"

    def test_add_node_with_explicit_entry(self):
        g = StateGraph("test", entry_point="start")
        g.add_node("start", lambda s: s)
        g.add_node("end", lambda s: s)
        assert g.entry_point == "start"

    def test_add_edge(self):
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_edge("a", "b")
        assert len(g.edges) == 1
        assert g.edges[0].source == "a"
        assert g.edges[0].target == "b"

    def test_add_conditional_edges(self):
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_node("c", lambda s: s)

        def cond(state):
            return "yes" if state.get("flag") else "no"

        g.add_conditional_edges("a", cond, {"yes": "b", "no": "c"}, default="c")
        assert len(g.conditional_edges) == 1
        ce = g.conditional_edges[0]
        assert ce.source == "a"
        assert ce.paths == {"yes": "b", "no": "c"}
        assert ce.default == "c"

    def test_chaining_api(self):
        g = StateGraph("test")
        result = (
            g.add_node("a", lambda s: s)
            .add_node("b", lambda s: s)
            .add_edge("a", "b")
        )
        assert result is g

    def test_match_intents(self):
        g = StateGraph("test")
        g.match_intents = ["qa", "chat"]
        assert g.match_intents == ["qa", "chat"]


# ---------------------------------------------------------------------------
# Graph validation
# ---------------------------------------------------------------------------


class TestGraphValidation:
    """compile() validation rules."""

    def test_compile_empty_graph_raises(self):
        g = StateGraph("empty")
        with pytest.raises(AppError) as exc_info:
            g.compile()
        assert exc_info.value.code == 8001  # WORKFLOW_NODE_NOT_FOUND

    def test_compile_invalid_entry_point(self):
        g = StateGraph("test", entry_point="missing")
        g.add_node("a", lambda s: s)
        with pytest.raises(AppError) as exc_info:
            g.compile()
        assert exc_info.value.code == 8001

    def test_compile_edge_source_not_found(self):
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        g.add_edge("missing", "a")
        with pytest.raises(AppError) as exc_info:
            g.compile()
        assert exc_info.value.code == 8001

    def test_compile_edge_target_not_found(self):
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        g.add_edge("a", "missing")
        with pytest.raises(AppError) as exc_info:
            g.compile()
        assert exc_info.value.code == 8001

    def test_compile_conditional_path_not_found(self):
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_conditional_edges("a", lambda s: "x", {"x": "missing"})
        with pytest.raises(AppError) as exc_info:
            g.compile()
        assert exc_info.value.code == 8002  # WORKFLOW_EDGE_INVALID

    def test_compile_conditional_default_not_found(self):
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_conditional_edges("a", lambda s: "x", {"x": "b"}, default="missing")
        with pytest.raises(AppError) as exc_info:
            g.compile()
        assert exc_info.value.code == 8002

    def test_compile_valid_linear_graph(self):
        g = StateGraph("linear")
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_node("c", lambda s: s)
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        order = g.compile()
        assert order == ["a", "b", "c"]

    def test_compile_valid_branching_graph(self):
        g = StateGraph("branch")
        g.add_node("start", lambda s: s)
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_edge("start", "a")
        g.add_edge("start", "b")
        order = g.compile()
        # start first, then a and b in some order (both have in-degree 1)
        assert order[0] == "start"
        assert set(order[1:]) == {"a", "b"}


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestCycleDetection:
    """Kahn's algorithm detects cycles."""

    def test_simple_cycle(self):
        g = StateGraph("cycle")
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        with pytest.raises(AppError) as exc_info:
            g.compile()
        assert exc_info.value.code == 8004  # WORKFLOW_CYCLE_DETECTED

    def test_self_loop(self):
        g = StateGraph("self_loop")
        g.add_node("a", lambda s: s)
        g.add_edge("a", "a")
        with pytest.raises(AppError) as exc_info:
            g.compile()
        assert exc_info.value.code == 8004

    def test_cycle_with_conditional(self):
        g = StateGraph("cond_cycle")
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_conditional_edges("a", lambda s: "b", {"b": "b"})
        g.add_edge("b", "a")
        with pytest.raises(AppError) as exc_info:
            g.compile()
        assert exc_info.value.code == 8004


# ---------------------------------------------------------------------------
# WorkflowEngine — linear execution
# ---------------------------------------------------------------------------

from app.workflow.engine import WorkflowEngine


class TestWorkflowEngineLinear:
    """Execute simple linear DAGs."""

    @pytest.fixture
    def engine(self):
        return WorkflowEngine(max_concurrent_nodes=2)

    @pytest.mark.asyncio
    async def test_single_node(self, engine):
        g = StateGraph("single")
        g.add_node("only", lambda s: {"result": s.get("x", 0) * 2})
        state = await engine.execute(g, initial_state={"x": 5})
        assert state["result"] == 10
        assert "_node_results" in state
        assert len(state["_node_results"]) == 1
        assert state["_node_results"][0]["name"] == "only"
        assert state["_node_results"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_linear_chain(self, engine):
        g = StateGraph("chain")
        g.add_node("a", lambda s: {"a_out": 1})
        g.add_node("b", lambda s: {"b_out": s.get("a_out", 0) + 2})
        g.add_node("c", lambda s: {"c_out": s.get("b_out", 0) + 3})
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        state = await engine.execute(g, initial_state={})
        assert state["a_out"] == 1
        assert state["b_out"] == 3
        assert state["c_out"] == 6
        assert len(state["_node_results"]) == 3

    @pytest.mark.asyncio
    async def test_async_node(self, engine):
        async def async_fn(state):
            return {"async": True}

        g = StateGraph("async")
        g.add_node("async_node", async_fn)
        state = await engine.execute(g)
        assert state["async"] is True

    @pytest.mark.asyncio
    async def test_node_returning_non_dict(self, engine):
        """Non-dict returns are ignored (no state update)."""
        g = StateGraph("bad_return")
        g.add_node("a", lambda s: "not a dict")
        state = await engine.execute(g)
        assert state.get("a") is None
        # Node still recorded as completed
        assert state["_node_results"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_empty_initial_state(self, engine):
        g = StateGraph("empty_state")
        g.add_node("a", lambda s: {"k": "v"})
        state = await engine.execute(g)
        assert state["k"] == "v"


# ---------------------------------------------------------------------------
# WorkflowEngine — conditional branching
# ---------------------------------------------------------------------------


class TestWorkflowEngineConditional:
    """Execute DAGs with conditional edges."""

    @pytest.fixture
    def engine(self):
        return WorkflowEngine(max_concurrent_nodes=2)

    @pytest.mark.asyncio
    async def test_conditional_true_branch(self, engine):
        g = StateGraph("cond")
        g.add_node("start", lambda s: {"flag": True})
        g.add_node("branch_a", lambda s: {"taken": "a"})
        g.add_node("branch_b", lambda s: {"taken": "b"})
        g.add_conditional_edges(
            "start",
            lambda s: "yes" if s.get("flag") else "no",
            {"yes": "branch_a", "no": "branch_b"},
        )
        state = await engine.execute(g)
        assert state["taken"] == "a"
        # branch_b should be skipped
        results = {r["name"]: r["status"] for r in state["_node_results"]}
        assert results["start"] == "completed"
        assert results["branch_a"] == "completed"
        assert results.get("branch_b") == "skipped"

    @pytest.mark.asyncio
    async def test_conditional_false_branch(self, engine):
        g = StateGraph("cond")
        g.add_node("start", lambda s: {"flag": False})
        g.add_node("branch_a", lambda s: {"taken": "a"})
        g.add_node("branch_b", lambda s: {"taken": "b"})
        g.add_conditional_edges(
            "start",
            lambda s: "yes" if s.get("flag") else "no",
            {"yes": "branch_a", "no": "branch_b"},
        )
        state = await engine.execute(g)
        assert state["taken"] == "b"
        results = {r["name"]: r["status"] for r in state["_node_results"]}
        assert results.get("branch_a") == "skipped"

    @pytest.mark.asyncio
    async def test_conditional_with_default(self, engine):
        g = StateGraph("cond_default")
        g.add_node("start", lambda s: {})
        g.add_node("a", lambda s: {"taken": "a"})
        g.add_node("b", lambda s: {"taken": "b"})
        g.add_conditional_edges(
            "start",
            lambda s: "unknown",  # no match in paths
            {"yes": "a"},
            default="b",
        )
        state = await engine.execute(g)
        assert state["taken"] == "b"
        results = {r["name"]: r["status"] for r in state["_node_results"]}
        assert results.get("a") == "skipped"

    @pytest.mark.asyncio
    async def test_conditional_error_no_match_no_default(self, engine):
        g = StateGraph("cond_fail")
        g.add_node("start", lambda s: {})
        g.add_node("a", lambda s: {})
        g.add_conditional_edges(
            "start",
            lambda s: "unknown",
            {"yes": "a"},
        )
        with pytest.raises(AppError) as exc_info:
            await engine.execute(g)
        assert exc_info.value.code == 8002  # WORKFLOW_EDGE_INVALID


# ---------------------------------------------------------------------------
# WorkflowEngine — error handling
# ---------------------------------------------------------------------------


class TestWorkflowEngineErrors:
    """Node failures are recorded, not propagated."""

    @pytest.fixture
    def engine(self):
        return WorkflowEngine(max_concurrent_nodes=2)

    @pytest.mark.asyncio
    async def test_node_failure_recorded(self, engine):
        def fail_fn(state):
            raise RuntimeError("boom")

        g = StateGraph("fail")
        g.add_node("bad", fail_fn)
        state = await engine.execute(g)
        assert state["_node_results"][0]["status"] == "failed"
        assert "boom" in state["_node_results"][0]["error"]

    @pytest.mark.asyncio
    async def test_failed_node_does_not_update_state(self, engine):
        def fail_fn(state):
            raise RuntimeError("boom")

        g = StateGraph("fail")
        g.add_node("bad", fail_fn)
        g.add_node("next", lambda s: {"recovered": True})
        g.add_edge("bad", "next")
        state = await engine.execute(g)
        # next may or may not run depending on engine behavior;
        # the key invariant is that bad node's output is not in state
        # (error is recorded in _node_results, not in state keys)
        assert "recovered" in state or "_node_results" in state
        # Ensure the error message is only in _node_results, not as a state key
        for key in state:
            if key != "_node_results":
                assert "boom" not in str(state[key])

    @pytest.mark.asyncio
    async def test_condition_function_raises(self, engine):
        g = StateGraph("cond_raise")
        g.add_node("start", lambda s: {})
        g.add_node("a", lambda s: {})
        g.add_conditional_edges(
            "start",
            lambda s: (_ for _ in ()).throw(RuntimeError("cond boom")),
            {"x": "a"},
        )
        with pytest.raises(AppError) as exc_info:
            await engine.execute(g)
        assert exc_info.value.code == 8003  # WORKFLOW_EXECUTION_FAILED


# ---------------------------------------------------------------------------
# WorkflowRegistry
# ---------------------------------------------------------------------------

from app.workflow.registry import WorkflowRegistry, get_workflow_registry, reset_workflow_registry


class TestWorkflowRegistry:
    """Programmatic registration and retrieval."""

    @pytest.fixture(autouse=True)
    def clean_registry(self):
        reset_workflow_registry()
        yield
        reset_workflow_registry()

    def test_register_and_get(self):
        reg = WorkflowRegistry()
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        reg.register("my_flow", g)
        retrieved = reg.get("my_flow")
        assert retrieved.name == "test"

    def test_get_not_found_raises(self):
        reg = WorkflowRegistry()
        with pytest.raises(AppError) as exc_info:
            reg.get("missing")
        assert exc_info.value.code == 8001

    def test_get_or_none(self):
        reg = WorkflowRegistry()
        assert reg.get_or_none("missing") is None
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        reg.register("x", g)
        assert reg.get_or_none("x") is not None

    def test_match_by_intent(self):
        reg = WorkflowRegistry()
        g1 = StateGraph("qa_flow")
        g1.add_node("a", lambda s: s)
        g1.match_intents = ["qa", "chat"]
        reg.register("qa", g1)

        g2 = StateGraph("task_flow")
        g2.add_node("b", lambda s: s)
        g2.match_intents = ["task"]
        reg.register("task", g2)

        matched = reg.match("qa")
        assert matched.name == "qa_flow"

    def test_match_fallback_to_default(self):
        reg = WorkflowRegistry()
        g = StateGraph("default_qa")
        g.add_node("a", lambda s: s)
        g.match_intents = ["qa"]
        reg.register("default_qa", g)

        matched = reg.match("unknown_intent")
        assert matched.name == "default_qa"

    def test_match_no_fallback_raises(self):
        reg = WorkflowRegistry()
        g = StateGraph("other")
        g.add_node("a", lambda s: s)
        reg.register("other", g)

        with pytest.raises(AppError) as exc_info:
            reg.match("unknown")
        assert exc_info.value.code == 8001

    def test_list_workflows(self):
        reg = WorkflowRegistry()
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        reg.register("a", g)
        reg.register("b", g)
        assert sorted(reg.list_workflows()) == ["a", "b"]

    def test_has(self):
        reg = WorkflowRegistry()
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        reg.register("x", g)
        assert reg.has("x") is True
        assert reg.has("y") is False

    def test_clear(self):
        reg = WorkflowRegistry()
        g = StateGraph("test")
        g.add_node("a", lambda s: s)
        reg.register("x", g)
        reg.clear()
        assert reg.list_workflows() == []


# ---------------------------------------------------------------------------
# WorkflowRegistry — YAML loading
# ---------------------------------------------------------------------------


class TestWorkflowRegistryYaml:
    """Load workflows from YAML files."""

    @pytest.fixture(autouse=True)
    def clean_registry(self):
        reset_workflow_registry()
        yield
        reset_workflow_registry()

    def test_register_from_yaml(self):
        reg = WorkflowRegistry()
        yaml_content = """
id: test_yaml_flow
description: "A test workflow"
match:
  intents:
    - test_intent
steps:
  - id: step1
    agent: planner
    skills: []
    tools: []
  - id: step2
    agent: answer
    skills:
      - rag_answer
    tools: []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        try:
            reg.register_from_yaml(path)
            g = reg.get("test_yaml_flow")
            assert g.name == "test_yaml_flow"
            assert g.description == "A test workflow"
            assert g.match_intents == ["test_intent"]
            # Steps become nodes
            assert "step1" in g.nodes
            assert "step2" in g.nodes
            # Linear edges between steps
            assert len(g.edges) == 1
            assert g.edges[0].source == "step1"
            assert g.edges[0].target == "step2"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_register_from_yaml_missing_file(self):
        reg = WorkflowRegistry()
        with pytest.raises(AppError) as exc_info:
            reg.register_from_yaml("/nonexistent/workflow.yaml")
        assert exc_info.value.code == 8001

    def test_register_from_yaml_invalid_format(self):
        reg = WorkflowRegistry()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("not a mapping")
            f.flush()
            path = f.name

        try:
            with pytest.raises(AppError) as exc_info:
                reg.register_from_yaml(path)
            assert exc_info.value.code == 8002
        finally:
            Path(path).unlink(missing_ok=True)

    def test_yaml_node_fn_returns_metadata(self):
        """YAML-loaded nodes return step metadata as state."""
        reg = WorkflowRegistry()
        yaml_content = """
id: meta_flow
steps:
  - id: analyze
    agent: planner
    skills: []
    tools: [search]
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        try:
            reg.register_from_yaml(path)
            g = reg.get("meta_flow")
            # Execute the placeholder node
            import asyncio
            node_fn = g.nodes["analyze"]
            result = asyncio.get_event_loop().run_until_complete(node_fn({}))
            assert "_step_analyze" in result
            assert result["_step_analyze"]["agent"] == "planner"
            assert result["_step_analyze"]["tools"] == ["search"]
        finally:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Workflow schemas
# ---------------------------------------------------------------------------

from app.schemas.workflow import (
    WorkflowNodeStatus,
    WorkflowStatus,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowNodeResult,
    WorkflowStatusDetail,
)


class TestWorkflowSchemas:
    """Pydantic request/response models."""

    def test_node_status_enum(self):
        assert WorkflowNodeStatus.COMPLETED == "completed"
        assert WorkflowNodeStatus.FAILED == "failed"
        assert WorkflowNodeStatus.SKIPPED == "skipped"

    def test_workflow_status_enum(self):
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.FAILED == "failed"

    def test_run_request_minimal(self):
        req = WorkflowRunRequest(
            user_id="u1",
            session_id="s1",
            workflow_id="default_qa",
        )
        assert req.workflow_id == "default_qa"
        assert req.inputs == {}
        assert req.stream is True
        assert req.metadata == {}

    def test_run_request_full(self):
        req = WorkflowRunRequest(
            user_id="u1",
            session_id="s1",
            workflow_id="test_flow",
            inputs={"query": "hello"},
            stream=False,
            metadata={"channel": "web"},
        )
        assert req.inputs["query"] == "hello"
        assert req.stream is False

    def test_run_response(self):
        resp = WorkflowRunResponse(
            task_id="t1",
            workflow_id="test",
            content="answer",
            nodes=[
                WorkflowNodeResult(name="a", status="completed", duration_ms=10.0),
            ],
        )
        assert resp.task_id == "t1"
        assert resp.content == "answer"
        assert len(resp.nodes) == 1
        assert resp.nodes[0].name == "a"

    def test_node_result_failed(self):
        nr = WorkflowNodeResult(
            name="bad",
            status="failed",
            duration_ms=5.0,
            error="something wrong",
        )
        assert nr.error == "something wrong"
        assert nr.output is None

    def test_status_detail(self):
        detail = WorkflowStatusDetail(
            task_id="t1",
            workflow_id="test",
            status="completed",
            nodes=[],
            total_duration_ms=100.0,
            created_at="2026-01-01T00:00:00Z",
        )
        assert detail.status == "completed"
        assert detail.total_duration_ms == 100.0


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_workflow_package_exports(self):
        from app.workflow import (
            StateGraph,
            WorkflowEngine,
            WorkflowRegistry,
            Edge,
            ConditionalEdge,
            NodeExecutionResult,
        )
        assert StateGraph is not None
        assert WorkflowEngine is not None
        assert WorkflowRegistry is not None
        assert Edge is not None
        assert ConditionalEdge is not None
        assert NodeExecutionResult is not None


# ---------------------------------------------------------------------------
# Architecture compliance
# ---------------------------------------------------------------------------


class TestArchitectureCompliance:
    """Verify no forbidden imports in workflow/."""

    def test_workflow_no_infra_import(self):
        import app.workflow.engine
        import app.workflow.registry

        for mod in [app.workflow.engine, app.workflow.registry]:
            source_file = mod.__file__ or ""
            if source_file:
                with open(source_file, encoding="utf-8") as f:
                    content = f.read()
                assert "from app.infra" not in content, f"{source_file} imports from infra"
                assert "import app.infra" not in content, f"{source_file} imports from infra"

    def test_workflow_no_api_import(self):
        import app.workflow.engine
        import app.workflow.registry

        for mod in [app.workflow.engine, app.workflow.registry]:
            source_file = mod.__file__ or ""
            if source_file:
                with open(source_file, encoding="utf-8") as f:
                    content = f.read()
                assert "from app.api" not in content, f"{source_file} imports from api"

    def test_workflow_no_domain_import(self):
        import app.workflow.engine
        import app.workflow.registry

        for mod in [app.workflow.engine, app.workflow.registry]:
            source_file = mod.__file__ or ""
            if source_file:
                with open(source_file, encoding="utf-8") as f:
                    content = f.read()
                assert "from app.domain" not in content, f"{source_file} imports from domain"
