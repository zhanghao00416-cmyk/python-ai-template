"""Agent API routes — thin layer delegating to domain service.

Endpoints:
  POST /api/v1/agent/run             — execute agent task (sync mode)
  GET  /api/v1/agent/trajectories     — list trajectories by session
  GET  /api/v1/agent/trajectories/{task_id} — trajectory detail

Dependency: app/domain/agent_orchestration/service.py (via deps bridge)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.constants import API_PREFIX
from app.core.context import request_id_var, trace_id_var
from app.core.errors import AgentError, ErrorCode, make_error
from app.core.response import error_response, error_to_status, ok_response
from app.schemas.agent import AgentRunRequest

router = APIRouter(prefix=API_PREFIX, tags=["agent"])


def _get_agent_service(session: AsyncSession):
    """Bridge: create AgentOrchestrationService from DI + DB session."""
    from app.core.di import container
    from app.domain.agent_orchestration.repo import AgentTrajectoryRepo
    from app.domain.agent_orchestration.service import AgentOrchestrationService
    from app.tools.registry import ToolRegistry

    repo = AgentTrajectoryRepo(session=session)
    tool_registry = container.resolve(ToolRegistry)
    return AgentOrchestrationService(repo=repo, tool_registry=tool_registry)


@router.post("/agent/run")
async def run_agent(
    request: AgentRunRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Execute an agent task (sync mode for F11; SSE in F14+)."""
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = _get_agent_service(session)

    try:
        result = await service.run_agent(
            user_id=request.user_id,
            session_id=request.session_id,
            query=request.query,
            agent_type=request.agent_type.value,
            agent_name=request.agent_name,
            tools=request.tools,
            skills=request.skills,
            max_steps=request.max_steps,
            model_override=request.model_override,
            metadata=request.metadata,
        )
        await session.commit()
        return ok_response(
            data=result.model_dump(mode="json"),
            request_id=rid,
            trace_id=tid,
        )
    except AgentError as exc:
        await session.rollback()
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        await session.rollback()
        err = make_error(ErrorCode.AGENT_EXECUTION_FAILED, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


@router.get("/agent/trajectories")
async def list_trajectories(
    session_id: str | None = Query(None, description="Filter by session ID"),
    agent_name: str | None = Query(None, description="Filter by agent name"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    """List agent trajectory summaries."""
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = _get_agent_service(session)

    try:
        items, total = await service.list_trajectories(
            session_id=session_id,
            agent_name=agent_name,
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


@router.get("/agent/trajectories/{task_id}")
async def get_trajectory(
    task_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """Get full trajectory detail by task_id."""
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = _get_agent_service(session)

    try:
        detail = await service.get_trajectory_detail(task_id)
        if detail is None:
            err = make_error(ErrorCode.TASK_NOT_FOUND, f"Trajectory '{task_id}' not found")
            return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)
        return ok_response(
            data=detail.model_dump(mode="json"),
            request_id=rid,
            trace_id=tid,
        )
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)
