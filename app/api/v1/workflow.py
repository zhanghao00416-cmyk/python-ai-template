"""Workflow API routes — thin layer delegating to WorkflowEngine + Registry.

Endpoints:
  POST /api/v1/workflow/run           — execute a workflow (sync mode)
  GET  /api/v1/workflow/runs/{task_id} — get workflow execution result

Dependency: app/workflow/registry.py + app/workflow/engine.py (via DI)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.constants import API_PREFIX
from app.core.context import request_id_var, trace_id_var
from app.core.errors import ErrorCode, make_error
from app.core.response import error_response, error_to_status, ok_response
from app.schemas.workflow import (
    WorkflowNodeResult,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowStatusDetail,
)

router = APIRouter(prefix=API_PREFIX, tags=["workflow"])


# ---------------------------------------------------------------------------
# In-memory store for workflow runs (F13 scope; persist in F14+ via task queue)
# ---------------------------------------------------------------------------

_run_store: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/workflow/run")
async def run_workflow(request: WorkflowRunRequest):
    """Execute a workflow DAG (sync mode for F13; SSE in F14+)."""
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    task_id = str(uuid.uuid4())

    from app.workflow.engine import WorkflowEngine
    from app.workflow.registry import get_workflow_registry
    from app.core.config import get_settings

    registry = get_workflow_registry()
    settings = get_settings()
    engine = WorkflowEngine(
        max_concurrent_nodes=settings.workflow.max_concurrent_nodes,
    )

    created_at = datetime.now(timezone.utc).isoformat()

    try:
        graph = registry.get(request.workflow_id)
    except Exception as exc:
        err = make_error(
            ErrorCode.WORKFLOW_NODE_NOT_FOUND,
            f"Workflow '{request.workflow_id}' not found",
        )
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)

    try:
        final_state = await engine.execute(graph, initial_state=dict(request.inputs))
    except Exception as exc:
        from app.core.errors import AppError

        if isinstance(exc, AppError):
            _run_store[task_id] = {
                "task_id": task_id,
                "workflow_id": request.workflow_id,
                "status": "failed",
                "nodes": [],
                "total_duration_ms": 0.0,
                "created_at": created_at,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            }
            return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
        err = make_error(ErrorCode.WORKFLOW_EXECUTION_FAILED, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)

    # Build node results from _node_results in final state
    raw_results = final_state.pop("_node_results", [])
    node_results = [
        WorkflowNodeResult(
            name=r["name"],
            status=r["status"],
            duration_ms=r.get("duration_ms", 0.0),
            output=r.get("output"),
            error=r.get("error"),
        )
        for r in raw_results
    ]

    total_duration = sum(r.duration_ms for r in node_results)
    content = str(final_state.get("content", "")) if "content" in final_state else ""
    completed_at = datetime.now(timezone.utc).isoformat()

    # Determine overall status
    has_failed = any(r.status == "failed" for r in node_results)
    status = "failed" if has_failed else "completed"

    _run_store[task_id] = {
        "task_id": task_id,
        "workflow_id": request.workflow_id,
        "status": status,
        "nodes": [r.model_dump(mode="json") for r in node_results],
        "total_duration_ms": round(total_duration, 2),
        "created_at": created_at,
        "completed_at": completed_at,
    }

    resp = WorkflowRunResponse(
        task_id=task_id,
        workflow_id=request.workflow_id,
        content=content,
        nodes=node_results,
    )
    return ok_response(data=resp.model_dump(mode="json"), request_id=rid, trace_id=tid)


@router.get("/workflow/runs/{task_id}")
async def get_workflow_run(task_id: str):
    """Get workflow execution result by task_id."""
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""

    run_data = _run_store.get(task_id)
    if run_data is None:
        err = make_error(
            ErrorCode.TASK_NOT_FOUND,
            f"Workflow run '{task_id}' not found",
        )
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)

    detail = WorkflowStatusDetail(**run_data)
    return ok_response(data=detail.model_dump(mode="json"), request_id=rid, trace_id=tid)
