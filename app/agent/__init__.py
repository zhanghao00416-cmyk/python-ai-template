"""app.agent — Agent execution engine (independent of business domains).

Public API::

    from app.agent import AgentState, BaseAgent, ReactAgent, OrchestratorAgent
    from app.agent import TrajectoryEntry, ToolCall, TokenUsage, AgentResult
    from app.agent import SubTask, SubTaskResult, DebateStrategy, DebateResult
"""

from app.agent.state import AgentState, is_valid_transition, transition
from app.agent.trajectory import AgentResult, TokenUsage, ToolCall, TrajectoryEntry
from app.agent.base import BaseAgent
from app.agent.react import ReactAgent
from app.agent.orchestrator import (
    DebateResult,
    DebateRound,
    DebateStrategy,
    OrchestratorAgent,
    SubTask,
    SubTaskResult,
)

__all__ = [
    "AgentState",
    "is_valid_transition",
    "transition",
    "AgentResult",
    "TokenUsage",
    "ToolCall",
    "TrajectoryEntry",
    "BaseAgent",
    "ReactAgent",
    "OrchestratorAgent",
    "SubTask",
    "SubTaskResult",
    "DebateStrategy",
    "DebateRound",
    "DebateResult",
]
