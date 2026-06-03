from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

import structlog

from app.core.config import get_settings
from app.core.di import container
from app.core.logging import setup_logging, get_logger

logger = get_logger("bootstrap")

_start_time: float = 0.0


async def startup() -> None:
    global _start_time
    _start_time = time.monotonic()

    settings = get_settings()
    setup_logging(level=settings.logging.level, log_format=settings.logging.format)
    logger.info("bootstrap.startup_begin")

    try:
        await _init_infra(settings)
    except Exception as exc:
        logger.error("bootstrap.infra_failed", error=str(exc))

    _register_services()
    logger.info("bootstrap.startup_complete")


async def shutdown() -> None:
    logger.info("bootstrap.shutdown_begin")
    container.cleanup()
    logger.info("bootstrap.shutdown_complete")


async def _init_infra(settings: Any) -> None:
    health: dict[str, str] = {}

    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(
            settings.database.url,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
        )
        container.register(type(engine), lambda: engine, singleton=True)

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        container.register(type(session_factory), lambda: session_factory, singleton=True)

        async with engine.begin() as conn:
            await conn.execute(engine.dialect.text("SELECT 1"))
        health["database"] = "ok"
        logger.info("bootstrap.database_ok")
    except Exception as exc:
        health["database"] = "error"
        logger.warning("bootstrap.database_failed", error=str(exc))

    try:
        from redis import asyncio as aioredis

        redis_client = aioredis.from_url(settings.redis.url)
        await redis_client.ping()
        container.register(type(redis_client), lambda: redis_client, singleton=True)
        health["redis"] = "ok"
        logger.info("bootstrap.redis_ok")
    except Exception as exc:
        health["redis"] = "degraded"
        logger.warning("bootstrap.redis_failed", error=str(exc))

    try:
        from qdrant_client import QdrantClient

        qdrant_client = QdrantClient(url=settings.qdrant.url, timeout=settings.qdrant.timeout)
        container.register(type(qdrant_client), lambda: qdrant_client, singleton=True)
        health["qdrant"] = "ok"
        logger.info("bootstrap.qdrant_ok")
    except Exception as exc:
        health["qdrant"] = "degraded"
        logger.warning("bootstrap.qdrant_failed", error=str(exc))

    container.register(dict, lambda: health, singleton=False)


def _register_services() -> None:
    pass


def get_uptime() -> float:
    if _start_time == 0.0:
        return 0.0
    return round(time.monotonic() - _start_time, 1)


def get_health_status() -> dict[str, Any]:
    from app.core.constants import APP_VERSION

    health_info = container.resolve(dict) if container._factories.get(dict) else {}
    db_status = health_info.get("database", "not_checked")
    redis_status = health_info.get("redis", "not_checked")
    qdrant_status = health_info.get("qdrant", "not_checked")

    if db_status == "error":
        status = "error"
    elif redis_status == "degraded" or qdrant_status == "degraded":
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "version": APP_VERSION,
        "uptime": get_uptime(),
        "dependencies": {
            "database": db_status,
            "redis": redis_status,
            "qdrant": qdrant_status,
        },
    }


@asynccontextmanager
async def lifespan(app: Any):
    await startup()
    yield
    await shutdown()