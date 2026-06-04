from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.core.errors import ErrorCode, format_error_code
from app.services.sse_stream import SSEStreamService, wrap_with_heartbeat
import json


class TestSSEStreamServiceBasic:
    def _make_sse(
        self,
        intent: str = "chat",
        user_id: str = "user-1",
        session_id: str = "sess-1",
        is_disconnected=None,
    ):
        return SSEStreamService(
            intent=intent,
            user_id=user_id,
            session_id=session_id,
            is_disconnected=is_disconnected,
        )

    def _parse_events(self, output: list[str]) -> list[dict]:
        events = []
        for chunk in output:
            lines = chunk.strip().split("\n")
            for line in lines:
                if line.startswith("data: "):
                    data_str = line[len("data: "):]
                    events.append(json.loads(data_str))
        return events

    @pytest.mark.asyncio
    async def test_start_event(self):
        sse = self._make_sse(intent="qa", user_id="u1", session_id="s1")
        result = []
        async for event in sse.start():
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 1
        assert events[0]["type"] == "start"
        assert events[0]["intent"] == "qa"
        assert events[0]["user_id"] == "u1"
        assert events[0]["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_chunk_event(self):
        sse = self._make_sse()
        async for _ in sse.start():
            pass
        result = []
        async for event in sse.chunk("hello"):
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 1
        assert events[0]["type"] == "chunk"
        assert events[0]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_intent_event(self):
        sse = self._make_sse()
        result = []
        async for event in sse.intent("qa", confidence=0.95, layer_used="keyword"):
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 1
        assert events[0]["type"] == "intent"
        assert events[0]["intent"] == "qa"
        assert events[0]["confidence"] == 0.95
        assert events[0]["layer_used"] == "keyword"

    @pytest.mark.asyncio
    async def test_citation_event(self):
        sse = self._make_sse()
        sources = [{"filename": "doc.md", "chunk_text": "text", "score": 0.9}]
        result = []
        async for event in sse.citation(sources):
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 1
        assert events[0]["type"] == "citation"
        assert events[0]["sources"] == sources

    @pytest.mark.asyncio
    async def test_citation_empty_sources_skipped(self):
        sse = self._make_sse()
        result = []
        async for event in sse.citation([]):
            result.append(event)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_heartbeat_event(self):
        sse = self._make_sse()
        result = []
        async for event in sse.heartbeat():
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 1
        assert events[0]["type"] == "heartbeat"
        assert "ts" in events[0]

    @pytest.mark.asyncio
    async def test_progress_event(self):
        sse = self._make_sse()
        result = []
        async for event in sse.progress(current=2, total=5, node="rag_search"):
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 1
        assert events[0]["type"] == "progress"
        assert events[0]["current"] == 2
        assert events[0]["total"] == 5
        assert events[0]["node"] == "rag_search"

    @pytest.mark.asyncio
    async def test_progress_event_without_node(self):
        sse = self._make_sse()
        result = []
        async for event in sse.progress(current=1, total=3):
            result.append(event)
        events = self._parse_events(result)
        assert events[0]["type"] == "progress"
        assert "node" not in events[0]

    @pytest.mark.asyncio
    async def test_usage_event(self):
        sse = self._make_sse()
        result = []
        async for event in sse.usage(input_tokens=150, output_tokens=300, model="qwen-plus"):
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 1
        assert events[0]["type"] == "usage"
        assert events[0]["input_tokens"] == 150
        assert events[0]["output_tokens"] == 300
        assert events[0]["model"] == "qwen-plus"

    @pytest.mark.asyncio
    async def test_done_event(self):
        sse = self._make_sse()
        result = []
        async for event in sse.done():
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 1
        assert events[0]["type"] == "done"
        assert events[0]["reason"] == "complete"

    @pytest.mark.asyncio
    async def test_error_event_integer_code(self):
        sse = self._make_sse()
        result = []
        async for event in sse.error(code=ErrorCode.INTENT_TIMEOUT, message="Intent timed out"):
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert events[0]["code"] == "AI_2003"
        assert events[0]["message"] == "Intent timed out"

    @pytest.mark.asyncio
    async def test_error_event_uses_format_error_code(self):
        sse = self._make_sse()
        result = []
        async for event in sse.error(code=ErrorCode.QDRANT_UNAVAILABLE, message="Qdrant down"):
            result.append(event)
        events = self._parse_events(result)
        assert events[0]["code"] == "AI_1202"

    @pytest.mark.asyncio
    async def test_structured_event(self):
        sse = self._make_sse()
        data = {"key": "value", "count": 42}
        result = []
        async for event in sse.structured(data, user_id="u2", session_id="s2"):
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 1
        assert events[0]["type"] == "structured"
        assert events[0]["data"] == data
        assert events[0]["user_id"] == "u2"
        assert events[0]["session_id"] == "s2"

    @pytest.mark.asyncio
    async def test_structured_event_optional_fields(self):
        sse = self._make_sse()
        result = []
        async for event in sse.structured(data={"x": 1}):
            result.append(event)
        events = self._parse_events(result)
        assert "user_id" not in events[0]
        assert "session_id" not in events[0]


class TestSSEStreamServiceDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_detect_sync_callback(self):
        sse = SSEStreamService(
            intent="chat",
            user_id="u1",
            session_id="s1",
            is_disconnected=lambda: True,
        )
        with pytest.raises(asyncio.CancelledError):
            async for _ in sse.start():
                pass

    @pytest.mark.asyncio
    async def test_disconnect_detect_async_callback(self):
        async def check():
            return True

        sse = SSEStreamService(
            intent="chat",
            user_id="u1",
            session_id="s1",
            is_disconnected=check,
        )
        with pytest.raises(asyncio.CancelledError):
            async for _ in sse.start():
                pass

    @pytest.mark.asyncio
    async def test_no_disconnect_by_default(self):
        sse = SSEStreamService(
            intent="chat",
            user_id="u1",
            session_id="s1",
        )
        result = []
        async for event in sse.start():
            result.append(event)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_disconnect_mid_stream(self):
        call_count = 0

        def disconnect_after_first():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        sse = SSEStreamService(
            intent="chat",
            user_id="u1",
            session_id="s1",
            is_disconnected=disconnect_after_first,
        )
        result = []
        async for event in sse.start():
            result.append(event)
        assert len(result) == 1

        with pytest.raises(asyncio.CancelledError):
            async for _ in sse.chunk("should fail"):
                pass


class TestSSEStreamServiceStartThenError:
    @pytest.mark.asyncio
    async def test_safe_start_then_error_when_not_started(self):
        sse = SSEStreamService(intent="chat", user_id="u1", session_id="s1")
        result = []
        async for event in sse.safe_start_then_error(
            code=ErrorCode.MODEL_TIMEOUT, message="Model timed out"
        ):
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 3
        assert events[0]["type"] == "start"
        assert events[1]["type"] == "error"
        assert events[1]["code"] == "AI_1101"
        assert events[2]["type"] == "done"

    @pytest.mark.asyncio
    async def test_safe_start_then_error_when_already_started(self):
        sse = SSEStreamService(intent="chat", user_id="u1", session_id="s1")
        async for _ in sse.start():
            pass
        result = []
        async for event in sse.safe_start_then_error(
            code=ErrorCode.CLOUD_MODEL_ERROR, message="Cloud model failed"
        ):
            result.append(event)
        events = self._parse_events(result)
        assert len(events) == 2
        assert events[0]["type"] == "error"
        assert events[0]["code"] == "AI_1104"
        assert events[1]["type"] == "done"

    def _parse_events(self, output: list[str]) -> list[dict]:
        events = []
        for chunk in output:
            lines = chunk.strip().split("\n")
            for line in lines:
                if line.startswith("data: "):
                    data_str = line[len("data: "):]
                    events.append(json.loads(data_str))
        return events


class TestSSEStreamServiceProperties:
    def test_user_id_property(self):
        sse = SSEStreamService(intent="chat", user_id="user-123", session_id="sess-456")
        assert sse.user_id == "user-123"

    def test_session_id_property(self):
        sse = SSEStreamService(intent="chat", user_id="user-123", session_id="sess-456")
        assert sse.session_id == "sess-456"


class TestSSEStreamEventFormat:
    def _parse_events(self, output: list[str]) -> list[dict]:
        events = []
        for chunk in output:
            lines = chunk.strip().split("\n")
            for line in lines:
                if line.startswith("data: "):
                    data_str = line[len("data: "):]
                    events.append(json.loads(data_str))
        return events

    @pytest.mark.asyncio
    async def test_event_format_is_sse(self):
        sse = SSEStreamService(intent="chat", user_id="u1", session_id="s1")
        result = []
        async for event in sse.start():
            result.append(event)
        assert len(result) == 1
        assert result[0].startswith("data: ")
        assert result[0].endswith("\n\n")

    @pytest.mark.asyncio
    async def test_full_chat_stream(self):
        sse = SSEStreamService(intent="chat", user_id="u1", session_id="s1")
        events_raw = []

        async for e in sse.start():
            events_raw.append(e)
        async for e in sse.chunk("Hello"):
            events_raw.append(e)
        async for e in sse.chunk(" world"):
            events_raw.append(e)
        async for e in sse.usage(input_tokens=10, output_tokens=20, model="qwen-plus"):
            events_raw.append(e)
        async for e in sse.done():
            events_raw.append(e)

        events = self._parse_events(events_raw)
        assert len(events) == 5
        assert events[0]["type"] == "start"
        assert events[1]["type"] == "chunk"
        assert events[2]["type"] == "chunk"
        assert events[3]["type"] == "usage"
        assert events[4]["type"] == "done"

    @pytest.mark.asyncio
    async def test_full_orchestrated_stream(self):
        sse = SSEStreamService(intent="qa", user_id="u1", session_id="s1")
        events_raw = []

        async for e in sse.start():
            events_raw.append(e)
        async for e in sse.intent("qa", confidence=0.92, layer_used="similarity"):
            events_raw.append(e)
        async for e in sse.citation([{"filename": "a.md", "score": 0.9}]):
            events_raw.append(e)
        async for e in sse.chunk("Answer"):
            events_raw.append(e)
        async for e in sse.usage(input_tokens=100, output_tokens=200, model="qwen-plus"):
            events_raw.append(e)
        async for e in sse.done():
            events_raw.append(e)

        events = self._parse_events(events_raw)
        assert len(events) == 6
        type_seq = [e["type"] for e in events]
        assert type_seq == ["start", "intent", "citation", "chunk", "usage", "done"]


class TestSSEStreamServiceErrorCodeFormats:
    @pytest.mark.asyncio
    async def test_error_code_all_domains(self):
        """Verify error codes from different domains produce correct AI_xxxx format."""
        test_cases = [
            (ErrorCode.INTERNAL_ERROR, "AI_0001"),
            (ErrorCode.AUTH_INVALID_KEY, "AI_1001"),
            (ErrorCode.MODEL_TIMEOUT, "AI_1101"),
            (ErrorCode.QDRANT_UNAVAILABLE, "AI_1202"),
            (ErrorCode.INTENT_CLASSIFY_FAILED, "AI_2001"),
            (ErrorCode.RAG_COLLECTION_NOT_FOUND, "AI_3001"),
            (ErrorCode.MULTIMODAL_INVALID_INPUT, "AI_4001"),
            (ErrorCode.KB_UPLOAD_FAILED, "AI_6001"),
            (ErrorCode.AGENT_STATE_INVALID, "AI_7001"),
            (ErrorCode.WORKFLOW_NODE_NOT_FOUND, "AI_8001"),
            (ErrorCode.TASK_NOT_FOUND, "AI_9001"),
            (ErrorCode.SSE_CONNECTION_LOST, "AI_9007"),
        ]
        for code, expected_sse_code in test_cases:
            assert format_error_code(code) == expected_sse_code

    @pytest.mark.asyncio
    async def test_error_event_with_various_codes(self):
        sse = SSEStreamService(intent="chat", user_id="u1", session_id="s1")
        codes = [
            ErrorCode.MODEL_TIMEOUT,
            ErrorCode.KB_VECTOR_WRITE_FAILED,
            ErrorCode.INTENT_UNKNOWN,
        ]
        for code in codes:
            result = []
            async for event in sse.error(code=code, message="test"):
                result.append(event)
            events = self._parse_events(result)
            assert events[0]["type"] == "error"
            assert events[0]["code"] == format_error_code(code)

    def _parse_events(self, output: list[str]) -> list[dict]:
        events = []
        for chunk in output:
            lines = chunk.strip().split("\n")
            for line in lines:
                if line.startswith("data: "):
                    data_str = line[len("data: "):]
                    events.append(json.loads(data_str))
        return events


class TestWrapWithHeartbeat:
    @pytest.mark.asyncio
    async def test_wrap_with_heartbeat_no_idle(self):
        """Main generator produces events without idle time."""
        sse = SSEStreamService(intent="chat", user_id="u1", session_id="s1")

        async def main_gen():
            yield sse._format_event({"type": "chunk", "content": "hi"})
            yield sse._format_event({"type": "chunk", "content": "there"})

        result = []
        async for event in wrap_with_heartbeat(main_gen(), sse, interval=100.0):
            result.append(event)

        events = []
        for r in result:
            for line in r.strip().split("\n"):
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: "):]))
        assert len(events) == 2
        assert events[0]["type"] == "chunk"
        assert events[1]["type"] == "chunk"

    @pytest.mark.asyncio
    async def test_wrap_with_heartbeat_with_heartbeat_during_idle(self):
        """Heartbeat should be sent when main generator is idle."""
        sse = SSEStreamService(intent="chat", user_id="u1", session_id="s1")

        async def slow_gen():
            yield sse._format_event({"type": "chunk", "content": "first"})
            await asyncio.sleep(0.1)
            yield sse._format_event({"type": "chunk", "content": "second"})

        result = []
        async for event in wrap_with_heartbeat(slow_gen(), sse, interval=0.05):
            result.append(event)

        all_text = "".join(result)
        assert "heartbeat" in all_text or "first" in all_text

    @pytest.mark.asyncio
    async def test_wrap_with_heartbeat_generator_error(self):
        """Errors from main generator should propagate."""
        sse = SSEStreamService(intent="chat", user_id="u1", session_id="s1")

        async def error_gen():
            yield sse._format_event({"type": "chunk", "content": "ok"})
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            async for event in wrap_with_heartbeat(error_gen(), sse, interval=100.0):
                pass


class TestFormatErrorCode:
    def test_format_various_codes(self):
        assert format_error_code(0) == "AI_0000"
        assert format_error_code(1) == "AI_0001"
        assert format_error_code(1202) == "AI_1202"
        assert format_error_code(9007) == "AI_9007"

    def test_parse_various_codes(self):
        from app.core.errors import parse_error_code

        assert parse_error_code("AI_2003") == 2003
        assert parse_error_code("AI_1202") == 1202
        assert parse_error_code(2003) == 2003