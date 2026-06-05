"""Prompt management API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.constants import API_PREFIX
from app.core.context import request_id_var, trace_id_var
from app.core.di import container
from app.core.errors import ErrorCode, TaskError, make_error
from app.core.response import error_response, error_to_status, ok_response
from app.domain.prompt.repo import PromptTemplateRepo, PromptTemplateVersionRepo
from app.domain.prompt.service import PromptDomainService
from app.schemas.prompt import PromptUpdateRequest
from app.services.prompt_manager import PromptManager

router = APIRouter(prefix=API_PREFIX, tags=["prompt"])


def _get_prompt_service(session: AsyncSession) -> PromptDomainService:
    """Factory to create PromptDomainService with DB session and DI dependencies."""
    template_repo = PromptTemplateRepo(session=session)
    version_repo = PromptTemplateVersionRepo(session=session)
    prompt_manager = container.resolve(PromptManager)
    return PromptDomainService(
        template_repo=template_repo,
        version_repo=version_repo,
        prompt_manager=prompt_manager,
    )


@router.get("/prompts")
async def list_prompts(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    directory: str | None = Query(default=None),
    name: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
):
    """List prompt templates with pagination and filtering.
    
    When `name` is provided and matches exactly, returns full detail (including content).
    """
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = _get_prompt_service(session)

    try:
        # If name is provided and exact match, return full detail
        if name:
            template = await service.get_template(name)
            if template:
                return ok_response(
                    data=template.model_dump(mode="json"),
                    request_id=rid,
                    trace_id=tid,
                )

        items, total = await service.list_templates(
            directory=directory,
            name=name,
            offset=offset,
            limit=limit,
        )
        return ok_response(
            data={
                "items": [item.model_dump(mode="json") for item in items],
                "total": total,
                "offset": offset,
                "limit": limit,
            },
            request_id=rid,
            trace_id=tid,
        )
    except TaskError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


@router.put("/prompts/{name}")
async def update_prompt(
    name: str,
    request: PromptUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Update a prompt template or rollback to a specific version.
    
    `content` and `rollback_version` are mutually exclusive.
    """
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = _get_prompt_service(session)

    try:
        result = await service.update_template(
            name=name,
            content=request.content,
            description=request.description,
            rollback_version=request.rollback_version,
        )
        return ok_response(
            data=result.model_dump(mode="json"),
            request_id=rid,
            trace_id=tid,
        )
    except TaskError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


@router.get("/prompts/{name}/versions")
async def list_prompt_versions(
    name: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
):
    """List version history for a prompt template."""
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = _get_prompt_service(session)

    try:
        result = await service.get_versions(
            name=name,
            offset=offset,
            limit=limit,
        )
        return ok_response(
            data=result.model_dump(mode="json"),
            request_id=rid,
            trace_id=tid,
        )
    except TaskError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


@router.post("/prompts/{name}/reset")
async def reset_prompt(
    name: str,
    session: AsyncSession = Depends(get_db_session),
):
    """Reset a prompt template to its baseline version from prompts/ directory."""
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = _get_prompt_service(session)

    try:
        result = await service.reset_template(name)
        return ok_response(
            data=result.model_dump(mode="json"),
            request_id=rid,
            trace_id=tid,
        )
    except TaskError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)
