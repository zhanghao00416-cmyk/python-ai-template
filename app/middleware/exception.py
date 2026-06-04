from __future__ import annotations

import json

import structlog
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.errors import (
    AppError,
    ErrorCode,
    ERROR_HTTP_STATUS,
    format_error_code,
)
from app.core.context import get_request_id, get_trace_id
from app.core.response import error_response, validation_error_response

logger = structlog.get_logger("middleware.exception")


async def exception_handler_middleware(request: Request, call_next):
    """Starlette-style middleware that catches exceptions and returns structured JSON.

    - AppError -> structured JSON with integer code, message, request_id, trace_id
    - ValidationError (Pydantic) passed through as 422 (FastAPI handles natively)
    - json.JSONDecodeError -> 400 with code 0005
    - Any other unhandled exception -> 500 with code 0001 (AI_0001)

    Reads trace_id/request_id from contextvars (set by TraceMiddleware).
    """
    try:
        response = await call_next(request)
        return response
    except AppError as exc:
        request_id = get_request_id() or str(request.headers.get("x-request-id", ""))
        trace_id = get_trace_id() or str(request.headers.get("x-trace-id", ""))
        status_code = ERROR_HTTP_STATUS.get(exc.code, 500)
        body = error_response(exc, request_id=request_id, trace_id=trace_id)
        logger.error(
            "app_error",
            code=exc.code,
            sse_code=format_error_code(exc.code),
            message=exc.message,
            request_id=request_id,
            trace_id=trace_id,
        )
        return JSONResponse(status_code=status_code, content=body)

    except ValidationError:
        raise

    except json.JSONDecodeError:
        request_id = get_request_id() or str(request.headers.get("x-request-id", ""))
        trace_id = get_trace_id() or str(request.headers.get("x-trace-id", ""))
        body = validation_error_response(
            "Request body is not valid JSON",
            request_id=request_id,
            trace_id=trace_id,
        )
        logger.error("json_decode_error", request_id=request_id, trace_id=trace_id)
        return JSONResponse(status_code=400, content=body)

    except Exception as exc:
        request_id = get_request_id() or str(request.headers.get("x-request-id", ""))
        trace_id = get_trace_id() or str(request.headers.get("x-trace-id", ""))
        logger.exception(
            "unhandled_error",
            error=str(exc),
            request_id=request_id,
            trace_id=trace_id,
        )
        body = {
            "code": ErrorCode.INTERNAL_ERROR,
            "message": "Internal server error",
            "request_id": request_id,
            "trace_id": trace_id,
        }
        return JSONResponse(status_code=500, content=body)