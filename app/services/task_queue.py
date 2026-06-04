from __future__ import annotations

import json
from typing import Any

import structlog

from app.infra.redis_client import RedisClient

logger = structlog.get_logger("services.task_queue")


class TaskQueueService:
    """Redis-backed lightweight task queue service.

    Uses Redis LIST for enqueue/dequeue and HASH for fast status lookup.
    PG (TaskModel) is the source of truth; Redis is for dispatch only.
    """

    def __init__(self, redis_client: RedisClient, queue_name: str = "arq:tasks") -> None:
        self._redis = redis_client
        self._queue_name = queue_name

    async def enqueue(self, task_id: str, task_type: str, input_data: dict[str, Any] | None = None) -> None:
        payload = json.dumps({
            "task_id": task_id,
            "task_type": task_type,
            "input_data": input_data or {},
        })
        try:
            await self._redis.client.lpush(self._queue_name, payload)
            logger.info("task_queue.enqueued", task_id=task_id, task_type=task_type)
        except Exception as exc:
            logger.error("task_queue.enqueue_failed", task_id=task_id, error=str(exc))
            raise

    async def dequeue(self, timeout: int = 0) -> dict[str, Any] | None:
        try:
            result = await self._redis.client.brpop(self._queue_name, timeout=timeout)
            if result is None:
                return None
            _, payload = result
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            return json.loads(payload)
        except Exception as exc:
            logger.error("task_queue.dequeue_failed", error=str(exc))
            raise

    async def get_queue_size(self) -> int:
        try:
            return await self._redis.client.llen(self._queue_name)
        except Exception:
            return 0

    async def set_task_status_cache(
        self,
        task_id: str,
        status: str,
        progress: float | None = None,
    ) -> None:
        mapping: dict[str, str] = {"status": status}
        if progress is not None:
            mapping["progress"] = str(progress)
        key = f"task_status:{task_id}"
        try:
            await self._redis.client.hset(key, mapping=mapping)
            await self._redis.client.expire(key, 86400)
        except Exception as exc:
            logger.warning("task_queue.cache_set_failed", task_id=task_id, error=str(exc))

    async def get_task_status_cache(self, task_id: str) -> dict[str, str] | None:
        key = f"task_status:{task_id}"
        try:
            data = await self._redis.client.hgetall(key)
            return data if data else None
        except Exception:
            return None

    async def remove_task_status_cache(self, task_id: str) -> None:
        key = f"task_status:{task_id}"
        try:
            await self._redis.client.delete(key)
        except Exception:
            pass