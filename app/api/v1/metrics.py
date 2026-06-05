from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.metrics import get_metrics_response

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint (not under /api/v1)."""
    body, content_type = get_metrics_response()
    return PlainTextResponse(content=body.decode(), media_type=content_type)
