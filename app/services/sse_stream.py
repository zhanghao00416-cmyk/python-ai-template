from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

import structlog

from app.core.config import get_settings
from app.core.errors import format_error_code

logger = structlog.get_logger("services.sse_stream")
_DEBUG_CONTENT_LIMIT = 200


class SSEStreamService:
    """SSE stream event formatter with heartbeat and disconnect detection.

    Business domains call semantic methods (start, chunk, citation, etc.)
    and never deal with SSE wire format directly.

    10 event types: start, intent, chunk, structured, citation,
    heartbeat, progress, usage, done, error.
    """

    def __init__(
        self,
        intent: str,
        user_id: str,
        session_id: str,
        is_disconnected: Callable[[], bool] | Callable[[], Any] | None = None,
    ) -> None:
        self._intent = intent
        self._user_id = user_id
        self._session_id = session_id
        self._is_disconnected = is_disconnected or (lambda: False)
        self._started = False

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def session_id(self) -> str:
        return self._session_id

    def _format_event(self, data: dict[str, Any]) -> str:
        self._log_debug_event(data)
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _truncate_debug_content(self, content: str) -> str:
        if len(content) <= _DEBUG_CONTENT_LIMIT:
            return content
        return f"{content[:_DEBUG_CONTENT_LIMIT]}..."

    def _summarize_structured_data(self, data: Any) -> dict[str, Any]:
        if isinstance(data, list):
            return {"kind": "list", "count": len(data)}
        if isinstance(data, dict):
            return {"kind": "dict", "keys": sorted(data.keys())}
        return {"kind": type(data).__name__}

    def _log_debug_event(self, event: dict[str, Any]) -> None:
        settings = get_settings()
        if not settings.server.debug_sse_output:
            return

        event_type = event.get("type")
        if event_type == "heartbeat":
            return

        common = {
            "intent": self._intent,
            "user_id": self._user_id,
            "session_id": self._session_id,
            "event_type": event_type,
        }

        if event_type == "start":
            logger.info("sse_debug_start", **common, event_intent=event.get("intent"))
            return
        if event_type == "chunk":
            logger.info(
                "sse_debug_chunk",
                **common,
                content=self._truncate_debug_content(str(event.get("content", ""))),
            )
            return
        if event_type == "citation":
            sources = event.get("sources") or []
            logger.info(
                "sse_debug_citation",
                **common,
                source_count=len(sources) if isinstance(sources, list) else 0,
            )
            return
        if event_type == "structured":
            logger.info(
                "sse_debug_structured",
                **common,
                data_summary=self._summarize_structured_data(event.get("data")),
            )
            return
        if event_type == "progress":
            logger.info(
                "sse_debug_progress",
                **common,
                current=event.get("current"),
                total=event.get("total"),
                node=event.get("node"),
            )
            return
        if event_type == "intent":
            logger.info(
                "sse_debug_intent",
                **common,
                event_intent=event.get("intent"),
                confidence=event.get("confidence"),
                layer_used=event.get("layer_used"),
            )
            return
        if event_type == "usage":
            logger.info(
                "sse_debug_usage",
                **common,
                input_tokens=event.get("input_tokens"),
                output_tokens=event.get("output_tokens"),
                model=event.get("model"),
            )
            return
        if event_type == "error":
            logger.info(
                "sse_debug_error",
                **common,
                code=event.get("code"),
                message=event.get("message"),
            )
            return
        if event_type == "done":
            logger.info("sse_debug_done", **common)

    async def _check_connection(self) -> None:
        if inspect.iscoroutinefunction(self._is_disconnected):
            is_disconnected = await self._is_disconnected()
        else:
            is_disconnected = self._is_disconnected()

        if is_disconnected:
            logger.warning(
                "sse_client_disconnected",
                intent=self._intent,
                user_id=self._user_id,
                session_id=self._session_id,
            )
            raise asyncio.CancelledError("Client disconnected")

    async def start(self) -> AsyncGenerator[str, None]:
        await self._check_connection()
        self._started = True
        event: dict[str, Any] = {
            "type": "start",
            "intent": self._intent,
            "user_id": self._user_id,
            "session_id": self._session_id,
        }
        yield self._format_event(event)
        logger.debug(
            "sse_start_sent",
            intent=self._intent,
            user_id=self._user_id,
        )

    async def intent(
        self, intent: str, confidence: float, layer_used: str
    ) -> AsyncGenerator[str, None]:
        await self._check_connection()
        event: dict[str, Any] = {
            "type": "intent",
            "intent": intent,
            "confidence": confidence,
            "layer_used": layer_used,
        }
        yield self._format_event(event)

    async def chunk(self, content: str) -> AsyncGenerator[str, None]:
        await self._check_connection()
        event: dict[str, Any] = {"type": "chunk", "content": content}
        yield self._format_event(event)

    async def structured(
        self,
        data: Any,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        await self._check_connection()
        event: dict[str, Any] = {"type": "structured", "data": data}
        if user_id is not None:
            event["user_id"] = user_id
        if session_id is not None:
            event["session_id"] = session_id
        yield self._format_event(event)

    async def citation(
        self, sources: list[dict[str, Any]]
    ) -> AsyncGenerator[str, None]:
        if not sources:
            return
        await self._check_connection()
        event: dict[str, Any] = {"type": "citation", "sources": sources}
        yield self._format_event(event)

    async def heartbeat(self) -> AsyncGenerator[str, None]:
        await self._check_connection()
        event: dict[str, Any] = {"type": "heartbeat", "ts": time.time()}
        yield self._format_event(event)

    async def progress(
        self, current: int, total: int, node: str | None = None
    ) -> AsyncGenerator[str, None]:
        await self._check_connection()
        event: dict[str, Any] = {
            "type": "progress",
            "current": current,
            "total": total,
        }
        if node is not None:
            event["node"] = node
        yield self._format_event(event)

    async def usage(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> AsyncGenerator[str, None]:
        await self._check_connection()
        event: dict[str, Any] = {
            "type": "usage",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": model,
        }
        yield self._format_event(event)

    async def done(self) -> AsyncGenerator[str, None]:
        await self._check_connection()
        event: dict[str, Any] = {"type": "done", "reason": "complete"}
        yield self._format_event(event)
        logger.debug(
            "sse_done_sent",
            intent=self._intent,
            user_id=self._user_id,
        )

    async def error(
        self, code: int, message: str
    ) -> AsyncGenerator[str, None]:
        sse_code = format_error_code(code)
        event: dict[str, Any] = {"type": "error", "code": sse_code, "message": message}
        yield self._format_event(event)

    async def safe_start_then_error(
        self, code: int, message: str
    ) -> AsyncGenerator[str, None]:
        if not self._started:
            start_event: dict[str, Any] = {
                "type": "start",
                "intent": self._intent,
                "user_id": self._user_id,
                "session_id": self._session_id,
            }
            yield self._format_event(start_event)
            self._started = True

        sse_code = format_error_code(code)
        error_event: dict[str, Any] = {
            "type": "error",
            "code": sse_code,
            "message": message,
        }
        yield self._format_event(error_event)

        done_event: dict[str, Any] = {"type": "done", "reason": "complete"}
        yield self._format_event(done_event)
        logger.warning(
            "sse_start_then_error_sent",
            intent=self._intent,
            user_id=self._user_id,
            code=sse_code,
        )


async def wrap_with_heartbeat(
    main_gen: AsyncGenerator[str, None],
    sse: SSEStreamService,
    interval: float | None = None,
) -> AsyncGenerator[str, None]:
    """Merge main event stream with periodic heartbeats.

    Uses a Queue to decouple the main generator from the heartbeat timeout,
    avoiding CancelledError closing the main generator when asyncio.wait_for cancels __anext__().
    """
    if interval is None:
        settings = get_settings()
        interval = float(settings.sse.heartbeat_interval)

    queue: asyncio.Queue[str | BaseException] = asyncio.Queue()
    stop_event = asyncio.Event()

    async def _producer() -> None:
        try:
            async for event in main_gen:
                await queue.put(event)
        except BaseException as exc:
            await queue.put(exc)
        finally:
            stop_event.set()

    producer_task = asyncio.ensure_future(_producer())

    try:
        while not stop_event.is_set() or not queue.empty():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                async for hb in sse.heartbeat():
                    yield hb
                continue

            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        if not producer_task.done():
            producer_task.cancel()
            try:
                await producer_task
            except (asyncio.CancelledError, BaseException):
                pass