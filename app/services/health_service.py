from __future__ import annotations

import time

import structlog

from app.core.di import container

logger = structlog.get_logger("services.health")


async def check_database() -> dict:
    try:
        from app.infra.database import get_engine
        import sqlalchemy

        engine = get_engine()
        start = time.monotonic()
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        latency = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "latency_ms": latency}
    except Exception as exc:
        logger.warning("health.database_check_failed", error=str(exc))
        return {"status": "error", "latency_ms": None}


async def check_redis() -> dict:
    try:
        from app.infra.redis_client import RedisClient

        redis_client = container.resolve(RedisClient)
        start = time.monotonic()
        await redis_client.ping()
        latency = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "latency_ms": latency}
    except Exception as exc:
        logger.warning("health.redis_check_failed", error=str(exc))
        return {"status": "degraded", "latency_ms": None}


async def check_qdrant() -> dict:
    try:
        from app.infra.vector_store import VectorStoreBase

        vector_store = container.resolve(VectorStoreBase)
        start = time.monotonic()
        collections = await vector_store.list_collections()
        latency = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "latency_ms": latency, "collections": collections}
    except Exception as exc:
        logger.warning("health.qdrant_check_failed", error=str(exc))
        return {"status": "degraded", "latency_ms": None}