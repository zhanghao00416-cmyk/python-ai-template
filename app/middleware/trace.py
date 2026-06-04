from __future__ import annotations

import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import trace_id_var, request_id_var, user_id_var, session_id_var

logger = structlog.get_logger("middleware.trace")


class TraceMiddleware:
    """Inject trace_id / request_id / user_id / session_id from request headers
    into contextvars and structlog contextvars. Add X-Request-Id to response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers_list = scope.get("headers", [])
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in headers_list}

        trace_id = headers.get("x-trace-id", "") or str(uuid.uuid4())
        request_id = headers.get("x-request-id", "") or str(uuid.uuid4())
        user_id = headers.get("x-user-id", "")
        session_id = headers.get("x-session-id", "")

        trace_id_var.set(trace_id)
        request_id_var.set(request_id)
        user_id_var.set(user_id)
        session_id_var.set(session_id)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
        )

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                headers.append((b"x-trace-id", trace_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            trace_id_var.set("")
            request_id_var.set("")
            user_id_var.set("")
            session_id_var.set("")
            structlog.contextvars.clear_contextvars()