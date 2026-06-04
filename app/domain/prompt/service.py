from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from app.core.errors import ErrorCode, TaskError, make_error
from app.domain.prompt.repo import (
    PromptTemplateRepo,
    PromptTemplateVersionRepo,
    extract_template_variables,
)
from app.infra.models import PromptTemplateModel, PromptTemplateVersionModel
from app.schemas.prompt import (
    PromptTemplateDetail,
    PromptTemplateListItem,
    PromptUpdateResponse,
    PromptVersionItem,
    PromptVersionListResponse,
    PromptResetResponse,
    RenderedPrompt,
)

logger = structlog.get_logger("domain.prompt.service")

_CONTENT_PREVIEW_LENGTH = 100


class PromptDomainService:
    """Domain service for prompt template management.

    Orchestrates PG persistence (via repos) and file-system loading
    (via PromptManager). Provides version management, rollback, and reset.
    """

    def __init__(
        self,
        template_repo: PromptTemplateRepo,
        version_repo: PromptTemplateVersionRepo,
        prompt_manager: Any,
    ) -> None:
        self._template_repo = template_repo
        self._version_repo = version_repo
        self._prompt_manager = prompt_manager

    async def get_template(self, name: str) -> PromptTemplateDetail:
        template = await self._template_repo.get_by_name(name)
        if template is None:
            raise TaskError(ErrorCode.PROMPT_NOT_FOUND, f"Prompt template '{name}' not found")
        return PromptTemplateDetail(
            name=template.name,
            directory=template.directory,
            description=template.description,
            content=template.content,
            variables=template.variables,
            version=template.version,
            baseline_content=template.baseline_content,
            baseline_version=template.baseline_version,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    async def list_templates(
        self,
        directory: str | None = None,
        name: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PromptTemplateListItem], int]:
        from app.infra.database import Pagination

        pagination = Pagination(offset=offset, limit=limit, sort_by="updated_at", sort_order="desc")
        items, total = await self._template_repo.list_templates(
            directory=directory,
            name_filter=name,
            pagination=pagination,
        )
        list_items = [
            PromptTemplateListItem(
                name=t.name,
                directory=t.directory,
                description=t.description,
                variables=t.variables,
                version=t.version,
                updated_at=t.updated_at,
            )
            for t in items
        ]
        return list_items, total

    async def update_template(
        self,
        name: str,
        content: str | None = None,
        description: str | None = None,
        rollback_version: int | None = None,
    ) -> PromptUpdateResponse:
        template = await self._template_repo.get_by_name(name)
        if template is None:
            raise TaskError(ErrorCode.PROMPT_NOT_FOUND, f"Prompt template '{name}' not found")

        previous_version = template.version

        if rollback_version is not None and content is not None:
            raise TaskError(
                ErrorCode.VALIDATION_ERROR,
                "Cannot specify both content and rollback_version; they are mutually exclusive",
            )

        if rollback_version is not None:
            version_entry = await self._version_repo.get_version(template.id, rollback_version)
            if version_entry is None:
                raise TaskError(
                    ErrorCode.PROMPT_NOT_FOUND,
                    f"Version {rollback_version} not found for template '{name}'",
                )
            content = version_entry.content

        if content is None and rollback_version is None:
            raise TaskError(
                ErrorCode.VALIDATION_ERROR,
                "Must provide either content or rollback_version",
            )

        variables = extract_template_variables(content) if content else template.variables

        new_version = previous_version + 1

        now = datetime.now(timezone.utc)
        update_data: dict = {
            "content": content,
            "variables": variables,
            "version": new_version,
        }
        if description is not None:
            update_data["description"] = description

        updated = await self._template_repo.update_template(name, update_data)
        if updated is None:
            raise TaskError(ErrorCode.PROMPT_WRITE_FAILED, f"Failed to update template '{name}'")

        await self._version_repo.create_version({
            "template_id": template.id,
            "version": new_version,
            "content": content,
            "description": description or f"Version {new_version}",
            "updated_by": "system",
        })

        if self._prompt_manager is not None:
            self._prompt_manager.update_cache(name, content, template.directory or "")

        return PromptUpdateResponse(
            name=name,
            version=new_version,
            previous_version=previous_version,
            updated_at=updated.updated_at if updated else now,
        )

    async def get_versions(
        self,
        name: str,
        offset: int = 0,
        limit: int = 20,
    ) -> PromptVersionListResponse:
        template = await self._template_repo.get_by_name(name)
        if template is None:
            raise TaskError(ErrorCode.PROMPT_NOT_FOUND, f"Prompt template '{name}' not found")

        from app.infra.database import Pagination

        pagination = Pagination(offset=offset, limit=limit, sort_by="version", sort_order="desc")
        versions, total = await self._version_repo.get_versions_by_template_id(
            template_id=template.id,
            pagination=pagination,
        )
        version_items = [
            PromptVersionItem(
                version=v.version,
                content_preview=(v.content[:_CONTENT_PREVIEW_LENGTH] + "...") if v.content and len(v.content) > _CONTENT_PREVIEW_LENGTH else v.content,
                description=v.description,
                updated_by=v.updated_by,
                created_at=v.created_at,
            )
            for v in versions
        ]
        return PromptVersionListResponse(
            name=name,
            current_version=template.version,
            baseline_version=template.baseline_version,
            versions=version_items,
        )

    async def reset_template(self, name: str) -> PromptResetResponse:
        template = await self._template_repo.get_by_name(name)
        if template is None:
            raise TaskError(ErrorCode.PROMPT_NOT_FOUND, f"Prompt template '{name}' not found")

        baseline_content = self._prompt_manager.load_from_file(name) if self._prompt_manager else None
        if baseline_content is None:
            baseline_content = template.baseline_content

        if baseline_content is None:
            raise TaskError(ErrorCode.PROMPT_WRITE_FAILED, f"No baseline content found for template '{name}'")

        previous_version = template.version
        new_version = previous_version + 1

        variables = extract_template_variables(baseline_content)

        update_data: dict = {
            "content": baseline_content,
            "variables": variables,
            "version": new_version,
        }
        updated = await self._template_repo.update_template(name, update_data)

        await self._version_repo.create_version({
            "template_id": template.id,
            "version": new_version,
            "content": baseline_content,
            "description": f"Reset to baseline (version {template.baseline_version or 1})",
            "updated_by": "system",
        })

        if self._prompt_manager is not None:
            directory = template.directory or ""
            self._prompt_manager.update_cache(name, baseline_content, directory)

        return PromptResetResponse(
            name=name,
            version=new_version,
            reset_from_version=previous_version,
            baseline_source=f"prompts/{template.directory}/{name}.md" if template.directory else f"prompts/{name}.md",
            updated_at=updated.updated_at if updated else None,
        )

    def render(self, name: str, variables: dict[str, Any]) -> RenderedPrompt:
        content = self._prompt_manager.get_cached(name)
        if content is None:
            raise TaskError(ErrorCode.PROMPT_NOT_FOUND, f"Prompt template '{name}' not found in cache")

        for var_name, var_value in variables.items():
            content = content.replace(f"{{{{{var_name}}}}}", str(var_value))

        return RenderedPrompt(name=name, content=content, variables=variables)