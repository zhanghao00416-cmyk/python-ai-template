from __future__ import annotations

import logging
import re
from typing import Any

import structlog

from app.core.context import get_trace_id, get_request_id, get_user_id


_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(secret|password|token|key|auth|credential)", re.IGNORECASE
)

_REDACTED = "***REDACTED***"


def _redact_sensitive(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if _SENSITIVE_KEY_PATTERNS.search(key):
            event_dict[key] = _REDACTED
    return event_dict


def _inject_context(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.setdefault("trace_id", get_trace_id())
    event_dict.setdefault("request_id", get_request_id())
    event_dict.setdefault("user_id", get_user_id())
    return event_dict


def setup_logging(level: str = "INFO", log_format: str = "json") -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        _inject_context,
        _redact_sensitive,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(format="%(message)s", stream=None, level=getattr(logging, level.upper(), logging.INFO))

    stdlib_logger = logging.getLogger()
    stdlib_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)