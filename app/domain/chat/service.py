from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import structlog

from app.core.errors import AppError, ErrorCode, SystemError
from app.domain.session.service import SessionService
from app.schemas.chat import ChatRequest, ChatResponseData, ChatUsage
from app.schemas.llm import LLMRequest, Message as LLMMessage
from app.schemas.session import (
    MessageCreateRequest,
    MessageDetail,
    SessionCreateRequest,
    SessionRole,
)
from app.services.context_manager import ContextManager
from app.services.llm.gateway import LLMGateway
from app.services.sse_stream import SSEStreamService, wrap_with_heartbeat

logger = structlog.get_logger("domain.chat.service")


class ChatDomainService:
    """Domain service for chat conversations.

    Orchestrates: session management -> context window assembly -> LLM call -> SSE stream.
    """

    def __init__(
        self,
        session_service: SessionService,
        context_manager: ContextManager,
        llm_gateway: LLMGateway,
    ) -> None:
        self._session_service = session_service
        self._context_manager = context_manager
        self._llm_gateway = llm_gateway

    async def chat_stream(
        self,
        request: ChatRequest,
        is_disconnected: Any | None = None,
    ) -> AsyncGenerator[str, None]:
        """Handle streaming chat request via SSE."""
        sse = SSEStreamService(
            intent="chat",
            user_id=request.user_id,
            session_id=request.session_id,
            is_disconnected=is_disconnected,
        )

        try:
            session_id = UUID(request.session_id)
        except ValueError:
            async for event in sse.safe_start_then_error(
                ErrorCode.VALIDATION_ERROR, "Invalid session_id format"
            ):
                yield event
            return

        # Ensure session exists (auto-create)
        try:
            await self._session_service.get_session(session_id)
        except SystemError:
            create_req = SessionCreateRequest(
                user_id=request.user_id,
                title=request.title,
                model_settings=request.model_settings,
                metadata=request.metadata,
            )
            await self._session_service.create_session(create_req)
            logger.info("chat.session_auto_created", session_id=str(session_id), user_id=request.user_id)

        # Store user message
        user_msg_req = MessageCreateRequest(
            session_id=session_id,
            role=SessionRole.USER,
            content=request.query,
            model_name=request.model_override,
            metadata=request.metadata,
        )
        await self._session_service.add_message(user_msg_req)

        # Build context window
        messages_resp = await self._session_service.get_messages(session_id, limit=100, offset=0)
        context_result = await self._context_manager.get_context_window(
            session_id=session_id,
            messages=messages_resp.items,
            max_tokens=request.max_tokens,
        )

        # Build LLM messages
        llm_messages: list[LLMMessage] = []
        if context_result.system_prompt:
            llm_messages.append(LLMMessage(role="system", content=context_result.system_prompt))
        if context_result.summary:
            llm_messages.append(LLMMessage(role="system", content=context_result.summary))
        for msg in context_result.messages:
            llm_messages.append(LLMMessage(role=msg.role, content=msg.content or ""))

        llm_request = LLMRequest(
            messages=llm_messages,
            model=request.model_override,
            task_type="chat",
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
            metadata=request.metadata,
        )

        # Stream start
        async for event in sse.start():
            yield event

        assistant_content = ""
        input_tokens = 0
        output_tokens = 0
        model_used = request.model_override or "default"

        try:
            stream_iter = await self._llm_gateway.generate_stream(llm_request)
            async for chunk in stream_iter:
                if chunk.content:
                    assistant_content += chunk.content
                    async for event in sse.chunk(chunk.content):
                        yield event
                if chunk.input_tokens is not None:
                    input_tokens = chunk.input_tokens
                if chunk.output_tokens is not None:
                    output_tokens = chunk.output_tokens
                if chunk.finish_reason:
                    break
        except AppError as exc:
            logger.error("chat.llm_stream_failed", error=str(exc), session_id=str(session_id))
            async for event in sse.error(exc.code, exc.message):
                yield event
            async for event in sse.done():
                yield event
            return
        except Exception as exc:
            logger.error("chat.llm_stream_failed", error=str(exc), session_id=str(session_id))
            async for event in sse.error(ErrorCode.SERVICE_UNAVAILABLE, "LLM stream failed"):
                yield event
            async for event in sse.done():
                yield event
            return

        # Store assistant message
        if assistant_content:
            assistant_msg_req = MessageCreateRequest(
                session_id=session_id,
                role=SessionRole.ASSISTANT,
                content=assistant_content,
                model_name=model_used,
                metadata=request.metadata,
            )
            await self._session_service.add_message(assistant_msg_req)

        # Usage event
        async for event in sse.usage(
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or max(1, len(assistant_content) // 4),
            model=model_used,
        ):
            yield event

        # Done
        async for event in sse.done():
            yield event

    async def chat_sync(self, request: ChatRequest) -> ChatResponseData:
        """Handle synchronous chat request (stream=false)."""
        try:
            session_id = UUID(request.session_id)
        except ValueError:
            raise SystemError(ErrorCode.VALIDATION_ERROR, "Invalid session_id format")

        # Ensure session exists (auto-create)
        try:
            await self._session_service.get_session(session_id)
        except SystemError:
            create_req = SessionCreateRequest(
                user_id=request.user_id,
                title=request.title,
                model_settings=request.model_settings,
                metadata=request.metadata,
            )
            await self._session_service.create_session(create_req)
            logger.info("chat.session_auto_created", session_id=str(session_id), user_id=request.user_id)

        # Store user message
        user_msg_req = MessageCreateRequest(
            session_id=session_id,
            role=SessionRole.USER,
            content=request.query,
            model_name=request.model_override,
            metadata=request.metadata,
        )
        await self._session_service.add_message(user_msg_req)

        # Build context window
        messages_resp = await self._session_service.get_messages(session_id, limit=100, offset=0)
        context_result = await self._context_manager.get_context_window(
            session_id=session_id,
            messages=messages_resp.items,
            max_tokens=request.max_tokens,
        )

        # Build LLM messages
        llm_messages: list[LLMMessage] = []
        if context_result.system_prompt:
            llm_messages.append(LLMMessage(role="system", content=context_result.system_prompt))
        if context_result.summary:
            llm_messages.append(LLMMessage(role="system", content=context_result.summary))
        for msg in context_result.messages:
            llm_messages.append(LLMMessage(role=msg.role, content=msg.content or ""))

        llm_request = LLMRequest(
            messages=llm_messages,
            model=request.model_override,
            task_type="chat",
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=False,
            metadata=request.metadata,
        )

        try:
            llm_response = await self._llm_gateway.generate(llm_request)
        except AppError:
            raise
        except Exception as exc:
            logger.error("chat.llm_sync_failed", error=str(exc), session_id=str(session_id))
            raise SystemError(ErrorCode.SERVICE_UNAVAILABLE, "LLM call failed") from exc

        # Store assistant message
        assistant_msg_req = MessageCreateRequest(
            session_id=session_id,
            role=SessionRole.ASSISTANT,
            content=llm_response.content,
            model_name=llm_response.model or request.model_override,
            metadata=request.metadata,
        )
        await self._session_service.add_message(assistant_msg_req)

        return ChatResponseData(
            content=llm_response.content,
            citations=[],
            usage=ChatUsage(
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                model=llm_response.model or request.model_override or "default",
            ),
        )
