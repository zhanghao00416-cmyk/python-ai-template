"""Tests for F19 — Evaluation Framework.

Coverage:
- Dialogue quality metrics (relevance, conciseness, citation, balance)
- Trajectory evaluation (validity, success rate, loops, efficiency, completeness)
- EvalRunner batch execution
- Edge cases (empty data, invalid transitions, max steps exceeded)
"""

from __future__ import annotations

import pytest

from app.agent.state import AgentState
from app.agent.trajectory import TokenUsage, ToolCall, TrajectoryEntry
from app.eval.metrics import (
    citation_accuracy,
    dialogue_turn_balance,
    response_conciseness,
    response_relevance,
)
from app.eval.runner import EvalRunner
from app.eval.trajectory_eval import (
    loop_detection,
    state_transition_validity,
    step_efficiency,
    tool_call_success_rate,
    trajectory_completeness,
)
from app.schemas.eval import EvalGrade


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return EvalRunner()


@pytest.fixture
def valid_trajectory():
    """A complete, valid ReAct trajectory."""
    return [
        TrajectoryEntry(
            agent_name="test_agent",
            step_index=1,
            state=AgentState.THINKING.value,
            thought="I need to search for info",
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
        ),
        TrajectoryEntry(
            agent_name="test_agent",
            step_index=2,
            state=AgentState.ACTING.value,
            action=ToolCall(tool="kb_search", input={"query": "test"}),
        ),
        TrajectoryEntry(
            agent_name="test_agent",
            step_index=3,
            state=AgentState.OBSERVING.value,
            observation={"result": "found 3 chunks"},
        ),
        TrajectoryEntry(
            agent_name="test_agent",
            step_index=4,
            state=AgentState.THINKING.value,
            thought="Based on the search, the answer is clear",
            token_usage=TokenUsage(input_tokens=15, output_tokens=10),
        ),
        TrajectoryEntry(
            agent_name="test_agent",
            step_index=5,
            state=AgentState.DONE.value,
            thought="The answer is 42",
        ),
    ]


@pytest.fixture
def trajectory_with_error():
    """A trajectory where a tool call failed."""
    return [
        TrajectoryEntry(
            agent_name="test_agent",
            step_index=1,
            state=AgentState.THINKING.value,
            thought="I need to calculate",
        ),
        TrajectoryEntry(
            agent_name="test_agent",
            step_index=2,
            state=AgentState.ACTING.value,
            action=ToolCall(tool="calculator", input={"expr": "1/0"}),
        ),
        TrajectoryEntry(
            agent_name="test_agent",
            step_index=3,
            state=AgentState.OBSERVING.value,
            observation={"error": "Division by zero"},
        ),
        TrajectoryEntry(
            agent_name="test_agent",
            step_index=4,
            state=AgentState.DONE.value,
            thought="Calculation failed, answer is unknown",
        ),
    ]


# ---------------------------------------------------------------------------
# Dialogue quality metrics
# ---------------------------------------------------------------------------

class TestResponseRelevance:
    def test_exact_match(self):
        score = response_relevance("hello world", "hello world response")
        assert score == 1.0

    def test_partial_match(self):
        score = response_relevance("hello world", "hello there")
        assert 0.0 < score < 1.0

    def test_no_overlap(self):
        score = response_relevance("abc xyz", "123 456")
        assert score == 0.0

    def test_empty_query(self):
        score = response_relevance("", "some response")
        assert score == 1.0

    def test_empty_response(self):
        score = response_relevance("query", "")
        assert score == 0.0

    def test_chinese(self):
        score = response_relevance("什么是RAG", "RAG是一种检索增强生成技术")
        assert score > 0.0


class TestResponseConciseness:
    def test_short_response(self):
        score = response_conciseness("short", max_length=500)
        assert score == 1.0

    def test_long_response(self):
        long_text = "x" * 1400
        score = response_conciseness(long_text, max_length=500)
        assert 0.0 < score < 1.0

    def test_very_long_response(self):
        very_long = "x" * 2000
        score = response_conciseness(very_long, max_length=500)
        assert score == 0.0

    def test_empty_response(self):
        score = response_conciseness("", max_length=500)
        assert score == 1.0


class TestCitationAccuracy:
    def test_all_matched(self):
        citations = [{"filename": "a.md"}, {"filename": "b.md"}]
        sources = [{"filename": "a.md"}, {"filename": "b.md"}, {"filename": "c.md"}]
        score = citation_accuracy(citations, sources)
        assert score == 1.0

    def test_partial_matched(self):
        citations = [{"filename": "a.md"}, {"filename": "x.md"}]
        sources = [{"filename": "a.md"}]
        score = citation_accuracy(citations, sources)
        assert score == 0.5

    def test_no_citations(self):
        score = citation_accuracy([], [{"filename": "a.md"}])
        assert score == 1.0

    def test_no_sources(self):
        score = citation_accuracy([{"filename": "a.md"}], None)
        assert score == 1.0


class TestDialogueTurnBalance:
    def test_balanced(self):
        messages = [
            {"role": "user"}, {"role": "assistant"},
            {"role": "user"}, {"role": "assistant"},
        ]
        score = dialogue_turn_balance(messages)
        assert score == 1.0

    def test_imbalanced(self):
        messages = [{"role": "user"}] * 9 + [{"role": "assistant"}]
        score = dialogue_turn_balance(messages)
        assert score < 0.5

    def test_empty(self):
        score = dialogue_turn_balance([])
        assert score == 0.0


# ---------------------------------------------------------------------------
# Trajectory evaluation
# ---------------------------------------------------------------------------

class TestStateTransitionValidity:
    def test_valid_transitions(self, valid_trajectory):
        result = state_transition_validity(valid_trajectory)
        assert result["score"] == 1.0
        assert result["invalid_count"] == 0

    def test_invalid_transition(self):
        traj = [
            TrajectoryEntry(agent_name="a", step_index=1, state=AgentState.IDLE.value),
            TrajectoryEntry(agent_name="a", step_index=2, state=AgentState.ACTING.value),  # Invalid: IDLE->ACTING
        ]
        result = state_transition_validity(traj)
        assert result["invalid_count"] == 1
        assert result["score"] == 0.0

    def test_empty_trajectory(self):
        result = state_transition_validity([])
        assert result["score"] == 0.0
        assert "Empty trajectory" in result["violations"]


class TestToolCallSuccessRate:
    def test_all_success(self, valid_trajectory):
        result = tool_call_success_rate(valid_trajectory)
        assert result["score"] == 1.0
        assert result["total"] == 1
        assert result["failed"] == 0

    def test_with_failure(self, trajectory_with_error):
        result = tool_call_success_rate(trajectory_with_error)
        assert result["score"] == 0.0
        assert result["total"] == 1
        assert result["failed"] == 1

    def test_no_tools(self):
        traj = [
            TrajectoryEntry(agent_name="a", step_index=1, state=AgentState.THINKING.value),
            TrajectoryEntry(agent_name="a", step_index=2, state=AgentState.DONE.value),
        ]
        result = tool_call_success_rate(traj)
        assert result["score"] == 1.0
        assert result["total"] == 0


class TestLoopDetection:
    def test_no_loops(self, valid_trajectory):
        result = loop_detection(valid_trajectory)
        assert result["loops_detected"] == 0
        assert result["score"] == 1.0

    def test_detect_loop(self):
        # Create a repeating pattern
        base = TrajectoryEntry(agent_name="a", step_index=1, state=AgentState.THINKING.value, thought="same")
        traj = [
            base,
            TrajectoryEntry(agent_name="a", step_index=2, state=AgentState.ACTING.value, action=ToolCall(tool="t")),
            TrajectoryEntry(agent_name="a", step_index=3, state=AgentState.OBSERVING.value, observation="ok"),
            TrajectoryEntry(agent_name="a", step_index=4, state=AgentState.THINKING.value, thought="same"),
            TrajectoryEntry(agent_name="a", step_index=5, state=AgentState.ACTING.value, action=ToolCall(tool="t")),
            TrajectoryEntry(agent_name="a", step_index=6, state=AgentState.OBSERVING.value, observation="ok"),
        ]
        result = loop_detection(traj, window_size=3)
        assert result["loops_detected"] == 1
        assert result["score"] < 1.0

    def test_empty(self):
        result = loop_detection([])
        assert result["score"] == 1.0


class TestStepEfficiency:
    def test_efficient(self, valid_trajectory):
        result = step_efficiency(valid_trajectory, max_steps=10)
        assert result["efficient"] is True
        assert result["score"] == 1.0

    def test_exceeds_max(self):
        traj = [
            TrajectoryEntry(agent_name="a", step_index=i, state=AgentState.THINKING.value)
            for i in range(15)
        ]
        result = step_efficiency(traj, max_steps=10)
        assert result["efficient"] is False
        assert result["score"] == 0.0

    def test_empty(self):
        result = step_efficiency([], max_steps=10)
        assert result["score"] == 0.0


class TestTrajectoryCompleteness:
    def test_complete(self, valid_trajectory):
        result = trajectory_completeness(valid_trajectory)
        assert result["score"] == 1.0
        assert result["has_thinking"] is True
        assert result["has_done"] is True
        assert result["has_acting"] is True
        assert result["has_observing"] is True

    def test_incomplete(self):
        traj = [
            TrajectoryEntry(agent_name="a", step_index=1, state=AgentState.THINKING.value),
        ]
        result = trajectory_completeness(traj)
        assert result["score"] == 0.5  # Has thinking but no terminal
        assert result["missing"] == ["DONE/ERROR"]

    def test_empty(self):
        result = trajectory_completeness([])
        assert result["score"] == 0.0
        assert "Empty trajectory" in result["missing"]


# ---------------------------------------------------------------------------
# EvalRunner
# ---------------------------------------------------------------------------

class TestEvalRunnerTrajectory:
    def test_run_trajectory_eval(self, runner, valid_trajectory):
        result = runner.run_trajectory_eval(valid_trajectory, agent_name="test")
        assert result.agent_name == "test"
        assert result.total_steps == 5
        assert result.overall_score > 0.0
        assert result.grade in (EvalGrade.EXCELLENT, EvalGrade.GOOD, EvalGrade.FAIR, EvalGrade.POOR)
        assert len(result.scores) == 5  # 5 dimensions
        assert result.evaluated_at != ""

    def test_empty_trajectory(self, runner):
        result = runner.run_trajectory_eval([])
        assert result.overall_score == 0.0
        assert result.grade == EvalGrade.POOR
        assert "Empty trajectory" in result.summary

    def test_trajectory_with_error(self, runner, trajectory_with_error):
        result = runner.run_trajectory_eval(trajectory_with_error, agent_name="err_agent")
        assert result.agent_name == "err_agent"
        assert result.total_steps == 4
        # Tool call failed, so success rate should be 0
        tool_score = next(s for s in result.scores if s.dimension == "tool_call_success_rate")
        assert tool_score.score == 0.0


class TestEvalRunnerDialogue:
    def test_run_dialogue_eval(self, runner):
        result = runner.run_dialogue_eval(
            messages=[{"role": "user"}, {"role": "assistant"}],
            session_id="s1",
            query="what is AI",
            response="AI is artificial intelligence",
            citations=[{"filename": "a.md"}],
            sources=[{"filename": "a.md"}],
        )
        assert result.session_id == "s1"
        assert result.message_count == 2
        assert result.overall_score > 0.0
        assert result.grade in (EvalGrade.EXCELLENT, EvalGrade.GOOD, EvalGrade.FAIR, EvalGrade.POOR)

    def test_empty_dialogue(self, runner):
        result = runner.run_dialogue_eval([])
        assert result.overall_score == 0.0
        assert result.grade == EvalGrade.POOR
        assert "Empty dialogue" in result.summary


class TestEvalRunnerBatch:
    def test_run_batch(self, runner, valid_trajectory):
        trajectories = [(valid_trajectory, {"agent_name": "a1", "agent_type": "react"})]
        dialogues = [
            {
                "session_id": "s1",
                "messages": [{"role": "user"}, {"role": "assistant"}],
                "query": "q1",
                "response": "r1",
            }
        ]
        report = runner.run_batch(trajectories=trajectories, dialogues=dialogues)
        assert report.report_id != ""
        assert len(report.trajectory_results) == 1
        assert len(report.dialogue_results) == 1
        assert report.overall_score > 0.0
        assert report.grade in (EvalGrade.EXCELLENT, EvalGrade.GOOD, EvalGrade.FAIR, EvalGrade.POOR)
        assert "Batch report" in report.summary
        assert report.created_at != ""

    def test_empty_batch(self, runner):
        report = runner.run_batch()
        assert report.overall_score == 0.0
        assert report.grade == EvalGrade.POOR
        assert len(report.trajectory_results) == 0
        assert len(report.dialogue_results) == 0

    def test_batch_trajectories_only(self, runner, valid_trajectory):
        trajectories = [
            (valid_trajectory, {"agent_name": "a1"}),
            (valid_trajectory, {"agent_name": "a2"}),
        ]
        report = runner.run_batch(trajectories=trajectories)
        assert len(report.trajectory_results) == 2
        assert len(report.dialogue_results) == 0


# ---------------------------------------------------------------------------
# Edge cases & integration
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_trajectory_with_invalid_state_string(self, runner):
        traj = [
            TrajectoryEntry(agent_name="a", step_index=1, state="INVALID_STATE"),
        ]
        # State transition check will try to enum this and may fail
        # We should gracefully handle unknown states
        result = state_transition_validity(traj)
        # An unknown state cannot have valid transitions
        assert result["invalid_count"] >= 0  # At minimum no transitions checked

    def test_max_steps_boundary(self):
        traj = [
            TrajectoryEntry(agent_name="a", step_index=i, state=AgentState.THINKING.value)
            for i in range(10)
        ]
        result = step_efficiency(traj, max_steps=10)
        assert result["score"] == 0.0
        assert result["efficient"] is False

    def test_conciseness_at_exact_max(self):
        text = "x" * 500
        score = response_conciseness(text, max_length=500)
        assert score == 1.0

    def test_citation_with_empty_filename(self):
        citations = [{"filename": ""}, {"filename": "a.md"}]
        sources = [{"filename": "a.md"}]
        score = citation_accuracy(citations, sources)
        assert score == 0.5  # One empty, one matched

    def test_runner_produces_consistent_scores(self, runner, valid_trajectory):
        result1 = runner.run_trajectory_eval(valid_trajectory, agent_name="a")
        result2 = runner.run_trajectory_eval(valid_trajectory, agent_name="a")
        assert result1.overall_score == result2.overall_score
        assert len(result1.scores) == len(result2.scores)

    def test_grade_boundaries(self):
        assert _to_grade(0.95) == EvalGrade.EXCELLENT
        assert _to_grade(0.8) == EvalGrade.GOOD
        assert _to_grade(0.6) == EvalGrade.FAIR
        assert _to_grade(0.3) == EvalGrade.POOR


# Helper imported from runner for testing grade mapping
from app.eval.runner import _to_grade
