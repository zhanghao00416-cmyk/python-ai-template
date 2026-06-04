"""Agent state machine — states and valid transitions.

Implements AGENT_SPEC §State Machine.
States: IDLE / THINKING / ACTING / OBSERVING / DONE / ERROR

Dependency: none (pure engine layer).
"""

from __future__ import annotations

from enum import Enum

from app.core.errors import (
    ERROR_CODE_AGENT_STATE_INVALID,
    make_error,
)
from app.core.logging import get_logger

logger = get_logger("agent.state")


class AgentState(str, Enum):
    """Lifecycle states for an Agent execution."""

    IDLE = "IDLE"
    THINKING = "THINKING"
    ACTING = "ACTING"
    OBSERVING = "OBSERVING"
    DONE = "DONE"
    ERROR = "ERROR"


# Valid transitions: from_state -> set of allowed to_states
_VALID_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.IDLE: frozenset({AgentState.THINKING, AgentState.ERROR}),
    AgentState.THINKING: frozenset({AgentState.ACTING, AgentState.DONE, AgentState.ERROR}),
    AgentState.ACTING: frozenset({AgentState.OBSERVING, AgentState.ERROR}),
    AgentState.OBSERVING: frozenset({AgentState.THINKING, AgentState.ERROR}),
    AgentState.DONE: frozenset({AgentState.IDLE, AgentState.ERROR}),
    AgentState.ERROR: frozenset({AgentState.IDLE}),
}


def is_valid_transition(from_state: AgentState, to_state: AgentState) -> bool:
    """Check whether a state transition is allowed."""
    allowed = _VALID_TRANSITIONS.get(from_state, frozenset())
    return to_state in allowed


def transition(current: AgentState, target: AgentState) -> AgentState:
    """Validate and perform a state transition.

    Returns *target* on success; raises ``AgentError(7001)`` on invalid.
    Any state may transition to ERROR (always allowed).
    Any state may be reset to IDLE (always allowed).
    """
    # Universal shortcuts
    if target == AgentState.ERROR or target == AgentState.IDLE:
        return target

    # Self-loop is always allowed (e.g. THINKING → THINKING in ReAct)
    if target == current:
        return target

    if is_valid_transition(current, target):
        return target

    logger.warning(
        "agent.state.invalid_transition",
        from_state=current.value,
        to_state=target.value,
    )
    raise make_error(
        ERROR_CODE_AGENT_STATE_INVALID,
        f"Invalid transition: {current.value} → {target.value}",
    )
