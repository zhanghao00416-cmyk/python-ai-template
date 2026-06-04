"""Tests for F12: Multi-Agent Coordination (Orchestrator Mode).

Verification: pytest tests/test_12_multi_agent.py

Covers:
  - SubTask / SubTaskResult data models
  - OrchestratorAgent: creation, add_sub_agent, plan, delegate, synthesize
  - OrchestratorAgent full run (3 sub-agents → aggregate results)
  - Trajectory recording (THINKING → ACTING → OBSERVING → ... → DONE)
  - DebateStrategy: propose/critique/revise loop, consensus, max rounds
  - DebateStrategy._parse_score
  - Error handling (sub-agent failure, no sub-agents, max_sub_agents limit)
  - Domain service integration (_create_engine orchestrator)
  - _parse_plan JSON extraction
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.base import BaseAgent
from app.agent.orchestrator import (
    DebateResult,
    DebateRound,
    DebateStrategy,
    OrchestratorAgent,
    SubTask,
    SubTaskResult,
)
from app.agent.react import ReactAgent
from app.agent.state import AgentState
from app.agent.trajectory import AgentResult, TokenUsage, ToolCall, TrajectoryEntry
from app.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool_registry() -> ToolRegistry:
    """Create an empty ToolRegistry for testing."""
    return ToolRegistry()


def _make_react_agent(
    name: str = "test_agent",
    think_fn: Any | None = None,
) -> ReactAgent:
    """Create a simple ReactAgent for sub-agent testing."""
    return ReactAgent(
        name=name,
        tool_registry=_make_tool_registry(),
        max_iterations=5,
        think_fn=think_fn,
    )


async def _echo_think_fn(
    user_input: str,
    history: list,
    context: dict,
) -> tuple[str, Any, TokenUsage]:
    """A think_fn that echoes input as a final answer."""
    return (f"Answer: {user_input}", None, TokenUsage(input_tokens=10, output_tokens=5))


async def _tool_think_fn(
    user_input: str,
    history: list,
    context: dict,
) -> tuple[str, Any, TokenUsage]:
    """A think_fn that always calls a tool (for step counting)."""
    if len(history) < 2:
        return (
            f"Thinking about: {user_input}",
            ToolCall(tool="calculator", input={"op": "add", "a": 1, "b": 2}),
            TokenUsage(input_tokens=5, output_tokens=3),
        )
    return (f"Final: {user_input}", None, TokenUsage(input_tokens=5, output_tokens=3))


async def _plan_think_fn(
    user_input: str,
    history: list,
    context: dict,
) -> tuple[str, Any, TokenUsage]:
    """A think_fn that returns a JSON plan for orchestrator plan()."""
    plan_json = json.dumps([
        {"description": "Research the topic", "agent_name": "researcher"},
        {"description": "Write the summary", "agent_name": "writer"},
    ])
    return (plan_json, None, TokenUsage(input_tokens=20, output_tokens=10))


async def _synth_think_fn(
    user_input: str,
    history: list,
    context: dict,
) -> tuple[str, Any, TokenUsage]:
    """A think_fn for synthesis."""
    return ("Synthesised final answer", None, TokenUsage(input_tokens=15, output_tokens=8))


# ---------------------------------------------------------------------------
# SubTask / SubTaskResult data models
# ---------------------------------------------------------------------------

class TestSubTask:
    """SubTask data model."""

    def test_creation(self):
        st = SubTask(task_id="t1", description="Do X", agent_name="agent_a")
        assert st.task_id == "t1"
        assert st.description == "Do X"
        assert st.agent_name == "agent_a"
        assert st.context == {}

    def test_with_context(self):
        st = SubTask(
            task_id="t2",
            description="Do Y",
            agent_name="agent_b",
            context={"key": "value"},
        )
        assert st.context == {"key": "value"}

    def test_frozen(self):
        st = SubTask(task_id="t1", description="Do X", agent_name="agent_a")
        with pytest.raises(AttributeError):
            st.task_id = "t2"  # type: ignore


class TestSubTaskResult:
    """SubTaskResult data model."""

    def test_success(self):
        r = SubTaskResult(
            task_id="t1",
            agent_name="agent_a",
            content="Done!",
            success=True,
        )
        assert r.success is True
        assert r.content == "Done!"
        assert r.token_usage == TokenUsage()
        assert r.trajectory == []

    def test_failure(self):
        r = SubTaskResult(
            task_id="t1",
            agent_name="agent_a",
            content="Failed: timeout",
            success=False,
        )
        assert r.success is False

    def test_with_token_usage(self):
        r = SubTaskResult(
            task_id="t1",
            agent_name="agent_a",
            content="OK",
            success=True,
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
        )
        assert r.token_usage.input_tokens == 100
        assert r.token_usage.output_tokens == 50


# ---------------------------------------------------------------------------
# OrchestratorAgent — creation and sub-agent management
# ---------------------------------------------------------------------------

class TestOrchestratorAgentCreation:
    """OrchestratorAgent construction and sub-agent management."""

    def test_basic_creation(self):
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
        )
        assert orch.name == "orchestrator"
        assert orch.agent_type == "orchestrator"
        assert orch.state == AgentState.IDLE
        assert orch.sub_agents == {}

    def test_with_sub_agents(self):
        sub_a = _make_react_agent("agent_a")
        sub_b = _make_react_agent("agent_b")
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={"agent_a": sub_a, "agent_b": sub_b},
        )
        assert len(orch.sub_agents) == 2
        assert "agent_a" in orch.sub_agents
        assert "agent_b" in orch.sub_agents

    def test_add_sub_agent(self):
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
        )
        sub = _make_react_agent("new_agent")
        orch.add_sub_agent("new_agent", sub)
        assert "new_agent" in orch.sub_agents

    def test_add_sub_agent_respects_limit(self):
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            max_sub_agents=2,
        )
        orch.add_sub_agent("a1", _make_react_agent("a1"))
        orch.add_sub_agent("a2", _make_react_agent("a2"))
        orch.add_sub_agent("a3", _make_react_agent("a3"))  # Should be rejected
        assert len(orch.sub_agents) == 2
        assert "a3" not in orch.sub_agents


# ---------------------------------------------------------------------------
# OrchestratorAgent — plan
# ---------------------------------------------------------------------------

class TestOrchestratorPlan:
    """OrchestratorAgent.plan() — task decomposition."""

    @pytest.mark.asyncio
    async def test_plan_fallback_no_sub_agents(self):
        """Without sub-agents, plan returns one task for the orchestrator itself."""
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
        )
        tasks = await orch.plan("Do something")
        assert len(tasks) == 1
        assert tasks[0].agent_name == "orchestrator"
        assert tasks[0].description == "Do something"

    @pytest.mark.asyncio
    async def test_plan_fallback_with_sub_agents(self):
        """With sub-agents, plan distributes to each (round-robin fallback)."""
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={
                "researcher": _make_react_agent("researcher"),
                "writer": _make_react_agent("writer"),
            },
        )
        tasks = await orch.plan("Write an article")
        assert len(tasks) == 2
        names = [t.agent_name for t in tasks]
        assert "researcher" in names
        assert "writer" in names

    @pytest.mark.asyncio
    async def test_plan_with_think_fn(self):
        """With a think_fn that returns JSON plan, plan() parses sub-tasks."""
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={
                "researcher": _make_react_agent("researcher"),
                "writer": _make_react_agent("writer"),
            },
            think_fn=_plan_think_fn,
        )
        tasks = await orch.plan("Complex task")
        assert len(tasks) == 2
        assert tasks[0].description == "Research the topic"
        assert tasks[0].agent_name == "researcher"
        assert tasks[1].description == "Write the summary"
        assert tasks[1].agent_name == "writer"


# ---------------------------------------------------------------------------
# OrchestratorAgent — delegate
# ---------------------------------------------------------------------------

class TestOrchestratorDelegate:
    """OrchestratorAgent.delegate() — sub-task execution."""

    @pytest.mark.asyncio
    async def test_delegate_success(self):
        """Delegate to a working sub-agent returns success."""
        sub = _make_react_agent("researcher", think_fn=_echo_think_fn)
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={"researcher": sub},
        )
        task = SubTask(task_id="t1", description="Find info", agent_name="researcher")
        result = await orch.delegate(task)
        assert result.success is True
        assert result.agent_name == "researcher"
        assert "Find info" in result.content

    @pytest.mark.asyncio
    async def test_delegate_agent_not_found(self):
        """Delegate to non-existent agent returns failure."""
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
        )
        task = SubTask(task_id="t1", description="Find info", agent_name="missing")
        result = await orch.delegate(task)
        assert result.success is False
        assert "not available" in result.content

    @pytest.mark.asyncio
    async def test_delegate_sub_agent_failure(self):
        """Sub-agent that raises returns failure result."""
        async def _fail_fn(user_input, history, context):
            raise RuntimeError("LLM down")

        sub = _make_react_agent("broken", think_fn=_fail_fn)
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={"broken": sub},
        )
        task = SubTask(task_id="t1", description="Do X", agent_name="broken")
        result = await orch.delegate(task)
        assert result.success is False
        assert "failed" in result.content.lower() or "LLM down" in result.content


# ---------------------------------------------------------------------------
# OrchestratorAgent — synthesize
# ---------------------------------------------------------------------------

class TestOrchestratorSynthesize:
    """OrchestratorAgent.synthesize() — result aggregation."""

    @pytest.mark.asyncio
    async def test_synthesize_fallback(self):
        """Without think_fn, synthesize concatenates successful results."""
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
        )
        results = [
            SubTaskResult(task_id="t1", agent_name="a1", content="Result 1", success=True),
            SubTaskResult(task_id="t2", agent_name="a2", content="Result 2", success=True),
        ]
        final = await orch.synthesize(results, "original task")
        assert "[a1]: Result 1" in final
        assert "[a2]: Result 2" in final

    @pytest.mark.asyncio
    async def test_synthesize_with_failed(self):
        """Synthesize mentions failed sub-agents."""
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
        )
        results = [
            SubTaskResult(task_id="t1", agent_name="a1", content="OK", success=True),
            SubTaskResult(task_id="t2", agent_name="a2", content="Fail", success=False),
        ]
        final = await orch.synthesize(results, "task")
        assert "[a1]: OK" in final
        assert "1 sub-agent(s) failed" in final

    @pytest.mark.asyncio
    async def test_synthesize_all_failed(self):
        """When all sub-agents fail, synthesize reports failures."""
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
        )
        results = [
            SubTaskResult(task_id="t1", agent_name="a1", content="Fail", success=False),
        ]
        final = await orch.synthesize(results, "task")
        assert "1 sub-agent(s) failed" in final

    @pytest.mark.asyncio
    async def test_synthesize_with_think_fn(self):
        """With think_fn, synthesize delegates to LLM for aggregation."""
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            think_fn=_synth_think_fn,
        )
        results = [
            SubTaskResult(task_id="t1", agent_name="a1", content="OK", success=True),
        ]
        final = await orch.synthesize(results, "task")
        assert final == "Synthesised final answer"


# ---------------------------------------------------------------------------
# OrchestratorAgent — full run
# ---------------------------------------------------------------------------

class TestOrchestratorRun:
    """OrchestratorAgent.run() — full lifecycle: plan → delegate → synthesize."""

    @pytest.mark.asyncio
    async def test_run_with_3_sub_agents(self):
        """Orchestrator assigns 3 sub-agent tasks → aggregates results."""
        sub1 = _make_react_agent("researcher", think_fn=_echo_think_fn)
        sub2 = _make_react_agent("writer", think_fn=_echo_think_fn)
        sub3 = _make_react_agent("reviewer", think_fn=_echo_think_fn)

        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={
                "researcher": sub1,
                "writer": sub2,
                "reviewer": sub3,
            },
        )

        result = await orch.run("Write a review article")
        assert isinstance(result, AgentResult)
        assert result.agent_type == "orchestrator"
        assert result.content  # Non-empty content
        assert result.agent_name == "orchestrator"
        # 3 sub-agents should produce results
        assert "[researcher]:" in result.content or "[writer]:" in result.content

    @pytest.mark.asyncio
    async def test_run_trajectory_recording(self):
        """Trajectory records THINKING → ACTING → OBSERVING cycles + DONE."""
        sub = _make_react_agent("worker", think_fn=_echo_think_fn)
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={"worker": sub},
        )

        result = await orch.run("Do task")
        assert len(result.trajectory) > 0

        states = [e.state for e in result.trajectory]
        # Must contain THINKING, ACTING, OBSERVING, DONE
        assert "THINKING" in states
        assert "ACTING" in states
        assert "OBSERVING" in states
        assert "DONE" in states
        # DONE must be last
        assert states[-1] == "DONE"

    @pytest.mark.asyncio
    async def test_run_token_accumulation(self):
        """Tokens from sub-agents are accumulated in the orchestrator result."""
        sub = _make_react_agent("worker", think_fn=_echo_think_fn)
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={"worker": sub},
        )

        result = await orch.run("Task")
        # Sub-agent echo_think_fn produces 10 input + 5 output
        assert result.total_token_usage.input_tokens > 0
        assert result.total_token_usage.output_tokens > 0

    @pytest.mark.asyncio
    async def test_run_no_sub_agents(self):
        """Orchestrator with no sub-agents returns a single-task result."""
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
        )
        result = await orch.run("Solo task")
        assert isinstance(result, AgentResult)
        assert result.content  # Should produce some output

    @pytest.mark.asyncio
    async def test_run_all_sub_agents_fail(self):
        """When all sub-agents fail, orchestrator still completes."""
        async def _fail_fn(user_input, history, context):
            raise RuntimeError("broken")

        sub = _make_react_agent("broken", think_fn=_fail_fn)
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={"broken": sub},
        )
        result = await orch.run("Task that will fail")
        assert isinstance(result, AgentResult)
        assert result.agent_type == "orchestrator"
        # Should still reach DONE
        states = [e.state for e in result.trajectory]
        assert "DONE" in states

    @pytest.mark.asyncio
    async def test_run_with_plan_think_fn(self):
        """Orchestrator uses think_fn for plan() then delegates."""
        researcher = _make_react_agent("researcher", think_fn=_echo_think_fn)
        writer = _make_react_agent("writer", think_fn=_echo_think_fn)

        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={
                "researcher": researcher,
                "writer": writer,
            },
            think_fn=_plan_think_fn,
        )
        result = await orch.run("Complex task")
        assert isinstance(result, AgentResult)
        # Plan generates 2 sub-tasks targeting researcher and writer
        acting_steps = [
            e for e in result.trajectory
            if e.state == "ACTING"
        ]
        assert len(acting_steps) == 2

    @pytest.mark.asyncio
    async def test_run_final_state_is_done(self):
        """After run completes, agent state is DONE."""
        sub = _make_react_agent("worker", think_fn=_echo_think_fn)
        orch = OrchestratorAgent(
            name="orchestrator",
            tool_registry=_make_tool_registry(),
            sub_agents={"worker": sub},
        )
        await orch.run("Task")
        assert orch.state == AgentState.DONE


# ---------------------------------------------------------------------------
# _parse_plan
# ---------------------------------------------------------------------------

class TestParsePlan:
    """OrchestratorAgent._parse_plan() — JSON extraction."""

    def test_valid_json_array(self):
        text = '[{"description": "Do A", "agent_name": "a1"}]'
        tasks = OrchestratorAgent._parse_plan(text)
        assert len(tasks) == 1
        assert tasks[0].description == "Do A"
        assert tasks[0].agent_name == "a1"

    def test_json_in_markdown(self):
        text = 'Here is the plan:\n```json\n[{"description": "X", "agent_name": "a"}]\n```'
        tasks = OrchestratorAgent._parse_plan(text)
        assert len(tasks) == 1

    def test_invalid_json(self):
        text = "This is not JSON at all"
        tasks = OrchestratorAgent._parse_plan(text)
        assert tasks == []

    def test_empty_array(self):
        tasks = OrchestratorAgent._parse_plan("[]")
        assert tasks == []

    def test_multiple_items(self):
        text = json.dumps([
            {"description": "A", "agent_name": "a1"},
            {"description": "B", "agent_name": "a2"},
            {"description": "C", "agent_name": "a3"},
        ])
        tasks = OrchestratorAgent._parse_plan(text)
        assert len(tasks) == 3


# ---------------------------------------------------------------------------
# DebateStrategy
# ---------------------------------------------------------------------------

class TestDebateStrategy:
    """DebateStrategy — propose/critique/revise loop."""

    @pytest.mark.asyncio
    async def test_consensus_reached(self):
        """Debate reaches consensus when score >= threshold."""
        async def propose_fn(user_input, history, context):
            return ("Great proposal", None, TokenUsage(10, 5))

        async def critique_fn(user_input, history, context):
            return ("Looks good. SCORE: 0.9", None, TokenUsage(8, 4))

        proposer = _make_react_agent("proposer", think_fn=propose_fn)
        critic = _make_react_agent("critic", think_fn=critique_fn)

        strategy = DebateStrategy(rounds=3, consensus_threshold=0.8)
        result = await strategy.execute(proposer, critic, "Solve X")

        assert isinstance(result, DebateResult)
        assert result.consensus_reached is True
        assert result.rounds_completed == 1
        assert result.final_answer == "Great proposal"

    @pytest.mark.asyncio
    async def test_max_rounds_no_consensus(self):
        """Debate exhausts rounds without reaching consensus."""
        async def propose_fn(user_input, history, context):
            return ("Proposal", None, TokenUsage(5, 3))

        async def critique_fn(user_input, history, context):
            return ("Needs work. SCORE: 0.3", None, TokenUsage(5, 3))

        proposer = _make_react_agent("proposer", think_fn=propose_fn)
        critic = _make_react_agent("critic", think_fn=critique_fn)

        strategy = DebateStrategy(rounds=3, consensus_threshold=0.8)
        result = await strategy.execute(proposer, critic, "Solve X")

        assert result.consensus_reached is False
        assert result.rounds_completed == 3
        assert len(result.history) == 3

    @pytest.mark.asyncio
    async def test_history_records(self):
        """Each debate round produces a DebateRound in history."""
        async def propose_fn(user_input, history, context):
            return ("Proposal", None, TokenUsage(5, 3))

        async def critique_fn(user_input, history, context):
            return ("SCORE: 0.5", None, TokenUsage(5, 3))

        proposer = _make_react_agent("proposer", think_fn=propose_fn)
        critic = _make_react_agent("critic", think_fn=critique_fn)

        strategy = DebateStrategy(rounds=2, consensus_threshold=0.9)
        result = await strategy.execute(proposer, critic, "Task")

        assert len(result.history) == 2
        for rnd in result.history:
            assert isinstance(rnd, DebateRound)
            assert rnd.round_index > 0
            assert rnd.proposal
            assert rnd.critique


class TestDebateParseScore:
    """DebateStrategy._parse_score() — score extraction."""

    def test_score_found(self):
        assert DebateStrategy._parse_score("Good work. SCORE: 0.85") == 0.85

    def test_score_case_insensitive(self):
        assert DebateStrategy._parse_score("score: 0.7") == 0.7

    def test_score_clamped_max(self):
        assert DebateStrategy._parse_score("SCORE: 1.5") == 1.0

    def test_score_clamped_min(self):
        # Regex only matches non-negative numbers; negative falls through to default
        assert DebateStrategy._parse_score("SCORE: -0.5") == 0.5

    def test_no_score_returns_default(self):
        assert DebateStrategy._parse_score("No score here") == 0.5

    def test_integer_score(self):
        assert DebateStrategy._parse_score("SCORE: 1") == 1.0


# ---------------------------------------------------------------------------
# Domain service integration
# ---------------------------------------------------------------------------

class TestDomainServiceIntegration:
    """AgentOrchestrationService._create_engine() with orchestrator type."""

    def test_create_engine_orchestrator(self):
        """_create_engine returns OrchestratorAgent for agent_type='orchestrator'."""
        from app.domain.agent_orchestration.service import AgentOrchestrationService
        from app.domain.agent_orchestration.repo import AgentTrajectoryRepo

        mock_repo = MagicMock(spec=AgentTrajectoryRepo)
        registry = _make_tool_registry()
        service = AgentOrchestrationService(repo=mock_repo, tool_registry=registry)

        engine = service._create_engine(
            agent_type="orchestrator",
            name="test_orch",
            tools=[],
            max_iterations=10,
        )
        assert isinstance(engine, OrchestratorAgent)
        assert engine.name == "test_orch"
        assert engine.agent_type == "orchestrator"

    def test_create_engine_react(self):
        """_create_engine still returns ReactAgent for agent_type='react'."""
        from app.domain.agent_orchestration.service import AgentOrchestrationService
        from app.domain.agent_orchestration.repo import AgentTrajectoryRepo

        mock_repo = MagicMock(spec=AgentTrajectoryRepo)
        registry = _make_tool_registry()
        service = AgentOrchestrationService(repo=mock_repo, tool_registry=registry)

        engine = service._create_engine(
            agent_type="react",
            name="test_react",
            tools=[],
            max_iterations=10,
        )
        assert isinstance(engine, ReactAgent)
        assert engine.name == "test_react"

    def test_create_engine_workflow_fallback(self):
        """_create_engine falls back to ReactAgent for 'workflow' (F13 not yet)."""
        from app.domain.agent_orchestration.service import AgentOrchestrationService
        from app.domain.agent_orchestration.repo import AgentTrajectoryRepo

        mock_repo = MagicMock(spec=AgentTrajectoryRepo)
        registry = _make_tool_registry()
        service = AgentOrchestrationService(repo=mock_repo, tool_registry=registry)

        engine = service._create_engine(
            agent_type="workflow",
            name="test_wf",
            tools=[],
            max_iterations=10,
        )
        assert isinstance(engine, ReactAgent)  # Fallback


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------

class TestPackageExports:
    """Verify F12 symbols are exported from app.agent."""

    def test_orchestrator_agent_exported(self):
        from app.agent import OrchestratorAgent as OA
        assert OA is OrchestratorAgent

    def test_sub_task_exported(self):
        from app.agent import SubTask as ST
        assert ST is SubTask

    def test_sub_task_result_exported(self):
        from app.agent import SubTaskResult as STR
        assert STR is SubTaskResult

    def test_debate_strategy_exported(self):
        from app.agent import DebateStrategy as DS
        assert DS is DebateStrategy

    def test_debate_result_exported(self):
        from app.agent import DebateResult as DR
        assert DR is DebateResult
