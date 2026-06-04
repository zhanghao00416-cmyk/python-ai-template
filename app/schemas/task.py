from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    KB_UPLOAD = "kb_upload"
    AGENT_RUN = "agent_run"
    WORKFLOW_RUN = "workflow_run"
    BATCH_IMPORT = "batch_import"
    BATCH_EVAL = "batch_eval"
    BATCH_EMBED = "batch_embed"
    CUSTOM = "custom"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


VALID_TASK_STATUSES = {s.value for s in TaskStatus}

TASK_TYPE_VALUES = {t.value for t in TaskType}


class TaskCreateRequest(BaseModel):
    task_type: TaskType
    input_data: dict[str, Any] | None = None
    callback_url: str | None = None
    metadata: dict[str, Any] | None = None


class TaskCreateResponse(BaseModel):
    task_id: UUID
    task_type: str
    status: str
    created_at: datetime


class TaskStatusResponse(BaseModel):
    task_id: UUID
    task_type: str
    status: str
    progress: float | None = None
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None