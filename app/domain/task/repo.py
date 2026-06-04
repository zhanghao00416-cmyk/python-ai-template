from __future__ import annotations

import structlog
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode, TaskError, make_error
from app.infra.database import BaseRepo, Pagination
from app.infra.models import TaskModel
from app.schemas.task import TaskType, TaskStatus, VALID_TASK_STATUSES

logger = structlog.get_logger("domain.task.repo")


class TaskRepo(BaseRepo[TaskModel]):
    """Repository for Task persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TaskModel, session)

    async def get_by_task_id(self, task_id: UUID) -> TaskModel | None:
        return await self.get_by_id(task_id)

    async def create_task(self, data: dict) -> TaskModel:
        return await self.create(data)

    async def update_task(self, task_id: UUID, data: dict) -> TaskModel | None:
        return await self.update(task_id, data)

    async def list_tasks(
        self,
        task_type: str | None = None,
        status: str | None = None,
        user_id: str | None = None,
        pagination: Pagination | None = None,
    ) -> tuple[list[TaskModel], int]:
        filters: dict = {}
        if task_type is not None:
            filters["task_type"] = task_type
        if status is not None:
            filters["status"] = status
        if user_id is not None:
            filters["user_id"] = user_id
        result = await self.list(filters=filters or None, pagination=pagination)
        return result.items, result.total