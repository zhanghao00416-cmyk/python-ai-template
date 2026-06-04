from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    content: str | list[dict[str, Any]] = ""


class LLMRequest(BaseModel):
    messages: list[Message]
    model: str | None = None
    task_type: str = "chat"
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    timeout: float = 30.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMChunk(BaseModel):
    content: str | None = None
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None