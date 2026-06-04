from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog

from app.domain.session.repo import SessionRepo, MessageRepo
from app.core.errors import AppError, ErrorCode, SystemError
from app.schemas.session import (
    SessionCreateRequest,
    SessionDetail,
    SessionListResponse,
    MessageCreateRequest,
    MessageDetail,
    MessageListResponse,
    MessageUpdateRequest,
    ContextWindowResult,
    SessionRole,
    VALID_ROLES,
)

logger = structlog.get_logger("domain.session.service")


class SessionService:
    """Domain service for session and message management."""

    def __init__(self, session_repo: SessionRepo, message_repo: MessageRepo) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo

    async def create_session(self, request: SessionCreateRequest) -> SessionDetail:
        logger.info("session.create", user_id=request.user_id)
        data: dict = {
            "user_id": request.user_id,
            "title": request.title,
            "intent_type": request.intent_type,
            "model_config": request.model_settings,
            "metadata_": request.metadata,
        }
        session = await self._session_repo.create_session(data)
        return self._session_to_detail(session)

    async def get_session(self, session_id: UUID) -> SessionDetail:
        session = await self._session_repo.get_by_session_id(session_id)
        if session is None:
            raise SystemError(
                ErrorCode.VALIDATION_ERROR,
                f"Session {session_id} not found",
            )
        return self._session_to_detail(session)

    async def list_sessions(
        self,
        user_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> SessionListResponse:
        from app.infra.database import Pagination

        pagination = Pagination(
            offset=offset, limit=limit, sort_by="created_at", sort_order="desc"
        )
        items, total = await self._session_repo.list_sessions(
            user_id=user_id, pagination=pagination
        )
        return SessionListResponse(
            items=[self._session_to_detail(s) for s in items],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def delete_session(self, session_id: UUID) -> bool:
        logger.info("session.delete", session_id=str(session_id))
        session = await self._session_repo.get_by_session_id(session_id)
        if session is None:
            raise SystemError(
                ErrorCode.VALIDATION_ERROR,
                f"Session {session_id} not found",
            )
        return await self._session_repo.delete_session(session_id)

    async def expire_session(self, session_id: UUID) -> SessionDetail:
        logger.info("session.expire", session_id=str(session_id))
        session = await self._session_repo.get_by_session_id(session_id)
        if session is None:
            raise SystemError(
                ErrorCode.VALIDATION_ERROR,
                f"Session {session_id} not found",
            )
        updated = await self._session_repo.update_session(session_id, {
            "metadata_": {**(session.metadata_ or {}), "status": "expired"},
        })
        if updated is None:
            raise SystemError(ErrorCode.INTERNAL_ERROR, "Failed to expire session")
        return self._session_to_detail(updated)

    async def add_message(self, request: MessageCreateRequest) -> MessageDetail:
        session = await self._session_repo.get_by_session_id(request.session_id)
        if session is None:
            raise SystemError(
                ErrorCode.VALIDATION_ERROR,
                f"Session {request.session_id} not found",
            )
        data: dict = {
            "session_id": request.session_id,
            "role": request.role.value,
            "content": request.content,
            "model_name": request.model_name,
            "citations": [c if isinstance(c, dict) else c.model_dump() for c in (request.citations or [])],
            "tool_calls": [tc if isinstance(tc, dict) else tc.model_dump() for tc in (request.tool_calls or [])],
            "tool_results": [tr if isinstance(tr, dict) else tr.model_dump() for tr in (request.tool_results or [])],
            "metadata_": request.metadata,
        }
        message = await self._message_repo.create_message(data)
        return self._message_to_detail(message)

    async def get_messages(
        self,
        session_id: UUID,
        limit: int = 20,
        offset: int = 0,
        role: str | None = None,
    ) -> MessageListResponse:
        from app.infra.database import Pagination

        pagination = Pagination(
            offset=offset, limit=limit, sort_by="created_at", sort_order="desc"
        )
        items, total = await self._message_repo.list_messages(
            session_id=session_id,
            role=role,
            pagination=pagination,
        )
        return MessageListResponse(
            items=[self._message_to_detail(m) for m in items],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def update_message(
        self, message_id: UUID, request: MessageUpdateRequest
    ) -> MessageDetail:
        message = await self._message_repo.get_by_message_id(message_id)
        if message is None:
            raise SystemError(
                ErrorCode.VALIDATION_ERROR,
                f"Message {message_id} not found",
            )
        updated = await self._message_repo.update_message(message_id, {
            "content": request.content,
        })
        if updated is None:
            raise SystemError(ErrorCode.INTERNAL_ERROR, "Failed to update message")
        return self._message_to_detail(updated)

    @staticmethod
    def _session_to_detail(session: object) -> SessionDetail:
        return SessionDetail(
            id=session.id,
            user_id=session.user_id,
            title=session.title,
            intent_type=session.intent_type,
            model_settings=session.model_config,
            created_at=session.created_at,
            updated_at=session.updated_at,
            metadata=session.metadata_,
        )

    @staticmethod
    def _message_to_detail(message: object) -> MessageDetail:
        return MessageDetail(
            id=message.id,
            session_id=message.session_id,
            role=message.role,
            content=message.content,
            token_count=message.token_count,
            model_name=message.model_name,
            citations=message.citations,
            tool_calls=message.tool_calls,
            tool_results=message.tool_results,
            created_at=message.created_at,
            metadata=message.metadata_,
        )