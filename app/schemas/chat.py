from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for POST /api/v1/chat."""

    user_id: str
    session_id: str
    query: str = Field(..., min_length=1)
    stream: bool = True
    model_override: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    title: str | None = Field(None, description="Session title; used only when auto-creating session")
    model_settings: dict[str, Any] | None = Field(None, description="Model config; used only when auto-creating session")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatUsage(BaseModel):
    """Token usage summary."""

    input_tokens: int
    output_tokens: int
    model: str


class ChatResponseData(BaseModel):
    """Data payload for synchronous chat response."""

    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    usage: ChatUsage


class ChatResponse(BaseModel):
    """Synchronous JSON envelope for chat."""

    code: int = 0
    message: str = "ok"
    data: ChatResponseData


class ChatSessionResponse(BaseModel):
    """Response for GET /api/v1/chat/sessions/{session_id}."""

    code: int = 0
    message: str = "ok"
    data: dict[str, Any]


class ChatMessagesResponse(BaseModel):
    """Response for GET /api/v1/chat/sessions/{session_id}/messages."""

    code: int = 0
    message: str = "ok"
    data: dict[str, Any]


class ChatDeleteResponse(BaseModel):
    """Response for DELETE /api/v1/chat/sessions/{session_id}."""

    code: int = 0
    message: str = "ok"
    data: dict[str, Any]
