"""Intent classification Pydantic schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IntentOptions(BaseModel):
    """Classification layer options."""

    keyword_enabled: bool = True
    similarity_enabled: bool = True
    multi_intent_enabled: bool = True


class IntentRequest(BaseModel):
    """Request body for POST /api/v1/intent."""

    user_id: str = Field(..., min_length=1, max_length=128)
    session_id: str = Field(..., min_length=1, max_length=128)
    query: str = Field(..., min_length=1, max_length=1000)
    candidates: list[str] | None = Field(default=None)
    options: IntentOptions = Field(default_factory=IntentOptions)


class RoutingInfo(BaseModel):
    """Recommended routing for the primary intent."""

    workflow_id: str = ""
    model: str = ""


class SubIntent(BaseModel):
    """Additional detected intent (not executed)."""

    intent: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    query: str
    original_query: str


class IntentResultData(BaseModel):
    """Data payload for intent classification response."""

    intent: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    query: str
    layer_used: str
    routing: RoutingInfo
    sub_intents: list[SubIntent] = Field(default_factory=list)


class IntentResponse(BaseModel):
    """Synchronous JSON envelope for intent classification."""

    code: int = 0
    message: str = "ok"
    data: IntentResultData
