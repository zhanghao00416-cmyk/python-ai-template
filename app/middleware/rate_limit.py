"""Rate limiting middleware.

Uses Redis INCR + EXPIRE sliding-window per identifier (API key or IP).
Endpoint-specific overrides supported.
Gracefully degrades when Redis is unavailable.
"""

from __future__ import annotations

import structlog
from starlette.requests import Request  # noqa: TC002
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.context import get_request_id, get_trace_id
from app.core.di import container
from app.core.errors import ErrorCode, get_error_description
from app.infra.redis_client import RedisClient

logger = structlog.get_logger("middleware.rate_limit")

EXEMPT_PATHS = {"/api/v1/health", "/metrics", "/docs", "/openapi.json"}


async def rate_limit_middleware(request: Request, call_next):
    """Check rate limit for the request.

    - Skipped when rate_limit.enabled=false.
    - Skipped for exempt paths.
    - Identifier: API key header if present, else client IP.
    - Endpoint overrides from config take precedence over default.
    - On exceed: 429 with Retry-After / X-RateLimit-* headers.
    - Redis unavailable: log warning and allow through (degraded).
    """
    settings = get_settings()
    path = request.url.path

    if path in EXEMPT_PATHS or any(path.startswith(p) for p in ("/docs", "/openapi")):
        return await call_next(request)

    if not settings.rate_limit.enabled:
        return await call_next(request)

    # Resolve limit config for this path
    endpoint_cfg = settings.rate_limit.endpoints.get(path)
    if endpoint_cfg is not None:
        limit = endpoint_cfg.requests
        window = endpoint_cfg.window_seconds
    else:
        limit = settings.rate_limit.default.requests
        window = settings.rate_limit.default.window_seconds

    # Determine identifier
    api_key = request.headers.get("x-api-key", "")
    if api_key:
        identifier = f"key:{api_key[:16]}"
        error_code = ErrorCode.AUTH_RATE_LIMITED
    else:
        identifier = f"ip:{request.client.host if request.client else 'unknown'}"
        error_code = ErrorCode.RATE_LIMITED

    redis_key = f"rate_limit:{identifier}:{path}"

    try:
        redis_client = container.resolve(RedisClient)
    except KeyError:
        logger.warning("rate_limit.redis_not_registered", path=path)
        return await call_next(request)

    try:
        current = await redis_client.incr(redis_key)
        if current == 1:
            await redis_client.expire(redis_key, window)
    except Exception as exc:
        logger.warning("rate_limit.redis_error", error=str(exc), path=path)
        return await call_next(request)

    remaining = max(0, limit - current)
    if current > limit:
        request_id = get_request_id() or str(request.headers.get("x-request-id", ""))
        trace_id = get_trace_id() or str(request.headers.get("x-trace-id", ""))
        logger.warning(
            "rate_limit.exceeded",
            path=path,
            identifier=identifier.split(":", 1)[0] + ":***",
            current=current,
            limit=limit,
            window=window,
            request_id=request_id,
            trace_id=trace_id,
        )
        body = {
            "code": error_code,
            "message": get_error_description(error_code),
            "request_id": request_id,
            "trace_id": trace_id,
        }
        headers = {
            "Retry-After": str(window),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
        }
        return JSONResponse(status_code=429, headers=headers, content=body)

    # Attach rate limit info to response headers
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response
