from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Request

from app.core.constants import API_PREFIX
from app.core.response import ok_response
from app.core.context import request_id_var, trace_id_var, user_id_var, session_id_var

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

    from app.bootstrap import get_uptime
    from app.core.constants import APP_VERSION
    from app.services.health_service import check_database, check_redis, check_qdrant

    db_detail = await check_database()
    redis_detail = await check_redis()
    qdrant_detail = await check_qdrant()

    db_status = db_detail["status"]
    redis_status = redis_detail["status"]
    qdrant_status = qdrant_detail["status"]

    if db_status == "error":
        overall = "error"
    elif redis_status == "degraded" or qdrant_status == "degraded":
        overall = "degraded"
    else:
        overall = "ok"

    data = {
        "status": overall,
        "version": APP_VERSION,
        "uptime": get_uptime(),
        "dependencies": {
            "database": db_detail,
            "redis": redis_detail,
            "qdrant": qdrant_detail,
        },
    }

    return ok_response(data=data, request_id=rid, trace_id=tid)