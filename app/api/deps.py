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


def get_knowledge_service(session: AsyncSession):
    """Factory to create a KnowledgeService with resolved infra dependencies."""
    import importlib

    from app.domain.knowledge.repo import KnowledgeRepo
    from app.domain.knowledge.service import KnowledgeService
    from app.services.llm.gateway import LLMGateway
    from app.services.prompt_manager import PromptManager

    vs_mod = importlib.import_module("app.infra.vector_store.qdrant_store")
    vs_cls = getattr(vs_mod, "QdrantVectorStore")
    vector_store = container.resolve(vs_cls)
    repo = KnowledgeRepo(vector_store=vector_store)
    task_service = get_task_service(session)

    llm_gateway = None
    try:
        llm_gateway = container.resolve(LLMGateway)
    except Exception:
        pass

    prompt_manager = None
    try:
        prompt_manager = container.resolve(PromptManager)
    except Exception:
        pass

    return KnowledgeService(
        repo=repo,
        task_service=task_service,
        llm_gateway=llm_gateway,
        prompt_manager=prompt_manager,
    )


def _resolve_redis_client():
    """Resolve RedisClient from DI container; avoids top-level app.infra import."""
    import importlib
    redis_mod = importlib.import_module("app.infra.redis_client")
    redis_cls = getattr(redis_mod, "RedisClient")
    return container.resolve(redis_cls)