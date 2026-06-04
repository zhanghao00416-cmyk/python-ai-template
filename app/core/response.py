from __future__ import annotations

from typing import Any

from app.core.errors import AppError, ERROR_HTTP_STATUS, ErrorCode


def ok_response(data: Any = None, *, request_id: str = "", trace_id: str = "") -> dict[str, Any]:
    return {
        "code": 0,
        "message": "ok",
        "request_id": request_id,
        "trace_id": trace_id,
        "data": data,
    }


def error_response(
    error: AppError,
    *,
    request_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": error.code,
        "message": error.message,
        "request_id": request_id,
        "trace_id": trace_id,
    }
    if error.detail is not None:
        result["detail"] = error.detail
    return result


def error_to_status(error: AppError) -> int:
    return ERROR_HTTP_STATUS.get(error.code, 500)


def validation_error_response(
    message: str,
    *,
    request_id: str = "",
    trace_id: str = "",
    detail: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": ErrorCode.VALIDATION_ERROR,
        "message": message,
        "request_id": request_id,
        "trace_id": trace_id,
    }
    if detail is not None:
        result["detail"] = detail
    return result