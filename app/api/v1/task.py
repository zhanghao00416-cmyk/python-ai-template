from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.constants import API_PREFIX
from app.core.context import request_id_var, trace_id_var
from app.core.errors import ErrorCode, TaskError, make_error
from app.core.response import ok_response, error_response, error_to_status
from app.api.deps import get_db_session, get_task_service
from app.domain.task.service import TaskService
from app.schemas.task import TaskCreateRequest

router = APIRouter(prefix=API_PREFIX, tags=["tasks"])


@router.post("/tasks")
async def create_task(
    request: TaskCreateRequest,
    session=Depends(get_db_session),
):
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = get_task_service(session)

    try:
        result = await service.submit_task(
            task_type=request.task_type.value,
            input_data=request.input_data,
            callback_url=request.callback_url,
            metadata=request.metadata,
        )
        await session.commit()
        return ok_response(data=result.model_dump(mode="json"), request_id=rid, trace_id=tid)
    except TaskError as exc:
        await session.rollback()
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        await session.rollback()
        err = make_error(ErrorCode.TASK_SUBMIT_FAILED, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    session=Depends(get_db_session),
):
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = get_task_service(session)

    try:
        result = await service.get_task(task_id)
        return ok_response(data=result.model_dump(mode="json"), request_id=rid, trace_id=tid)
    except TaskError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)


@router.get("/tasks")
async def list_tasks(
    task_type: str | None = Query(None, description="Filter by task type"),
    status: str | None = Query(None, description="Filter by status"),
    user_id: str | None = Query(None, description="Filter by user ID"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session=Depends(get_db_session),
):
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = get_task_service(session)

    try:
        items, total = await service.list_tasks(
            task_type=task_type,
            status=status,
            user_id=user_id,
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
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)