"""API Key authentication middleware.

Checks X-API-Key header against configured key.
Sets request.state.user_id on success.
Exempts health and metrics endpoints.
"""

from __future__ import annotations

import structlog
from starlette.requests import Request  # noqa: TC002
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.context import get_request_id, get_trace_id
from app.core.errors import ErrorCode, get_error_description

logger = structlog.get_logger("middleware.auth")

EXEMPT_PATHS = {"/api/v1/health", "/metrics", "/docs", "/openapi.json"}


async def auth_middleware(request: Request, call_next):
    """Authenticate request via X-API-Key header.

    - Skipped when enable_auth=false (uses X-User-Id or default).
    - Skipped for exempt paths.
    - Missing/invalid key -> 401 with code 1001.
    - Valid key -> request.state.user_id set and request continues.
    """
    settings = get_settings()
    path = request.url.path

    if path in EXEMPT_PATHS or any(path.startswith(p) for p in ("/docs", "/openapi")):
        return await call_next(request)

    if not settings.security.enable_auth:
        user_id = request.headers.get("x-user-id", "anonymous")
        request.state.user_id = user_id
        return await call_next(request)

    api_key = request.headers.get("x-api-key", "")
    expected_key = settings.security.api_key

    if not expected_key:
        logger.warning("auth.no_key_configured", path=path)
        request.state.user_id = "anonymous"
        return await call_next(request)

    if not api_key or api_key != expected_key:
        request_id = get_request_id() or str(request.headers.get("x-request-id", ""))
        trace_id = get_trace_id() or str(request.headers.get("x-trace-id", ""))
        logger.warning(
            "auth.invalid_key",
            path=path,
            has_key=bool(api_key),
            request_id=request_id,
            trace_id=trace_id,
        )
        body = {
            "code": ErrorCode.AUTH_INVALID_KEY,
            "message": get_error_description(ErrorCode.AUTH_INVALID_KEY),
            "request_id": request_id,
            "trace_id": trace_id,
        }
        return JSONResponse(status_code=401, content=body)

    request.state.user_id = f"key_{api_key[:8]}"
    return await call_next(request)
