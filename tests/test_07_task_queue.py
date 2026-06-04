from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.errors import ErrorCode, TaskError, make_error
from app.domain.task.repo import TaskRepo
from app.domain.task.service import TaskService, _is_valid_transition
from app.schemas.task import TaskCreateRequest, TaskStatus, TaskType
from app.services.task_queue import TaskQueueService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task_model(
    task_id=None,
    task_type="kb_upload",
    status="pending",
    progress=0.0,
    input_data=None,
    output_data=None,
    error_message=None,
    callback_url=None,
    user_id=None,
    metadata_=None,
):
    model = MagicMock()
    model.id = task_id or uuid4()
    model.task_type = task_type
    model.status = status
    model.progress = progress
    model.input_data = input_data
    model.output_data = output_data
    model.error_message = error_message
    model.callback_url = callback_url
    model.user_id = user_id
    model.metadata_ = metadata_
    model.created_at = datetime.now(timezone.utc)
    model.started_at = None
    model.completed_at = None
    return model


def _make_task_service(repo=None, task_queue=None):
    if repo is None:
        repo = AsyncMock(spec=TaskRepo)
    if task_queue is None:
        task_queue = AsyncMock(spec=TaskQueueService)
    return TaskService(repo=repo, task_queue=task_queue), repo, task_queue


# ===========================================================================
# TestTaskType
# ===========================================================================

class TestTaskType:
    def test_task_type_values(self):
        assert TaskType.KB_UPLOAD.value == "kb_upload"
        assert TaskType.AGENT_RUN.value == "agent_run"
        assert TaskType.WORKFLOW_RUN.value == "workflow_run"
        assert TaskType.BATCH_IMPORT.value == "batch_import"
        assert TaskType.BATCH_EVAL.value == "batch_eval"
        assert TaskType.BATCH_EMBED.value == "batch_embed"
        assert TaskType.CUSTOM.value == "custom"


class TestTaskStatus:
    def test_task_status_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"


# ===========================================================================
# TestStatusTransitions
# ===========================================================================

class TestStatusTransitions:
    def test_pending_to_running(self):
        assert _is_valid_transition("pending", "running") is True

    def test_pending_to_failed(self):
        assert _is_valid_transition("pending", "failed") is True

    def test_running_to_completed(self):
        assert _is_valid_transition("running", "completed") is True

    def test_running_to_failed(self):
        assert _is_valid_transition("running", "failed") is True

    def test_completed_to_any(self):
        assert _is_valid_transition("completed", "running") is False
        assert _is_valid_transition("completed", "pending") is False

    def test_failed_to_any(self):
        assert _is_valid_transition("failed", "running") is False
        assert _is_valid_transition("failed", "pending") is False

    def test_pending_to_completed_invalid(self):
        assert _is_valid_transition("pending", "completed") is False

    def test_running_to_pending_invalid(self):
        assert _is_valid_transition("running", "pending") is False


# ===========================================================================
# TestTaskService
# ===========================================================================

class TestTaskServiceSubmit:
    @pytest.mark.asyncio
    async def test_submit_task_success(self):
        task_id = uuid4()
        model = _make_task_model(task_id=task_id, task_type="kb_upload", status="pending")

        service, repo, queue = _make_task_service()
        repo.create_task.return_value = model
        queue.enqueue = AsyncMock()

        result = await service.submit_task(
            task_type="kb_upload",
            input_data={"file": "test.md"},
            user_id="user-1",
        )

        assert result.task_id == task_id
        assert result.task_type == "kb_upload"
        assert result.status == "pending"
        repo.create_task.assert_called_once()
        queue.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_task_with_callback_url(self):
        task_id = uuid4()
        model = _make_task_model(task_id=task_id, callback_url="https://example.com/callback")

        service, repo, queue = _make_task_service()
        repo.create_task.return_value = model
        queue.enqueue = AsyncMock()

        result = await service.submit_task(
            task_type="batch_import",
            callback_url="https://example.com/callback",
        )

        call_data = repo.create_task.call_args[0][0]
        assert call_data["callback_url"] == "https://example.com/callback"

    @pytest.mark.asyncio
    async def test_submit_task_enqueue_failure(self):
        repo = AsyncMock(spec=TaskRepo)
        queue = AsyncMock(spec=TaskQueueService)

        task_id = uuid4()
        model = _make_task_model(task_id=task_id)
        repo.create_task.return_value = model
        queue.enqueue.side_effect = Exception("Redis connection failed")

        updated_model = _make_task_model(task_id=task_id, status="failed", error_message="Failed to enqueue task: Redis connection failed")
        repo.update_task.return_value = updated_model

        service = TaskService(repo=repo, task_queue=queue)

        with pytest.raises(TaskError) as exc_info:
            await service.submit_task(task_type="custom")

        assert exc_info.value.code == ErrorCode.TASK_SUBMIT_FAILED

    @pytest.mark.asyncio
    async def test_submit_task_all_types(self):
        service, repo, queue = _make_task_service()

        for task_type in ["kb_upload", "agent_run", "workflow_run", "batch_import", "batch_eval", "batch_embed", "custom"]:
            task_id = uuid4()
            model = _make_task_model(task_id=task_id, task_type=task_type)
            repo.create_task.return_value = model
            queue.enqueue = AsyncMock()

            result = await service.submit_task(task_type=task_type)
            assert result.task_type == task_type


class TestTaskServiceGet:
    @pytest.mark.asyncio
    async def test_get_task_success(self):
        task_id = uuid4()
        model = _make_task_model(task_id=task_id, task_type="kb_upload", status="running", progress=0.5)
        model.started_at = datetime.now(timezone.utc)

        service, repo, queue = _make_task_service()
        repo.get_by_task_id.return_value = model

        result = await service.get_task(task_id)

        assert result.task_id == task_id
        assert result.task_type == "kb_upload"
        assert result.status == "running"
        assert result.progress == 0.5

    @pytest.mark.asyncio
    async def test_get_task_not_found(self):
        service, repo, queue = _make_task_service()
        repo.get_by_task_id.return_value = None

        with pytest.raises(TaskError) as exc_info:
            await service.get_task(uuid4())

        assert exc_info.value.code == ErrorCode.TASK_NOT_FOUND


class TestTaskServiceUpdateStatus:
    @pytest.mark.asyncio
    async def test_update_pending_to_running(self):
        task_id = uuid4()
        model = _make_task_model(task_id=task_id, status="pending")
        updated_model = _make_task_model(task_id=task_id, status="running", progress=0.0)
        updated_model.started_at = datetime.now(timezone.utc)

        service, repo, queue = _make_task_service()
        repo.get_by_task_id.return_value = model
        repo.update_task.return_value = updated_model

        result = await service.update_task_status(task_id, "running")

        assert result.status == "running"
        call_data = repo.update_task.call_args[0][1]
        assert call_data["status"] == "running"
        assert "started_at" in call_data

    @pytest.mark.asyncio
    async def test_update_running_to_completed(self):
        task_id = uuid4()
        model = _make_task_model(task_id=task_id, status="running")
        model.started_at = datetime.now(timezone.utc)
        updated_model = _make_task_model(task_id=task_id, status="completed", progress=1.0)
        updated_model.started_at = model.started_at
        updated_model.completed_at = datetime.now(timezone.utc)

        service, repo, queue = _make_task_service()
        repo.get_by_task_id.return_value = model
        repo.update_task.return_value = updated_model

        result = await service.update_task_status(
            task_id, "completed", progress=1.0, output_data={"result": "done"}
        )

        assert result.status == "completed"
        call_data = repo.update_task.call_args[0][1]
        assert call_data["status"] == "completed"
        assert call_data["progress"] == 1.0
        assert "completed_at" in call_data

    @pytest.mark.asyncio
    async def test_update_running_to_failed(self):
        task_id = uuid4()
        model = _make_task_model(task_id=task_id, status="running")
        updated_model = _make_task_model(task_id=task_id, status="failed", error_message="Timeout")

        service, repo, queue = _make_task_service()
        repo.get_by_task_id.return_value = model
        repo.update_task.return_value = updated_model

        result = await service.update_task_status(
            task_id, "failed", error_message="Timeout"
        )

        assert result.status == "failed"
        call_data = repo.update_task.call_args[0][1]
        assert "completed_at" in call_data

    @pytest.mark.asyncio
    async def test_update_invalid_transition(self):
        task_id = uuid4()
        model = _make_task_model(task_id=task_id, status="completed")

        service, repo, queue = _make_task_service()
        repo.get_by_task_id.return_value = model

        with pytest.raises(TaskError) as exc_info:
            await service.update_task_status(task_id, "running")

        assert exc_info.value.code == ErrorCode.TASK_ALREADY_RUNNING

    @pytest.mark.asyncio
    async def test_update_task_not_found(self):
        service, repo, queue = _make_task_service()
        repo.get_by_task_id.return_value = None

        with pytest.raises(TaskError) as exc_info:
            await service.update_task_status(uuid4(), "running")

        assert exc_info.value.code == ErrorCode.TASK_NOT_FOUND


class TestTaskServiceList:
    @pytest.mark.asyncio
    async def test_list_tasks_with_filters(self):
        items = [
            _make_task_model(task_type="kb_upload", status="completed"),
            _make_task_model(task_type="agent_run", status="running"),
        ]

        service, repo, queue = _make_task_service()
        repo.list_tasks.return_value = (items, 2)

        results, total = await service.list_tasks(
            task_type="kb_upload", status="completed", offset=0, limit=20
        )

        assert total == 2
        assert len(results) == 2
        repo.list_tasks.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tasks_no_filters(self):
        items = [_make_task_model() for _ in range(5)]

        service, repo, queue = _make_task_service()
        repo.list_tasks.return_value = (items, 5)

        results, total = await service.list_tasks()

        assert total == 5
        assert len(results) == 5


# ===========================================================================
# TestTaskQueueService
# ===========================================================================

class TestTaskQueueService:
    @pytest.mark.asyncio
    async def test_enqueue(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.lpush = AsyncMock()

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")
        await tq.enqueue(task_id="test-123", task_type="kb_upload", input_data={"file": "a.md"})

        redis_mock.client.lpush.assert_called_once()
        call_args = redis_mock.client.lpush.call_args
        assert call_args[0][0] == "arq:tasks"

    @pytest.mark.asyncio
    async def test_enqueue_failure_raises(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.lpush = AsyncMock(side_effect=Exception("Redis down"))

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")

        with pytest.raises(Exception, match="Redis down"):
            await tq.enqueue(task_id="test-123", task_type="kb_upload")

    @pytest.mark.asyncio
    async def test_dequeue(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.brpop = AsyncMock(return_value=("arq:tasks", b'{"task_id": "abc", "task_type": "custom"}'))

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")
        result = await tq.dequeue(timeout=5)

        assert result is not None
        assert result["task_id"] == "abc"
        assert result["task_type"] == "custom"

    @pytest.mark.asyncio
    async def test_dequeue_empty(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.brpop = AsyncMock(return_value=None)

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")
        result = await tq.dequeue(timeout=1)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_queue_size(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.llen = AsyncMock(return_value=5)

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")
        size = await tq.get_queue_size()

        assert size == 5

    @pytest.mark.asyncio
    async def test_get_queue_size_error_returns_zero(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.llen = AsyncMock(side_effect=Exception("error"))

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")
        size = await tq.get_queue_size()

        assert size == 0

    @pytest.mark.asyncio
    async def test_set_and_get_task_status_cache(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.hset = AsyncMock()
        redis_mock.client.expire = AsyncMock()
        redis_mock.client.hgetall = AsyncMock(return_value={"status": "running", "progress": "0.5"})
        redis_mock.client.delete = AsyncMock()

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")

        await tq.set_task_status_cache("test-123", "running", progress=0.5)
        redis_mock.client.hset.assert_called_once()

        data = await tq.get_task_status_cache("test-123")
        assert data is not None
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_task_status_cache_empty(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.hgetall = AsyncMock(return_value={})

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")
        data = await tq.get_task_status_cache("nonexistent")

        assert data is None

    @pytest.mark.asyncio
    async def test_remove_task_status_cache(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.delete = AsyncMock()

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")
        await tq.remove_task_status_cache("test-123")
        redis_mock.client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_task_status_cache_error_silent(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.delete = AsyncMock(side_effect=Exception("error"))

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")
        await tq.remove_task_status_cache("test-123")  # Should not raise

    @pytest.mark.asyncio
    async def test_set_task_status_cache_error_logs(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.hset = AsyncMock(side_effect=Exception("Redis error"))

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")
        await tq.set_task_status_cache("test-123", "running")  # Should not raise, just log

    @pytest.mark.asyncio
    async def test_get_task_status_cache_error_returns_none(self):
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        redis_mock.client.hgetall = AsyncMock(side_effect=Exception("Redis error"))

        tq = TaskQueueService(redis_client=redis_mock, queue_name="arq:tasks")
        data = await tq.get_task_status_cache("test-123")

        assert data is None


# ===========================================================================
# TestCreateRequest validation
# ===========================================================================

class TestTaskCreateRequest:
    def test_valid_request(self):
        req = TaskCreateRequest(task_type=TaskType.KB_UPLOAD)
        assert req.task_type == TaskType.KB_UPLOAD
        assert req.input_data is None
        assert req.callback_url is None
        assert req.metadata is None

    def test_request_with_all_fields(self):
        req = TaskCreateRequest(
            task_type=TaskType.AGENT_RUN,
            input_data={"query": "test"},
            callback_url="https://example.com/callback",
            metadata={"priority": "high"},
        )
        assert req.task_type == TaskType.AGENT_RUN
        assert req.input_data == {"query": "test"}
        assert req.callback_url == "https://example.com/callback"

    def test_request_custom_type(self):
        req = TaskCreateRequest(task_type=TaskType.CUSTOM)
        assert req.task_type == TaskType.CUSTOM


# ===========================================================================
# Test error codes
# ===========================================================================

class TestTaskErrorCodes:
    def test_task_not_found(self):
        assert ErrorCode.TASK_NOT_FOUND == 9001
        assert ErrorCode.TASK_NOT_FOUND in ErrorCode._value2member_map_

    def test_task_already_running(self):
        assert ErrorCode.TASK_ALREADY_RUNNING == 9002

    def test_task_submit_failed(self):
        assert ErrorCode.TASK_SUBMIT_FAILED == 9003

    def test_make_error_task_domain(self):
        err = make_error(9001, "Task not found")
        assert isinstance(err, TaskError)
        assert err.code == 9001

    def test_make_error_9xxx_is_task_error(self):
        for code in [9001, 9002, 9003]:
            err = make_error(code, "test")
            assert isinstance(err, TaskError)


class TestTaskQueueConfig:
    def test_default_config(self):
        from app.core.config import TaskQueueSettings
        settings = TaskQueueSettings()
        assert settings.redis_queue_name == "arq:tasks"
        assert settings.max_retries == 3
        assert settings.retry_delay == 60

    def test_config_in_settings(self):
        from app.core.config import Settings
        settings = Settings()
        assert hasattr(settings, "task_queue")
        assert settings.task_queue.redis_queue_name == "arq:tasks"


# ===========================================================================
# Test API endpoints (with mocked service)
# ===========================================================================

class TestTaskAPIEndpoints:
    @pytest.fixture
    def mock_app(self):
        from fastapi import FastAPI
        from app.api.v1.task import router
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, mock_app):
        from httpx import AsyncClient, ASGITransport
        return AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://test")

    @pytest.mark.asyncio
    async def test_create_task_endpoint(self, mock_app):
        from httpx import AsyncClient, ASGITransport
        from unittest.mock import patch, MagicMock
        from app.api import deps

        task_id = uuid4()
        now = datetime.now(timezone.utc)

        mock_service = AsyncMock(spec=TaskService)
        mock_service.submit_task.return_value = MagicMock(
            task_id=task_id,
            task_type="kb_upload",
            status="pending",
            created_at=now,
            model_dump=MagicMock(return_value={
                "task_id": str(task_id),
                "task_type": "kb_upload",
                "status": "pending",
                "created_at": now.isoformat(),
            }),
        )

        with patch.object(deps, "get_task_service", return_value=mock_service):
            with patch.object(deps, "get_db_session") as mock_session:
                mock_sess = AsyncMock()
                mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
                mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                async with AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://test") as client:
                    pass

    def test_router_has_endpoints(self):
        from app.api.v1.task import router
        routes = [r.path for r in router.routes]
        assert "/tasks" in routes or any("/tasks" in str(r) for r in router.routes)