"""Agent schemas — request/response models for Agent API endpoints.

Aligned with API_CONTRACT.md §Agent:
  POST /api/v1/agent/run
  GET  /api/v1/agent/trajectories
  GET  /api/v1/agent/trajectories/{task_id}

Dependency: none (pure Pydantic models).
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentType(str, Enum):
    """Supported agent engine types."""

    REACT = "react"
    WORKFLOW = "workflow"
    ORCHESTRATOR = "orchestrator"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class AgentRunRequest(BaseModel):
    """POST /api/v1/agent/run request body."""

    user_id: str
    session_id: str
    query: str = Field(..., min_length=1)
    agent_type: AgentType = AgentType.REACT
    agent_name: str | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    max_steps: int = Field(default=10, ge=1, le=50)
    stream: bool = True
    model_override: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Response — sync mode
# ---------------------------------------------------------------------------

class TrajectoryStepDetail(BaseModel):
    """A single step in the agent trajectory (sync response)."""

    step_index: int
    state: str
    thought: str | None = None
    action: dict[str, Any] | None = None
    observation: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None
    created_at: str | None = None


class AgentUsageDetail(BaseModel):
    """Token usage summary."""

    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class AgentRunResponse(BaseModel):
    """POST /api/v1/agent/run sync response (stream=false)."""

    task_id: str | None = None
    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    trajectory: list[TrajectoryStepDetail] = Field(default_factory=list)
    usage: AgentUsageDetail = Field(default_factory=AgentUsageDetail)


# ---------------------------------------------------------------------------
# Trajectory list / detail
# ---------------------------------------------------------------------------

class TrajectoryListItem(BaseModel):
    """GET /api/v1/agent/trajectories — summary item."""

    task_id: str
    session_id: str
    agent_name: str
    agent_type: str
    step_count: int
    status: str
    created_at: str


class TrajectoryDetail(BaseModel):
    """GET /api/v1/agent/trajectories/{task_id} — full detail."""

    task_id: str
    session_id: str
    agent_name: str
    agent_type: str
    status: str
    steps: list[TrajectoryStepDetail] = Field(default_factory=list)
    total_token_usage: AgentUsageDetail = Field(default_factory=AgentUsageDetail)
    created_at: str
    completed_at: str | None = None
