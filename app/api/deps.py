from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.di import container


def get_settings():
    from app.core.config import get_settings
    return get_settings()


def get_health_status():
    from app.bootstrap import get_health_status
    return get_health_status()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session via DI container."""
    session_factory = container.resolve(async_sessionmaker)
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_task_service(session: AsyncSession):
    """Factory to create a TaskService with DB session and Redis queue.

    Resolves infra dependencies (RedisClient) via DI container;
    no direct infra import at module level.
    """
    from app.domain.task.repo import TaskRepo
    from app.domain.task.service import TaskService
    from app.services.task_queue import TaskQueueService

    repo = TaskRepo(session=session)
    redis_client = _resolve_redis_client()
    settings = get_settings()
    task_queue = TaskQueueService(
        redis_client=redis_client,
        queue_name=settings.task_queue.redis_queue_name,
    )
    return TaskService(repo=repo, task_queue=task_queue)


def _resolve_redis_client():
    """Resolve RedisClient from DI container; avoids top-level app.infra import."""
    import importlib
    redis_mod = importlib.import_module("app.infra.redis_client")
    redis_cls = getattr(redis_mod, "RedisClient")
    return container.resolve(redis_cls)