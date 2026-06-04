from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PromptTemplateListItem(BaseModel):
    name: str
    directory: str | None = None
    description: str | None = None
    variables: list[str] | None = None
    version: int
    updated_at: datetime


class PromptTemplateDetail(BaseModel):
    name: str
    directory: str | None = None
    description: str | None = None
    content: str | None = None
    variables: list[str] | None = None
    version: int
    baseline_content: str | None = None
    baseline_version: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PromptUpdateRequest(BaseModel):
    content: str | None = None
    description: str | None = None
    rollback_version: int | None = None


class PromptUpdateResponse(BaseModel):
    name: str
    version: int
    previous_version: int | None = None
    updated_at: datetime | None = None


class PromptVersionItem(BaseModel):
    version: int
    content_preview: str | None = None
    description: str | None = None
    updated_by: str | None = None
    created_at: datetime | None = None


class PromptVersionListResponse(BaseModel):
    name: str
    current_version: int
    baseline_version: int | None = None
    versions: list[PromptVersionItem] = []


class PromptResetResponse(BaseModel):
    name: str
    version: int
    reset_from_version: int | None = None
    baseline_source: str | None = None
    updated_at: datetime | None = None


class PromptListResponse(BaseModel):
    items: list[PromptTemplateListItem]
    total: int
    offset: int
    limit: int


class RenderedPrompt(BaseModel):
    name: str
    content: str
    variables: dict[str, Any] = {}