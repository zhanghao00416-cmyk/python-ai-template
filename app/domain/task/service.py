from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog

from app.domain.task.repo import TaskRepo
from app.core.errors import TaskError, ErrorCode
from app.schemas.task import (
    TaskCreateResponse,
    TaskCreateRequest,
    TaskStatus,
    TaskStatusResponse,
    TaskType,
    VALID_TASK_STATUSES,
)
from app.services.task_queue import TaskQueueService

logger = structlog.get_logger("domain.task.service")


class TaskService:
    """Domain service for task management.

    Orchestrates PG persistence (via TaskRepo) and Redis queue (via TaskQueueService).
    """

    def __init__(self, repo: TaskRepo, task_queue: TaskQueueService) -> None:
        self._repo = repo
        self._task_queue = task_queue

    async def submit_task(
        self,
        task_type: str,
        input_data: dict | None = None,
        callback_url: str | None = None,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> TaskCreateResponse:
        logger.info("task.submit", task_type=task_type, user_id=user_id)

        data: dict = {
            "task_type": task_type,
            "status": TaskStatus.PENDING.value,
            "input_data": input_data,
            "callback_url": callback_url,
            "metadata_": metadata,
            "progress": 0.0,
        }
        if user_id is not None:
            data["user_id"] = user_id

        task = await self._repo.create_task(data)
        task_id = task.id

        try:
            await self._task_queue.enqueue(
                task_id=str(task_id),
                task_type=task_type,
                input_data=input_data or {},
            )
        except Exception as exc:
            logger.error("task.enqueue_failed", task_id=str(task_id), error=str(exc))
            await self._repo.update_task(
                task_id,
                {
                    "status": TaskStatus.FAILED.value,
                    "error_message": f"Failed to enqueue task: {exc}",
                },
            )
            raise TaskError(
                ErrorCode.TASK_SUBMIT_FAILED,
                f"Failed to submit task to queue: {exc}",
            )

        logger.info("task.submitted", task_id=str(task_id), task_type=task_type)
        return TaskCreateResponse(
            task_id=task_id,
            task_type=task.task_type,
            status=task.status,
            created_at=task.created_at,
        )

    async def get_task(self, task_id: UUID) -> TaskStatusResponse:
        task = await self._repo.get_by_task_id(task_id)
        if task is None:
            raise TaskError(ErrorCode.TASK_NOT_FOUND, f"Task {task_id} not found")

        return TaskStatusResponse(
            task_id=task.id,
            task_type=task.task_type,
            status=task.status,
            progress=task.progress,
            input_data=task.input_data,
            output_data=task.output_data,
            error_message=task.error_message,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
        )

    async def update_task_status(
        self,
        task_id: UUID,
        status: str,
        progress: float | None = None,
        output_data: dict | None = None,
        error_message: str | None = None,
    ) -> TaskStatusResponse:
        task = await self._repo.get_by_task_id(task_id)
        if task is None:
            raise TaskError(ErrorCode.TASK_NOT_FOUND, f"Task {task_id} not found")

        current_status = task.status
        if not _is_valid_transition(current_status, status):
            raise TaskError(
                ErrorCode.TASK_ALREADY_RUNNING,
                f"Cannot transition task {task_id} from {current_status} to {status}",
            )

        update_data: dict = {"status": status}
        now = datetime.now(timezone.utc)

        if status == TaskStatus.RUNNING.value and task.started_at is None:
            update_data["started_at"] = now

        if status in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value):
            update_data["completed_at"] = now

        if progress is not None:
            update_data["progress"] = progress

        if output_data is not None:
            update_data["output_data"] = output_data

        if error_message is not None:
            update_data["error_message"] = error_message

        updated = await self._repo.update_task(task_id, update_data)
        if updated is None:
            raise TaskError(ErrorCode.TASK_NOT_FOUND, f"Task {task_id} update failed")

        return TaskStatusResponse(
            task_id=updated.id,
            task_type=updated.task_type,
            status=updated.status,
            progress=updated.progress,
            input_data=updated.input_data,
            output_data=updated.output_data,
            error_message=updated.error_message,
            created_at=updated.created_at,
            started_at=updated.started_at,
            completed_at=updated.completed_at,
        )

    async def list_tasks(
        self,
        task_type: str | None = None,
        status: str | None = None,
        user_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[TaskStatusResponse], int]:
        from app.infra.database import Pagination

        pagination = Pagination(offset=offset, limit=limit, sort_by="created_at", sort_order="desc")
        items, total = await self._repo.list_tasks(
            task_type=task_type,
            status=status,
            user_id=user_id,
            pagination=pagination,
        )
        responses = [
            TaskStatusResponse(
                task_id=t.id,
                task_type=t.task_type,
                status=t.status,
                progress=t.progress,
                input_data=t.input_data,
                output_data=t.output_data,
                error_message=t.error_message,
                created_at=t.created_at,
                started_at=t.started_at,
                completed_at=t.completed_at,
            )
            for t in items
        ]
        return responses, total


def _is_valid_transition(current: str, target: str) -> bool:
    transitions = {
        TaskStatus.PENDING.value: {TaskStatus.RUNNING.value, TaskStatus.FAILED.value},
        TaskStatus.RUNNING.value: {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value},
        TaskStatus.COMPLETED.value: set(),
        TaskStatus.FAILED.value: set(),
    }
    allowed = transitions.get(current, set())
    return target in allowed