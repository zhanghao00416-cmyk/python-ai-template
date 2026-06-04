"""Agent trajectory data models — in-memory representations.

Implements AGENT_SPEC §Trajectory Entry.
TrajectoryEntry records each step of an Agent's ReAct execution.
The DB persistence model lives in ``app/infra/models.py`` (AgentTrajectoryModel).

Dependency: app/agent/state.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token usage for a single LLM call or cumulative agent run."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool invocation request from the LLM."""

    tool: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrajectoryEntry:
    """One step in an Agent's ReAct execution cycle.

    Mirrors ``AgentTrajectoryModel`` columns for seamless serialisation.
    """

    agent_name: str
    step_index: int
    state: str  # AgentState.value
    thought: str | None = None
    action: ToolCall | None = None
    observation: Any | None = None
    token_usage: TokenUsage | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # -- serialisation helpers ------------------------------------------------

    def action_to_dict(self) -> dict[str, Any] | None:
        if self.action is None:
            return None
        return {"tool": self.action.tool, "input": self.action.input}

    def observation_to_dict(self) -> dict[str, Any] | None:
        if self.observation is None:
            return None
        if isinstance(self.observation, dict):
            return self.observation
        return {"result": str(self.observation)}

    def token_usage_to_dict(self) -> dict[str, Any] | None:
        if self.token_usage is None:
            return None
        return {
            "input_tokens": self.token_usage.input_tokens,
            "output_tokens": self.token_usage.output_tokens,
        }


@dataclass(slots=True)
class AgentResult:
    """Final result returned by ``BaseAgent.run()``."""

    content: str
    agent_name: str
    agent_type: str
    trajectory: list[TrajectoryEntry] = field(default_factory=list)
    total_token_usage: TokenUsage = field(default_factory=TokenUsage)
    task_id: str | None = None
