"""Trajectory evaluation — algorithmic evaluation of Agent execution traces.

Evaluates:
- State transition validity (against AGENT_SPEC rules)
- Tool call success rate
- Loop detection (repeated states/thoughts)
- Step efficiency (vs max_steps)
- Trajectory completeness (presence of required phases)

Dependency: app/agent/state.py (AgentState + transition rules),
            app/agent/trajectory.py (TrajectoryEntry).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.agent.state import AgentState, is_valid_transition
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agent.trajectory import TrajectoryEntry

logger = get_logger("eval.trajectory")


# ---------------------------------------------------------------------------
# State transition validity
# ---------------------------------------------------------------------------

def state_transition_validity(trajectory: list[TrajectoryEntry]) -> dict[str, Any]:
    """Check whether state transitions in the trajectory follow AGENT_SPEC rules.

    Returns:
        {
            "score": float (0.0-1.0),
            "invalid_count": int,
            "total_transitions": int,
            "violations": list[str],
        }
    """
    if not trajectory:
        return {"score": 0.0, "invalid_count": 0, "total_transitions": 0, "violations": ["Empty trajectory"]}

    violations: list[str] = []
    invalid_count = 0

    for i in range(len(trajectory) - 1):
        from_state = AgentState(trajectory[i].state)
        to_state = AgentState(trajectory[i + 1].state)

        if not is_valid_transition(from_state, to_state):
            invalid_count += 1
            violations.append(
                f"Step {trajectory[i].step_index}→{trajectory[i + 1].step_index}: "
                f"{from_state.value} → {to_state.value}"
            )

    total = len(trajectory) - 1
    score = 1.0 if total == 0 else 1.0 - (invalid_count / total)
    return {
        "score": round(score, 4),
        "invalid_count": invalid_count,
        "total_transitions": total,
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Tool call success rate
# ---------------------------------------------------------------------------

def tool_call_success_rate(trajectory: list[TrajectoryEntry]) -> dict[str, Any]:
    """Calculate the ratio of successful tool calls.

    A tool call is considered failed if the observation contains an "error" key
    or the tool was not found (AGENT_SPEC: tool_not_found).
    """
    tool_calls = [e for e in trajectory if e.action is not None]
    if not tool_calls:
        return {"score": 1.0, "total": 0, "success": 0, "failed": 0}

    failed = 0
    for entry in tool_calls:
        # Find the matching OBSERVING step (usually the next entry)
        obs = entry.observation
        if obs is None:
            # Look ahead for the next observation in the trajectory
            idx = next((i for i, e in enumerate(trajectory) if e.step_index == entry.step_index), -1)
            if idx >= 0 and idx + 1 < len(trajectory):
                obs = trajectory[idx + 1].observation

        if (isinstance(obs, dict) and "error" in obs) or (
            isinstance(obs, str) and obs.startswith("Tool error:")
        ):
            failed += 1

    success = len(tool_calls) - failed
    score = success / len(tool_calls)
    return {
        "score": round(score, 4),
        "total": len(tool_calls),
        "success": success,
        "failed": failed,
    }


# ---------------------------------------------------------------------------
# Loop detection
# ---------------------------------------------------------------------------

def loop_detection(
    trajectory: list[TrajectoryEntry],
    *,
    window_size: int = 3,
) -> dict[str, Any]:
    """Detect repeated patterns of (state, thought) within a sliding window.

    Returns:
        {
            "score": float (1.0 = no loops detected),
            "loops_detected": int,
            "details": list[str],
        }
    """
    if not trajectory:
        return {"score": 1.0, "loops_detected": 0, "details": []}

    patterns: dict[tuple[str, ...], int] = {}
    loops = 0
    details: list[str] = []

    for i in range(len(trajectory) - window_size + 1):
        window = trajectory[i : i + window_size]
        key = tuple(e.state for e in window)
        thought_key = tuple((e.thought or "")[:80] for e in window)
        combined = key + thought_key

        patterns[combined] = patterns.get(combined, 0) + 1
        if patterns[combined] == 2:
            loops += 1
            details.append(f"Loop at step {window[0].step_index} (pattern repeated)")

    # Score: 1.0 if no loops, decays with loop count
    score = max(0.0, 1.0 - loops * 0.25)
    return {
        "score": round(score, 4),
        "loops_detected": loops,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Step efficiency
# ---------------------------------------------------------------------------

def step_efficiency(
    trajectory: list[TrajectoryEntry],
    max_steps: int = 10,
) -> dict[str, Any]:
    """Measure whether the agent completed within reasonable step count.

    Score = 1.0 if steps <= max_steps/2,
    linear decay to 0.0 at max_steps.
    """
    steps = len(trajectory)
    if steps == 0:
        return {"score": 0.0, "steps": 0, "max_steps": max_steps, "efficient": False}

    half = max(1, max_steps // 2)
    if steps <= half:
        score = 1.0
    elif steps >= max_steps:
        score = 0.0
    else:
        score = 1.0 - (steps - half) / (max_steps - half)

    return {
        "score": round(score, 4),
        "steps": steps,
        "max_steps": max_steps,
        "efficient": steps < max_steps,
    }


# ---------------------------------------------------------------------------
# Trajectory completeness
# ---------------------------------------------------------------------------

def trajectory_completeness(trajectory: list[TrajectoryEntry]) -> dict[str, Any]:
    """Check whether the trajectory contains all required lifecycle phases.

    Required: at least one THINKING, one DONE or ERROR.
    Optional but recommended: ACTING, OBSERVING.
    """
    if not trajectory:
        return {
            "score": 0.0,
            "has_thinking": False,
            "has_acting": False,
            "has_observing": False,
            "has_done": False,
            "has_error": False,
            "missing": ["Empty trajectory"],
        }

    states = {AgentState(e.state) for e in trajectory}
    has_thinking = AgentState.THINKING in states
    has_acting = AgentState.ACTING in states
    has_observing = AgentState.OBSERVING in states
    has_done = AgentState.DONE in states
    has_error = AgentState.ERROR in states
    has_terminal = has_done or has_error

    missing: list[str] = []
    if not has_thinking:
        missing.append("THINKING")
    if not has_terminal:
        missing.append("DONE/ERROR")

    # Base score: 0.5 for having THINKING, +0.25 for ACTING, +0.25 for OBSERVING
    # If no terminal state, cap at 0.5
    score = 0.0
    if has_thinking:
        score = 0.5
        if has_terminal:
            if has_acting:
                score += 0.25
            if has_observing:
                score += 0.25
        # Without terminal, score stays at 0.5 regardless of acting/observing

    return {
        "score": round(score, 4),
        "has_thinking": has_thinking,
        "has_acting": has_acting,
        "has_observing": has_observing,
        "has_done": has_done,
        "has_error": has_error,
        "missing": missing,
    }
