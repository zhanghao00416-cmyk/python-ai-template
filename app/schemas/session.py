from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SessionRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class TruncationStrategy(str, Enum):
    RECENT_PRIORITY = "recent_priority"
    SUMMARY = "summary"
    SLIDING_WINDOW = "sliding_window"


VALID_ROLES = {r.value for r in SessionRole}


class SessionCreateRequest(BaseModel):
    user_id: str
    title: str | None = None
    intent_type: str | None = None
    model_settings: dict[str, Any] | None = Field(None, alias="model_config")
    metadata: dict[str, Any] | None = None


class SessionDetail(BaseModel):
    id: UUID
    user_id: str
    title: str | None = None
    intent_type: str | None = None
    model_settings: dict[str, Any] | None = Field(None, alias="model_config")
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] | None = None


class SessionListResponse(BaseModel):
    items: list[SessionDetail]
    total: int
    offset: int
    limit: int


class MessageCreateRequest(BaseModel):
    session_id: UUID
    role: SessionRole
    content: str
    model_name: str | None = None
    citations: list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_results: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None


class MessageDetail(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str | None = None
    token_count: int | None = None
    model_name: str | None = None
    citations: list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_results: list[dict[str, Any]] | None = None
    created_at: datetime
    metadata: dict[str, Any] | None = None


class MessageListResponse(BaseModel):
    items: list[MessageDetail]
    total: int
    offset: int
    limit: int


class ContextWindowResult(BaseModel):
    session_id: UUID
    system_prompt: str | None = None
    messages: list[MessageDetail]
    total_tokens: int
    truncated: bool
    summary: str | None = None


class MessageUpdateRequest(BaseModel):
    content: str