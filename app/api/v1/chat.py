from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.di import container
from app.core.errors import SystemError, ErrorCode
from app.domain.chat.service import ChatDomainService
from app.domain.session.repo import SessionRepo, MessageRepo
from app.domain.session.service import SessionService
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    ChatMessagesResponse,
    ChatDeleteResponse,
)
from app.services.context_manager import ContextManager
from app.services.llm.gateway import LLMGateway
from app.services.sse_stream import SSEStreamService, wrap_with_heartbeat

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_chat_service(session: AsyncSession) -> ChatDomainService:
    """Factory to create ChatDomainService with request-scoped DB session."""
    session_repo = SessionRepo(session=session)
    message_repo = MessageRepo(session=session)
    session_service = SessionService(
        session_repo=session_repo,
        message_repo=message_repo,
    )
    context_manager = container.resolve(ContextManager)
    llm_gateway = container.resolve(LLMGateway)
    return ChatDomainService(
        session_service=session_service,
        context_manager=context_manager,
        llm_gateway=llm_gateway,
    )


@router.post("")
async def chat_endpoint(
    request: ChatRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Chat completion endpoint.

    Supports SSE streaming (default) and synchronous JSON response.
    Auto-creates session if session_id does not exist.
    """
    chat_service = _get_chat_service(session)

    if request.stream:
        async def event_generator():
            async for event in chat_service.chat_stream(
                request=request,
                is_disconnected=lambda: http_request.is_disconnected,
            ):
                yield event

        sse = SSEStreamService(
            intent="chat",
            user_id=request.user_id,
            session_id=request.session_id,
            is_disconnected=lambda: http_request.is_disconnected,
        )
        wrapped = wrap_with_heartbeat(event_generator(), sse)
        return StreamingResponse(
            wrapped,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Synchronous mode
    result = await chat_service.chat_sync(request=request)
    return ChatResponse(data=result)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionResponse:
    """Get session details."""
    session_service = SessionService(
        session_repo=SessionRepo(session=session),
        message_repo=MessageRepo(session=session),
    )
    try:
        session = await session_service.get_session(session_id)
    except SystemError as exc:
        raise SystemError(ErrorCode.VALIDATION_ERROR, f"Session {session_id} not found") from exc

    return ChatSessionResponse(
        data={
            "id": str(session.id),
            "user_id": session.user_id,
            "title": session.title,
            "intent_type": session.intent_type,
            "model_config": session.model_settings,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            "metadata": session.metadata,
        }
    )


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: UUID,
    limit: int = 20,
    offset: int = 0,
    role: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> ChatMessagesResponse:
    """List messages for a session."""
    session_service = SessionService(
        session_repo=SessionRepo(session=session),
        message_repo=MessageRepo(session=session),
    )
    messages = await session_service.get_messages(
        session_id=session_id,
        limit=limit,
        offset=offset,
        role=role,
    )

    return ChatMessagesResponse(
        data={
            "items": [
                {
                    "id": str(m.id),
                    "session_id": str(m.session_id),
                    "role": m.role,
                    "content": m.content,
                    "token_count": m.token_count,
                    "model_name": m.model_name,
                    "citations": m.citations,
                    "tool_calls": m.tool_calls,
                    "tool_results": m.tool_results,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "metadata": m.metadata,
                }
                for m in messages.items
            ],
            "total": messages.total,
            "offset": messages.offset,
            "limit": messages.limit,
        }
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> ChatDeleteResponse:
    """Soft-delete a session and cascade to messages."""
    session_service = SessionService(
        session_repo=SessionRepo(session=session),
        message_repo=MessageRepo(session=session),
    )
    try:
        await session_service.get_session(session_id)
    except SystemError as exc:
        raise SystemError(ErrorCode.VALIDATION_ERROR, f"Session {session_id} not found") from exc

    deleted = await session_service.delete_session(session_id)
    return ChatDeleteResponse(
        data={
            "deleted_session_id": str(session_id),
            "deleted": deleted,
        }
    )
