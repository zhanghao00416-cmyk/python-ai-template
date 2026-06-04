from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, TaskError, make_error
from app.infra.database import BaseRepo, Pagination
from app.infra.models import PromptTemplateModel, PromptTemplateVersionModel

logger = structlog.get_logger("domain.prompt.repo")

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def extract_template_variables(content: str) -> list[str]:
    """Extract {{variable}} placeholders from template content."""
    return list(dict.fromkeys(_VARIABLE_PATTERN.findall(content)))


class PromptTemplateRepo(BaseRepo[PromptTemplateModel]):
    """Repository for PromptTemplate persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PromptTemplateModel, session)

    async def get_by_name(self, name: str) -> PromptTemplateModel | None:
        stmt = self.session.query(self.model).where(self.model.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_template(self, data: dict) -> PromptTemplateModel:
        return await self.create(data)

    async def update_template(self, name: str, data: dict) -> PromptTemplateModel | None:
        template = await self.get_by_name(name)
        if template is None:
            return None
        for key, value in data.items():
            if hasattr(template, key):
                setattr(template, key, value)
        await self.session.flush()
        await self.session.refresh(template)
        return template

    async def list_templates(
        self,
        directory: str | None = None,
        name_filter: str | None = None,
        pagination: Pagination | None = None,
    ) -> tuple[list[PromptTemplateModel], int]:
        filters: dict = {}
        if directory is not None:
            filters["directory"] = directory
        if name_filter is not None:
            filters["name"] = name_filter
        result = await self.list(filters=filters or None, pagination=pagination)
        return result.items, result.total


class PromptTemplateVersionRepo(BaseRepo[PromptTemplateVersionModel]):
    """Repository for PromptTemplateVersion persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PromptTemplateVersionModel, session)

    async def create_version(self, data: dict) -> PromptTemplateVersionModel:
        return await self.create(data)

    async def get_versions_by_template_id(
        self,
        template_id: UUID,
        pagination: Pagination | None = None,
    ) -> tuple[list[PromptTemplateVersionModel], int]:
        filters = {"template_id": template_id}
        result = await self.list(
            filters=filters,
            pagination=pagination,
        )
        return result.items, result.total

    async def get_version(
        self, template_id: UUID, version: int
    ) -> PromptTemplateVersionModel | None:
        stmt = (
            self.session.query(self.model)
            .where(self.model.template_id == template_id)
            .where(self.model.version == version)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()