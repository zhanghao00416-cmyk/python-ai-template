from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Request

from app.core.constants import API_PREFIX
from app.core.response import ok_response
from app.core.context import request_id_var, trace_id_var, user_id_var, session_id_var
from app.bootstrap import get_health_status

router = APIRouter(prefix=API_PREFIX, tags=["health"])


@router.get("/health")
async def health_check(request: Request) -> dict:
    rid = request_id_var.get() or str(uuid4())
    tid = trace_id_var.get() or request.headers.get("X-Trace-Id", str(uuid4()))
    request_id_var.set(rid)
    trace_id_var.set(tid)

    if uid := request.headers.get("X-User-Id"):
        user_id_var.set(uid)
    if sid := request.headers.get("X-Session-Id"):
        session_id_var.set(sid)

    health = get_health_status()
    return ok_response(data=health, request_id=rid, trace_id=tid)