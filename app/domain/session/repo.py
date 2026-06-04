from __future__ import annotations

import structlog
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database import BaseRepo, Pagination
from app.infra.models import SessionModel, MessageModel

logger = structlog.get_logger("domain.session.repo")


class SessionRepo(BaseRepo[SessionModel]):
    """Repository for Session persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(SessionModel, session)

    async def get_by_session_id(self, session_id: UUID) -> SessionModel | None:
        return await self.get_by_id(session_id)

    async def create_session(self, data: dict) -> SessionModel:
        return await self.create(data)

    async def update_session(self, session_id: UUID, data: dict) -> SessionModel | None:
        return await self.update(session_id, data)

    async def delete_session(self, session_id: UUID) -> bool:
        return await self.delete(session_id)

    async def list_sessions(
        self,
        user_id: str | None = None,
        pagination: Pagination | None = None,
    ) -> tuple[list[SessionModel], int]:
        filters: dict = {}
        if user_id is not None:
            filters["user_id"] = user_id
        result = await self.list(filters=filters or None, pagination=pagination)
        return result.items, result.total

    async def count_sessions(self, user_id: str | None = None) -> int:
        filters: dict = {}
        if user_id is not None:
            filters["user_id"] = user_id
        return await self.count(filters=filters or None)


class MessageRepo(BaseRepo[MessageModel]):
    """Repository for Message persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(MessageModel, session)

    async def get_by_message_id(self, message_id: UUID) -> MessageModel | None:
        return await self.get_by_id(message_id)

    async def create_message(self, data: dict) -> MessageModel:
        return await self.create(data)

    async def update_message(self, message_id: UUID, data: dict) -> MessageModel | None:
        return await self.update(message_id, data)

    async def list_messages(
        self,
        session_id: UUID,
        role: str | None = None,
        pagination: Pagination | None = None,
    ) -> tuple[list[MessageModel], int]:
        filters: dict = {"session_id": session_id}
        if role is not None:
            filters["role"] = role
        result = await self.list(filters=filters, pagination=pagination)
        return result.items, result.total

    async def count_messages(self, session_id: UUID) -> int:
        return await self.count(filters={"session_id": session_id})

    async def get_messages_after(
        self,
        session_id: UUID,
        after_message_id: UUID | None = None,
        limit: int = 100,
    ) -> list[MessageModel]:
        pagination = Pagination(offset=0, limit=limit, sort_by="created_at", sort_order="desc")
        result = await self.list(filters={"session_id": session_id}, pagination=pagination)
        return list(result.items)