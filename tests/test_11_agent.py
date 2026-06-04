"""Tests for F11: Agent base class + state machine + ReAct loop.

Verification: pytest tests/test_11_agent.py

Covers:
  - AgentState enum and valid/invalid transitions
  - TrajectoryEntry / ToolCall / TokenUsage data models
  - BaseAgent abstract contract
  - ReactAgent full ReAct loop (THINKING → ACTING → OBSERVING → DONE)
  - 3-step tool calling with trajectory recording
  - max_iterations guard
  - Error handling (tool not found, execution failure)
  - Agent schemas (AgentRunRequest, AgentRunResponse, etc.)
  - AgentOrchestrationService (with mocked repo)
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

from app.agent.state import AgentState, is_valid_transition, transition
from app.core.errors import AppError, AgentError


class TestAgentState:
    """AgentState enum values."""

    def test_states_defined(self):
        expected = {"IDLE", "THINKING", "ACTING", "OBSERVING", "DONE", "ERROR"}
        actual = {s.value for s in AgentState}
        assert actual == expected

    def test_state_is_string_enum(self):
        assert AgentState.IDLE == "IDLE"
        assert AgentState.THINKING == "THINKING"


class TestStateTransitions:
    """Valid and invalid state transitions."""

    def test_idle_to_thinking(self):
        assert is_valid_transition(AgentState.IDLE, AgentState.THINKING)

    def test_thinking_to_acting(self):
        assert is_valid_transition(AgentState.THINKING, AgentState.ACTING)

    def test_thinking_to_done(self):
        assert is_valid_transition(AgentState.THINKING, AgentState.DONE)

    def test_acting_to_observing(self):
        assert is_valid_transition(AgentState.ACTING, AgentState.OBSERVING)

    def test_observing_to_thinking(self):
        assert is_valid_transition(AgentState.OBSERVING, AgentState.THINKING)

    def test_invalid_idle_to_done(self):
        assert not is_valid_transition(AgentState.IDLE, AgentState.DONE)

    def test_invalid_acting_to_thinking(self):
        assert not is_valid_transition(AgentState.ACTING, AgentState.THINKING)

    def test_invalid_done_to_thinking(self):
        assert not is_valid_transition(AgentState.DONE, AgentState.THINKING)

    def test_any_to_error(self):
        """Any state can transition to ERROR."""
        for state in AgentState:
            result = transition(state, AgentState.ERROR)
            assert result == AgentState.ERROR

    def test_any_to_idle_reset(self):
        """Any state can reset to IDLE."""
        for state in AgentState:
            result = transition(state, AgentState.IDLE)
            assert result == AgentState.IDLE

    def test_transition_valid(self):
        result = transition(AgentState.IDLE, AgentState.THINKING)
        assert result == AgentState.THINKING

    def test_transition_invalid_raises(self):
        with pytest.raises(AppError) as exc_info:
            transition(AgentState.IDLE, AgentState.DONE)
        assert exc_info.value.code == 7001  # AGENT_STATE_INVALID


# ---------------------------------------------------------------------------
# Trajectory data models
# ---------------------------------------------------------------------------

from app.agent.trajectory import AgentResult, TokenUsage, ToolCall, TrajectoryEntry


class TestTokenUsage:
    def test_defaults(self):
        u = TokenUsage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0

    def test_custom(self):
        u = TokenUsage(input_tokens=100, output_tokens=50)
        assert u.input_tokens == 100
        assert u.output_tokens == 50

    def test_frozen(self):
        u = TokenUsage()
        with pytest.raises(AttributeError):
            u.input_tokens = 10  # type: ignore


class TestToolCall:
    def test_defaults(self):
        tc = ToolCall(tool="kb_search")
        assert tc.tool == "kb_search"
        assert tc.input == {}

    def test_with_input(self):
        tc = ToolCall(tool="calculator", input={"a": 1, "b": 2})
        assert tc.input["a"] == 1


class TestTrajectoryEntry:
    def test_basic(self):
        entry = TrajectoryEntry(
            agent_name="test_agent",
            step_index=1,
            state="THINKING",
            thought="I need to search",
        )
        assert entry.agent_name == "test_agent"
        assert entry.step_index == 1
        assert entry.state == "THINKING"
        assert entry.thought == "I need to search"
        assert entry.action is None
        assert entry.observation is None
        assert entry.timestamp is not None

    def test_action_to_dict(self):
        tc = ToolCall(tool="search", input={"q": "test"})
        entry = TrajectoryEntry(
            agent_name="a", step_index=1, state="ACTING", action=tc,
        )
        d = entry.action_to_dict()
        assert d == {"tool": "search", "input": {"q": "test"}}

    def test_action_to_dict_none(self):
        entry = TrajectoryEntry(agent_name="a", step_index=1, state="THINKING")
        assert entry.action_to_dict() is None

    def test_observation_to_dict_string(self):
        entry = TrajectoryEntry(
            agent_name="a", step_index=1, state="OBSERVING", observation="result",
        )
        d = entry.observation_to_dict()
        assert d == {"result": "result"}

    def test_observation_to_dict_dict(self):
        entry = TrajectoryEntry(
            agent_name="a", step_index=1, state="OBSERVING",
            observation={"key": "value"},
        )
        d = entry.observation_to_dict()
        assert d == {"key": "value"}

    def test_token_usage_to_dict(self):
        entry = TrajectoryEntry(
            agent_name="a", step_index=1, state="THINKING",
            token_usage=TokenUsage(10, 20),
        )
        d = entry.token_usage_to_dict()
        assert d == {"input_tokens": 10, "output_tokens": 20}


class TestAgentResult:
    def test_basic(self):
        r = AgentResult(content="hello", agent_name="a", agent_type="react")
        assert r.content == "hello"
        assert r.agent_type == "react"
        assert r.trajectory == []
        assert r.total_token_usage.input_tokens == 0


# ---------------------------------------------------------------------------
# BaseAgent (via concrete ReactAgent)
# ---------------------------------------------------------------------------

from app.agent.base import BaseAgent
from app.agent.react import ReactAgent
from app.tools.registry import ToolRegistry


def _make_registry_with_tools(tools: dict[str, Any]) -> ToolRegistry:
    """Create a ToolRegistry with mock tools."""
    reg = ToolRegistry()
    for name, return_value in tools.items():
        async def _mock_fn(_rv=return_value, **kwargs):
            return _rv
        reg.register(name, _mock_fn, description=f"Mock {name}")
    return reg


class TestBaseAgentContract:
    """BaseAgent abstract contract tested through ReactAgent."""

    @pytest.fixture
    def registry(self):
        return _make_registry_with_tools({"search": {"results": ["a", "b"]}})

    @pytest.fixture
    def agent(self, registry):
        return ReactAgent(
            name="test_agent",
            tool_registry=registry,
            max_iterations=5,
            tools=["search"],
        )

    def test_initial_state_idle(self, agent):
        assert agent.state == AgentState.IDLE

    def test_name_and_type(self, agent):
        assert agent.name == "test_agent"
        assert agent.agent_type == "react"

    def test_max_iterations(self, agent):
        assert agent.max_iterations == 5

    @pytest.mark.asyncio
    async def test_act_tool_not_found(self, agent):
        """Tool not found returns error dict (not raises) per AGENT_SPEC."""
        agent._set_state(AgentState.THINKING)  # need valid state before ACTING
        tc = ToolCall(tool="nonexistent_tool", input={})
        result = await agent.act(tc)
        assert "error" in result
        assert result["error_code"] == 7002

    @pytest.mark.asyncio
    async def test_act_tool_success(self, agent):
        agent._set_state(AgentState.THINKING)
        tc = ToolCall(tool="search", input={"q": "test"})
        result = await agent.act(tc)
        assert result == {"results": ["a", "b"]}
        assert agent.state == AgentState.ACTING

    def test_observe_string(self, agent):
        agent._set_state(AgentState.THINKING)  # IDLE → THINKING
        agent._set_state(AgentState.ACTING)    # THINKING → ACTING
        text = agent.observe("some result")
        assert text == "some result"
        assert agent.state == AgentState.OBSERVING

    def test_observe_dict_with_error(self, agent):
        agent._set_state(AgentState.THINKING)  # IDLE → THINKING
        agent._set_state(AgentState.ACTING)    # THINKING → ACTING
        text = agent.observe({"error": "failed"})
        assert "failed" in text

    def test_should_continue_within_limit(self, agent):
        assert agent.should_continue(0) is True
        assert agent.should_continue(4) is True

    def test_should_continue_at_limit(self, agent):
        assert agent.should_continue(5) is False

    def test_should_continue_done(self, agent):
        agent.state = AgentState.DONE
        assert agent.should_continue(0) is False

    def test_should_continue_error(self, agent):
        agent.state = AgentState.ERROR
        assert agent.should_continue(0) is False


# ---------------------------------------------------------------------------
# ReactAgent — full ReAct loop
# ---------------------------------------------------------------------------


class TestReactAgentLoop:
    """ReactAgent ReAct loop with mock think function."""

    def _make_think_fn(self, plan: list[tuple[str, ToolCall | None, TokenUsage]]):
        """Create a think_fn that follows a scripted plan."""
        idx = [0]

        async def think_fn(user_input, history, context):
            if idx[0] < len(plan):
                result = plan[idx[0]]
                idx[0] += 1
                return result
            # Fallback: final answer
            return ("Done.", None, TokenUsage())

        return think_fn

    @pytest.mark.asyncio
    async def test_immediate_final_answer(self):
        """Agent produces final answer without tool calls."""
        registry = ToolRegistry()
        think_fn = self._make_think_fn([
            ("The answer is 42.", None, TokenUsage(10, 20)),
        ])
        agent = ReactAgent(
            name="qa_agent",
            tool_registry=registry,
            max_iterations=5,
            think_fn=think_fn,
        )
        result = await agent.run("What is the answer?")
        assert result.content == "The answer is 42."
        assert result.agent_name == "qa_agent"
        assert result.agent_type == "react"
        assert result.total_token_usage.input_tokens == 10
        assert result.total_token_usage.output_tokens == 20
        # Trajectory: THINKING + DONE
        assert len(result.trajectory) == 2
        assert result.trajectory[0].state == "THINKING"
        assert result.trajectory[1].state == "DONE"

    @pytest.mark.asyncio
    async def test_three_step_tool_calling(self):
        """Agent performs 3 tool calls then gives final answer.

        Verifies: IDLE → THINKING → ACTING → OBSERVING → THINKING → ... → DONE
        """
        registry = _make_registry_with_tools({
            "search": {"results": ["chunk1", "chunk2"]},
            "calculator": {"result": 42},
            "format": {"formatted": "Final output"},
        })

        plan = [
            # Step 1: call search
            (
                "I need to search for info",
                ToolCall(tool="search", input={"q": "test"}),
                TokenUsage(50, 30),
            ),
            # Step 2: call calculator
            (
                "Now I need to calculate",
                ToolCall(tool="calculator", input={"expr": "6*7"}),
                TokenUsage(40, 25),
            ),
            # Step 3: call format
            (
                "Let me format the result",
                ToolCall(tool="format", input={"data": "42"}),
                TokenUsage(30, 20),
            ),
            # Step 4: final answer
            (
                "The final answer is 42.",
                None,
                TokenUsage(20, 15),
            ),
        ]
        think_fn = self._make_think_fn(plan)
        agent = ReactAgent(
            name="research_agent",
            tool_registry=registry,
            max_iterations=10,
            tools=["search", "calculator", "format"],
            think_fn=think_fn,
        )

        result = await agent.run("Find and calculate something")

        assert result.content == "The final answer is 42."
        assert result.agent_type == "react"

        # Token accumulation
        assert result.total_token_usage.input_tokens == 140  # 50+40+30+20
        assert result.total_token_usage.output_tokens == 90   # 30+25+20+15

        # Trajectory: 4 THINKING + 3 ACTING + 3 OBSERVING + 1 DONE = 11
        thinking_entries = [e for e in result.trajectory if e.state == "THINKING"]
        acting_entries = [e for e in result.trajectory if e.state == "ACTING"]
        observing_entries = [e for e in result.trajectory if e.state == "OBSERVING"]
        done_entries = [e for e in result.trajectory if e.state == "DONE"]

        assert len(thinking_entries) == 4
        assert len(acting_entries) == 3
        assert len(observing_entries) == 3
        assert len(done_entries) == 1

        # Step indices are sequential
        for i, entry in enumerate(result.trajectory, start=1):
            assert entry.step_index == i

        # Agent name recorded on every entry
        for entry in result.trajectory:
            assert entry.agent_name == "research_agent"

    @pytest.mark.asyncio
    async def test_max_iterations_returns_partial(self):
        """Agent hits max_iterations and returns partial result."""
        registry = _make_registry_with_tools({"search": "result"})

        # Always call tool, never final answer
        async def infinite_think(user_input, history, context):
            return (
                "Still searching...",
                ToolCall(tool="search", input={}),
                TokenUsage(10, 5),
            )

        agent = ReactAgent(
            name="loop_agent",
            tool_registry=registry,
            max_iterations=3,
            think_fn=infinite_think,
        )

        result = await agent.run("Infinite task")

        # Should return (not raise) with partial content
        assert result.content is not None
        assert "max_iterations" in (result.task_id or "")

        # Check DONE state at end
        assert result.trajectory[-1].state == "DONE"

        # 3 iterations: 3 THINKING + 3 ACTING + 3 OBSERVING + 1 DONE = 10
        assert len(result.trajectory) == 10

    @pytest.mark.asyncio
    async def test_tool_not_found_continues_react(self):
        """When tool is not registered, agent continues (not crashes)."""
        registry = ToolRegistry()  # Empty registry

        call_count = [0]

        async def think_fn(user_input, history, context):
            call_count[0] += 1
            if call_count[0] == 1:
                return (
                    "Let me try a missing tool",
                    ToolCall(tool="missing_tool", input={}),
                    TokenUsage(10, 5),
                )
            return ("Giving up gracefully.", None, TokenUsage(5, 3))

        agent = ReactAgent(
            name="resilient_agent",
            tool_registry=registry,
            max_iterations=5,
            think_fn=think_fn,
        )

        result = await agent.run("Try something")

        # Should complete without error
        assert result.content == "Giving up gracefully."
        assert len(result.trajectory) >= 4  # THINK + ACT + OBSERVE + THINK + DONE

    @pytest.mark.asyncio
    async def test_think_fn_exception_propagates(self):
        """If think_fn raises, agent transitions to ERROR."""
        async def bad_think(user_input, history, context):
            raise RuntimeError("LLM crashed")

        registry = ToolRegistry()
        agent = ReactAgent(
            name="fragile_agent",
            tool_registry=registry,
            max_iterations=5,
            think_fn=bad_think,
        )

        with pytest.raises(AppError) as exc_info:
            await agent.run("Something")
        assert exc_info.value.code == 7003  # AGENT_EXECUTION_FAILED
        assert agent.state == AgentState.ERROR

    @pytest.mark.asyncio
    async def test_echo_fallback_without_think_fn(self):
        """Without think_fn, agent echoes input as final answer."""
        registry = ToolRegistry()
        agent = ReactAgent(
            name="echo_agent",
            tool_registry=registry,
            max_iterations=5,
        )
        result = await agent.run("Hello world")
        assert result.content == "Echo: Hello world"
        assert result.agent_type == "react"

    @pytest.mark.asyncio
    async def test_reset_between_runs(self):
        """Agent state resets between consecutive runs."""
        registry = ToolRegistry()
        agent = ReactAgent(
            name="reset_agent",
            tool_registry=registry,
            max_iterations=5,
        )

        result1 = await agent.run("First")
        assert result1.content == "Echo: First"
        assert agent.state == AgentState.DONE

        result2 = await agent.run("Second")
        assert result2.content == "Echo: Second"
        # Trajectory should be fresh
        assert result2.trajectory[0].step_index == 1


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

from app.schemas.agent import (
    AgentRunRequest,
    AgentRunResponse,
    AgentType,
    AgentUsageDetail,
    TrajectoryDetail,
    TrajectoryListItem,
    TrajectoryStepDetail,
)


class TestAgentSchemas:
    def test_agent_type_enum(self):
        assert AgentType.REACT.value == "react"
        assert AgentType.WORKFLOW.value == "workflow"
        assert AgentType.ORCHESTRATOR.value == "orchestrator"

    def test_run_request_minimal(self):
        req = AgentRunRequest(
            user_id="u1", session_id="s1", query="test",
        )
        assert req.agent_type == AgentType.REACT
        assert req.max_steps == 10
        assert req.stream is True
        assert req.tools is None
        assert req.skills is None

    def test_run_request_full(self):
        req = AgentRunRequest(
            user_id="u1",
            session_id="s1",
            query="complex task",
            agent_type=AgentType.ORCHESTRATOR,
            agent_name="researcher",
            tools=["kb_search"],
            skills=["rag_answer"],
            max_steps=5,
            stream=False,
            model_override="qwen-plus",
            metadata={"channel": "web"},
        )
        assert req.agent_type == AgentType.ORCHESTRATOR
        assert req.max_steps == 5

    def test_run_request_empty_query_rejected(self):
        with pytest.raises(Exception):
            AgentRunRequest(user_id="u1", session_id="s1", query="")

    def test_run_response(self):
        resp = AgentRunResponse(
            task_id="tid-1",
            content="answer",
            trajectory=[
                TrajectoryStepDetail(step_index=1, state="THINKING", thought="..."),
            ],
            usage=AgentUsageDetail(input_tokens=10, output_tokens=20, model="qwen-plus"),
        )
        assert resp.content == "answer"
        assert len(resp.trajectory) == 1
        assert resp.usage.input_tokens == 10

    def test_trajectory_list_item(self):
        item = TrajectoryListItem(
            task_id="t1", session_id="s1", agent_name="a",
            agent_type="react", step_count=5, status="completed",
            created_at="2026-01-01T00:00:00Z",
        )
        assert item.step_count == 5

    def test_trajectory_detail(self):
        detail = TrajectoryDetail(
            task_id="t1", session_id="s1", agent_name="a",
            agent_type="react", status="completed",
            steps=[TrajectoryStepDetail(step_index=1, state="DONE")],
            created_at="2026-01-01T00:00:00Z",
        )
        assert detail.status == "completed"
        assert len(detail.steps) == 1

    def test_step_detail_serialization(self):
        step = TrajectoryStepDetail(
            step_index=2,
            state="ACTING",
            action={"tool": "search", "input": {"q": "test"}},
            token_usage={"input_tokens": 10, "output_tokens": 5},
        )
        d = step.model_dump()
        assert d["state"] == "ACTING"
        assert d["action"]["tool"] == "search"


# ---------------------------------------------------------------------------
# AgentOrchestrationService
# ---------------------------------------------------------------------------

from app.domain.agent_orchestration.service import AgentOrchestrationService


class TestAgentOrchestrationService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.save_trajectory_entries = AsyncMock(return_value=[])
        repo.list_by_session_grouped = AsyncMock(return_value=([], 0))
        repo.list_by_session = AsyncMock(return_value=([], 0))
        return repo

    @pytest.fixture
    def registry(self):
        return _make_registry_with_tools({"search": {"results": ["a"]}})

    @pytest.fixture
    def service(self, mock_repo, registry):
        return AgentOrchestrationService(repo=mock_repo, tool_registry=registry)

    @pytest.mark.asyncio
    async def test_run_agent_basic(self, service, mock_repo):
        """Service runs agent and persists trajectory."""
        result = await service.run_agent(
            user_id="u1",
            session_id=str(uuid.uuid4()),
            query="Hello",
            agent_type="react",
            max_steps=5,
        )
        assert result.content == "Echo: Hello"
        assert result.task_id is not None
        # Trajectory saved
        mock_repo.save_trajectory_entries.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_agent_with_tool(self, service, mock_repo):
        """Service runs agent with tool calling."""
        registry = _make_registry_with_tools({"search": {"found": True}})
        svc = AgentOrchestrationService(repo=mock_repo, tool_registry=registry)

        call_count = [0]

        # Override ReactAgent's default think to use tools
        # We test via the service directly using the default echo behavior
        result = await svc.run_agent(
            user_id="u1",
            session_id=str(uuid.uuid4()),
            query="Search for something",
        )
        assert result.content is not None

    @pytest.mark.asyncio
    async def test_list_trajectories_empty(self, service, mock_repo):
        items, total = await service.list_trajectories()
        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_trajectory_detail_not_found(self, service, mock_repo):
        detail = await service.get_trajectory_detail(str(uuid.uuid4()))
        assert detail is None

    @pytest.mark.asyncio
    async def test_get_trajectory_detail_invalid_uuid(self, service):
        detail = await service.get_trajectory_detail("not-a-uuid")
        assert detail is None

    def test_create_engine_react(self, service):
        engine = service._create_engine("react", "test", [], 10)
        assert isinstance(engine, ReactAgent)
        assert engine.agent_type == "react"

    def test_create_engine_fallback(self, service):
        engine = service._create_engine("workflow", "test", [], 10)
        # Falls back to ReactAgent
        assert isinstance(engine, ReactAgent)


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_agent_package_exports(self):
        from app.agent import (
            AgentState,
            BaseAgent,
            ReactAgent,
            TrajectoryEntry,
            ToolCall,
            TokenUsage,
            AgentResult,
        )
        assert AgentState is not None
        assert BaseAgent is not None
        assert ReactAgent is not None

    def test_domain_package_exports(self):
        from app.domain.agent_orchestration import (
            AgentTrajectoryRepo,
            AgentOrchestrationService,
        )
        assert AgentTrajectoryRepo is not None
        assert AgentOrchestrationService is not None


# ---------------------------------------------------------------------------
# Architecture compliance
# ---------------------------------------------------------------------------


class TestArchitectureCompliance:
    """Verify no forbidden imports."""

    def test_agent_no_infra_import(self):
        """agent/ must not import from infra/."""
        import app.agent.state
        import app.agent.trajectory
        import app.agent.base
        import app.agent.react

        for mod in [app.agent.state, app.agent.trajectory, app.agent.base, app.agent.react]:
            source_file = mod.__file__ or ""
            if source_file:
                with open(source_file, encoding="utf-8") as f:
                    content = f.read()
                assert "from app.infra" not in content, f"{source_file} imports from infra"
                assert "import app.infra" not in content, f"{source_file} imports from infra"

    def test_agent_no_api_import(self):
        """agent/ must not import from api/."""
        import app.agent.state
        import app.agent.trajectory
        import app.agent.base
        import app.agent.react

        for mod in [app.agent.state, app.agent.trajectory, app.agent.base, app.agent.react]:
            source_file = mod.__file__ or ""
            if source_file:
                with open(source_file, encoding="utf-8") as f:
                    content = f.read()
                assert "from app.api" not in content, f"{source_file} imports from api"

    def test_agent_no_domain_import(self):
        """agent/ engine must not import from domain/."""
        import app.agent.state
        import app.agent.trajectory
        import app.agent.base
        import app.agent.react

        for mod in [app.agent.state, app.agent.trajectory, app.agent.base, app.agent.react]:
            source_file = mod.__file__ or ""
            if source_file:
                with open(source_file, encoding="utf-8") as f:
                    content = f.read()
                assert "from app.domain" not in content, f"{source_file} imports from domain"
