"""Application errors.

Canonical formats (see docs/01-architecture/ERROR_CODE.md):
- REST JSON ``code``: int (e.g. 2003; success is 0)
- SSE error event ``code``: str ``AI_%04d`` (e.g. ``AI_2003``)
- ``AppError.code``: int, same as REST
"""

from __future__ import annotations

from enum import IntEnum


def format_error_code(code: int) -> str:
    """Format integer code for SSE/logs (2003 -> 'AI_2003')."""
    return f"AI_{code:04d}"


def parse_error_code(value: str | int) -> int:
    """Parse REST/SSE code to integer ('AI_2003' or 2003 -> 2003)."""
    if isinstance(value, int):
        return value
    s = value.strip().upper()
    if s.startswith("AI_"):
        s = s[3:]
    return int(s)


ERROR_CODE_INTERNAL = 1
ERROR_CODE_CONFIG = 2
ERROR_CODE_SERVICE_UNAVAILABLE = 3
ERROR_CODE_TIMEOUT = 4
ERROR_CODE_VALIDATION = 5
ERROR_CODE_RATE_LIMITED = 6
ERROR_CODE_DEPENDENCY = 7


class ErrorCode(IntEnum):
    INTERNAL_ERROR = ERROR_CODE_INTERNAL
    CONFIG_ERROR = ERROR_CODE_CONFIG
    SERVICE_UNAVAILABLE = ERROR_CODE_SERVICE_UNAVAILABLE
    TIMEOUT_ERROR = ERROR_CODE_TIMEOUT
    VALIDATION_ERROR = ERROR_CODE_VALIDATION
    RATE_LIMITED = ERROR_CODE_RATE_LIMITED
    DEPENDENCY_ERROR = ERROR_CODE_DEPENDENCY


class AppError(Exception):
    def __init__(self, code: int, message: str, *, detail: str | None = None) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


class SystemError(AppError):
    pass


class AuthError(AppError):
    pass


class IntentError(AppError):
    pass


class RAGError(AppError):
    pass


class VisionError(AppError):
    pass


class VideoError(AppError):
    pass


class KnowledgeError(AppError):
    pass


class AgentError(AppError):
    pass


class WorkflowError(AppError):
    pass


class TaskError(AppError):
    pass


ERROR_HTTP_STATUS: dict[int, int] = {
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.CONFIG_ERROR: 500,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.TIMEOUT_ERROR: 504,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.DEPENDENCY_ERROR: 502,
}