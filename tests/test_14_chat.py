from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.errors import ErrorCode, SystemError
from app.domain.chat.service import ChatDomainService
from app.schemas.chat import ChatRequest, ChatResponseData, ChatUsage
from app.schemas.llm import LLMChunk, LLMResponse
from app.schemas.session import (
    ContextWindowResult,
    MessageDetail,
    MessageListResponse,
    SessionDetail,
    SessionRole,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_session_detail(session_id: UUID | None = None, user_id: str = "u1") -> SessionDetail:
    return SessionDetail(
        id=session_id or uuid4(),
        user_id=user_id,
        title="Test Session",
        intent_type=None,
        model_settings=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        metadata=None,
    )


def _make_message_detail(
    content: str = "Hello",
    role: str = "user",
    session_id: UUID | None = None,
) -> MessageDetail:
    return MessageDetail(
        id=uuid4(),
        session_id=session_id or uuid4(),
        role=role,
        content=content,
        token_count=None,
        model_name=None,
        citations=None,
        tool_calls=None,
        tool_results=None,
        created_at=datetime.now(timezone.utc),
        metadata=None,
    )


def _make_context_window_result(
    session_id: UUID,
    messages: list[MessageDetail] | None = None,
) -> ContextWindowResult:
    return ContextWindowResult(
        session_id=session_id,
        system_prompt=None,
        messages=messages or [],
        total_tokens=0,
        truncated=False,
        summary=None,
    )


def _parse_sse_events(output: list[str]) -> list[dict[str, Any]]:
    events = []
    for chunk in output:
        lines = chunk.strip().split("\n")
        for line in lines:
            if line.startswith("data: "):
                data_str = line[len("data: "):]
                events.append(json.loads(data_str))
    return events


# ===========================================================================
# ChatDomainService — chat_stream
# ===========================================================================

class TestChatDomainServiceStream:
    def _make_service(self):
        mock_session_service = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_llm_gateway = AsyncMock()
        service = ChatDomainService(
            session_service=mock_session_service,
            context_manager=mock_context_manager,
            llm_gateway=mock_llm_gateway,
        )
        return service, mock_session_service, mock_context_manager, mock_llm_gateway

    @pytest.mark.asyncio
    async def test_chat_stream_invalid_session_id(self):
        service, _, _, _ = self._make_service()
        request = ChatRequest(
            user_id="u1",
            session_id="not-a-uuid",
            query="Hello",
            stream=True,
        )
        result = []
        async for event in service.chat_stream(request):
            result.append(event)

        events = _parse_sse_events(result)
        assert len(events) == 3
        assert events[0]["type"] == "start"
        assert events[1]["type"] == "error"
        assert events[1]["code"] == "AI_0005"
        assert events[2]["type"] == "done"

    @pytest.mark.asyncio
    async def test_chat_stream_auto_create_session(self):
        service, mock_session_service, mock_context_manager, mock_llm_gateway = self._make_service()
        sid = uuid4()
        mock_session_service.get_session.side_effect = SystemError(
            ErrorCode.VALIDATION_ERROR, "Session not found"
        )
        mock_session_service.create_session.return_value = _make_session_detail(session_id=sid)
        mock_session_service.get_messages.return_value = MessageListResponse(
            items=[], total=0, offset=0, limit=100
        )
        mock_context_manager.get_context_window.return_value = _make_context_window_result(sid)

        async def mock_stream():
            yield LLMChunk(content="Hello")
            yield LLMChunk(content=" world")
            yield LLMChunk(content="", finish_reason="stop")

        mock_llm_gateway.generate_stream.return_value = mock_stream()

        request = ChatRequest(
            user_id="u1",
            session_id=str(sid),
            query="Hello",
            stream=True,
        )
        result = []
        async for event in service.chat_stream(request):
            result.append(event)

        events = _parse_sse_events(result)
        types = [e["type"] for e in events]
        assert "start" in types
        assert "chunk" in types
        assert "usage" in types
        assert "done" in types
        mock_session_service.create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_stream_existing_session(self):
        service, mock_session_service, mock_context_manager, mock_llm_gateway = self._make_service()
        sid = uuid4()
        mock_session_service.get_session.return_value = _make_session_detail(session_id=sid)
        mock_session_service.get_messages.return_value = MessageListResponse(
            items=[_make_message_detail(content="Previous", role="user", session_id=sid)],
            total=1,
            offset=0,
            limit=100,
        )
        mock_context_manager.get_context_window.return_value = _make_context_window_result(
            sid, messages=[_make_message_detail(content="Previous", role="user", session_id=sid)]
        )

        async def mock_stream():
            yield LLMChunk(content="Response")
            yield LLMChunk(content="", finish_reason="stop")

        mock_llm_gateway.generate_stream.return_value = mock_stream()

        request = ChatRequest(
            user_id="u1",
            session_id=str(sid),
            query="Hello",
            stream=True,
        )
        result = []
        async for event in service.chat_stream(request):
            result.append(event)

        events = _parse_sse_events(result)
        types = [e["type"] for e in events]
        assert types.count("chunk") >= 1
        mock_session_service.create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_stream_llm_error(self):
        service, mock_session_service, mock_context_manager, mock_llm_gateway = self._make_service()
        sid = uuid4()
        mock_session_service.get_session.return_value = _make_session_detail(session_id=sid)
        mock_session_service.get_messages.return_value = MessageListResponse(
            items=[], total=0, offset=0, limit=100
        )
        mock_context_manager.get_context_window.return_value = _make_context_window_result(sid)

        async def error_stream():
            raise SystemError(ErrorCode.SERVICE_UNAVAILABLE, "LLM failed")
            yield LLMChunk(content="")  # pragma: no cover

        mock_llm_gateway.generate_stream.return_value = error_stream()

        request = ChatRequest(
            user_id="u1",
            session_id=str(sid),
            query="Hello",
            stream=True,
        )
        result = []
        async for event in service.chat_stream(request):
            result.append(event)

        events = _parse_sse_events(result)
        types = [e["type"] for e in events]
        assert "error" in types
        assert "done" in types

    @pytest.mark.asyncio
    async def test_chat_stream_stores_user_and_assistant_messages(self):
        service, mock_session_service, mock_context_manager, mock_llm_gateway = self._make_service()
        sid = uuid4()
        mock_session_service.get_session.return_value = _make_session_detail(session_id=sid)
        mock_session_service.get_messages.return_value = MessageListResponse(
            items=[], total=0, offset=0, limit=100
        )
        mock_context_manager.get_context_window.return_value = _make_context_window_result(sid)

        async def mock_stream():
            yield LLMChunk(content="Answer")
            yield LLMChunk(content="", finish_reason="stop")

        mock_llm_gateway.generate_stream.return_value = mock_stream()

        request = ChatRequest(
            user_id="u1",
            session_id=str(sid),
            query="Question",
            stream=True,
        )
        result = []
        async for event in service.chat_stream(request):
            result.append(event)

        # Verify user message stored
        calls = mock_session_service.add_message.call_args_list
        assert len(calls) == 2  # user + assistant
        # AsyncMock records positional args when called with object directly
        assert calls[0][0][0].role == SessionRole.USER
        assert calls[0][0][0].content == "Question"
        assert calls[1][0][0].role == SessionRole.ASSISTANT
        assert calls[1][0][0].content == "Answer"


# ===========================================================================
# ChatDomainService — chat_sync
# ===========================================================================

class TestChatDomainServiceSync:
    def _make_service(self):
        mock_session_service = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_llm_gateway = AsyncMock()
        service = ChatDomainService(
            session_service=mock_session_service,
            context_manager=mock_context_manager,
            llm_gateway=mock_llm_gateway,
        )
        return service, mock_session_service, mock_context_manager, mock_llm_gateway

    @pytest.mark.asyncio
    async def test_chat_sync_success(self):
        service, mock_session_service, mock_context_manager, mock_llm_gateway = self._make_service()
        sid = uuid4()
        mock_session_service.get_session.return_value = _make_session_detail(session_id=sid)
        mock_session_service.get_messages.return_value = MessageListResponse(
            items=[], total=0, offset=0, limit=100
        )
        mock_context_manager.get_context_window.return_value = _make_context_window_result(sid)
        mock_llm_gateway.generate.return_value = LLMResponse(
            content="Sync answer",
            model="qwen-plus",
            input_tokens=10,
            output_tokens=5,
        )

        request = ChatRequest(
            user_id="u1",
            session_id=str(sid),
            query="Hello",
            stream=False,
        )
        result = await service.chat_sync(request)

        assert isinstance(result, ChatResponseData)
        assert result.content == "Sync answer"
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 5
        assert result.usage.model == "qwen-plus"

    @pytest.mark.asyncio
    async def test_chat_sync_invalid_session_id(self):
        service, _, _, _ = self._make_service()
        request = ChatRequest(
            user_id="u1",
            session_id="not-a-uuid",
            query="Hello",
            stream=False,
        )
        with pytest.raises(SystemError) as exc_info:
            await service.chat_sync(request)
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_chat_sync_auto_create_session(self):
        service, mock_session_service, mock_context_manager, mock_llm_gateway = self._make_service()
        sid = uuid4()
        mock_session_service.get_session.side_effect = SystemError(
            ErrorCode.VALIDATION_ERROR, "Session not found"
        )
        mock_session_service.create_session.return_value = _make_session_detail(session_id=sid)
        mock_session_service.get_messages.return_value = MessageListResponse(
            items=[], total=0, offset=0, limit=100
        )
        mock_context_manager.get_context_window.return_value = _make_context_window_result(sid)
        mock_llm_gateway.generate.return_value = LLMResponse(
            content="Answer",
            model="default",
            input_tokens=1,
            output_tokens=1,
        )

        request = ChatRequest(
            user_id="u1",
            session_id=str(sid),
            query="Hello",
            stream=False,
        )
        await service.chat_sync(request)
        mock_session_service.create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_sync_llm_error(self):
        service, mock_session_service, mock_context_manager, mock_llm_gateway = self._make_service()
        sid = uuid4()
        mock_session_service.get_session.return_value = _make_session_detail(session_id=sid)
        mock_session_service.get_messages.return_value = MessageListResponse(
            items=[], total=0, offset=0, limit=100
        )
        mock_context_manager.get_context_window.return_value = _make_context_window_result(sid)
        mock_llm_gateway.generate.side_effect = Exception("LLM down")

        request = ChatRequest(
            user_id="u1",
            session_id=str(sid),
            query="Hello",
            stream=False,
        )
        with pytest.raises(SystemError) as exc_info:
            await service.chat_sync(request)
        assert exc_info.value.code == ErrorCode.SERVICE_UNAVAILABLE


# ===========================================================================
# ChatDomainService — context window assembly
# ===========================================================================

class TestChatDomainServiceContextAssembly:
    def _make_service(self):
        mock_session_service = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_llm_gateway = AsyncMock()
        service = ChatDomainService(
            session_service=mock_session_service,
            context_manager=mock_context_manager,
            llm_gateway=mock_llm_gateway,
        )
        return service, mock_session_service, mock_context_manager, mock_llm_gateway

    @pytest.mark.asyncio
    async def test_context_window_passed_to_llm(self):
        service, mock_session_service, mock_context_manager, mock_llm_gateway = self._make_service()
        sid = uuid4()
        mock_session_service.get_session.return_value = _make_session_detail(session_id=sid)

        msg1 = _make_message_detail(content="User msg", role="user", session_id=sid)
        msg2 = _make_message_detail(content="Assistant msg", role="assistant", session_id=sid)
        mock_session_service.get_messages.return_value = MessageListResponse(
            items=[msg1, msg2], total=2, offset=0, limit=100
        )

        ctx_result = ContextWindowResult(
            session_id=sid,
            system_prompt="You are helpful.",
            messages=[msg1, msg2],
            total_tokens=50,
            truncated=False,
            summary="Summary of old messages",
        )
        mock_context_manager.get_context_window.return_value = ctx_result

        async def mock_stream():
            yield LLMChunk(content="Hi")
            yield LLMChunk(content="", finish_reason="stop")

        mock_llm_gateway.generate_stream.return_value = mock_stream()

        request = ChatRequest(
            user_id="u1",
            session_id=str(sid),
            query="Hello",
            stream=True,
            max_tokens=2048,
        )
        result = []
        async for event in service.chat_stream(request):
            result.append(event)

        # Verify context_manager called with correct params
        call_kwargs = mock_context_manager.get_context_window.call_args[1]
        assert call_kwargs["session_id"] == sid
        assert call_kwargs["max_tokens"] == 2048

        # Verify LLM request includes system prompt and summary
        llm_call = mock_llm_gateway.generate_stream.call_args[0][0]
        roles = [m.role for m in llm_call.messages]
        assert "system" in roles


# ===========================================================================
# Chat schemas
# ===========================================================================

class TestChatSchemas:
    def test_chat_request_defaults(self):
        req = ChatRequest(
            user_id="u1",
            session_id=str(uuid4()),
            query="Hello",
        )
        assert req.stream is True
        assert req.temperature == 0.7
        assert req.max_tokens == 4096
        assert req.model_override is None

    def test_chat_request_with_override(self):
        req = ChatRequest(
            user_id="u1",
            session_id=str(uuid4()),
            query="Hello",
            stream=False,
            model_override="qwen-plus",
            temperature=0.5,
            max_tokens=1024,
        )
        assert req.stream is False
        assert req.model_override == "qwen-plus"
        assert req.temperature == 0.5
        assert req.max_tokens == 1024

    def test_chat_response_data(self):
        usage = ChatUsage(input_tokens=10, output_tokens=20, model="qwen-plus")
        data = ChatResponseData(content="Answer", citations=[], usage=usage)
        assert data.content == "Answer"
        assert data.usage.input_tokens == 10

    def test_chat_request_metadata(self):
        req = ChatRequest(
            user_id="u1",
            session_id=str(uuid4()),
            query="Hello",
            metadata={"key": "value"},
        )
        assert req.metadata == {"key": "value"}


# ===========================================================================
# Chat API router — basic structure
# ===========================================================================

class TestChatAPIRouter:
    def test_router_has_prefix(self):
        from app.api.v1.chat import router
        assert router.prefix == "/chat"
        assert "chat" in router.tags

    def test_routes_defined(self):
        from app.api.v1.chat import router
        routes = [r.path for r in router.routes]
        # POST /chat (prefix + "") -> path is "/chat" in FastAPI
        assert any(r == "/chat" or r.endswith("/") for r in routes)
        assert any("sessions/{session_id}" in r for r in routes)
        assert any("sessions/{session_id}/messages" in r for r in routes)
