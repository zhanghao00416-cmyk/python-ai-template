"""Workflow schemas — Pydantic request/response models for Workflow API.

Implements API_CONTRACT.md Workflow section:
- POST /api/v1/workflow/run  → WorkflowRunRequest / WorkflowRunResponse
- GET  /api/v1/workflow/runs/{task_id} → WorkflowStatusDetail
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WorkflowNodeStatus(StrEnum):
    """Status of a single workflow node execution."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStatus(StrEnum):
    """Overall workflow execution status."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class WorkflowRunRequest(BaseModel):
    """POST /api/v1/workflow/run — execute a workflow DAG."""

    user_id: str = Field(..., description="用户标识")
    session_id: str = Field(..., description="会话标识")
    workflow_id: str = Field(..., description="workflows/ 目录中的工作流名称")
    inputs: dict[str, Any] = Field(default_factory=dict, description="工作流键值输入参数")
    stream: bool = Field(default=True, description="默认 true; false 返回同步 JSON")
    metadata: dict[str, Any] = Field(default_factory=dict, description="可扩展业务元数据")


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class WorkflowNodeResult(BaseModel):
    """Single node execution result within a workflow run."""

    name: str = Field(..., description="节点名称")
    status: str = Field(default="completed", description="completed | failed | skipped")
    duration_ms: float = Field(default=0.0, description="执行耗时(ms)")
    output: dict[str, Any] | None = Field(default=None, description="节点输出")
    error: str | None = Field(default=None, description="错误信息(仅 failed 状态)")


class WorkflowRunResponse(BaseModel):
    """POST /api/v1/workflow/run — sync response (stream=false)."""

    task_id: str = Field(..., description="执行任务 ID")
    workflow_id: str = Field(..., description="工作流名称")
    content: str = Field(default="", description="工作流最终输出文本")
    nodes: list[WorkflowNodeResult] = Field(default_factory=list, description="各节点执行结果")
    usage: dict[str, Any] | None = Field(default=None, description="Token 使用统计")


class WorkflowStatusDetail(BaseModel):
    """GET /api/v1/workflow/runs/{task_id} — workflow execution detail."""

    task_id: str
    workflow_id: str
    status: str = Field(..., description="running | completed | failed")
    nodes: list[WorkflowNodeResult] = Field(default_factory=list)
    total_duration_ms: float = Field(default=0.0)
    created_at: str | None = Field(default=None)
    completed_at: str | None = Field(default=None)
