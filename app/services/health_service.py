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


async def check_llm() -> dict:
    """Check LLM gateway channel health (circuit breaker state + latency)."""
    try:
        from app.infra.circuit_breaker import get_circuit_breaker
        from app.services.llm.gateway import LLMGateway

        gateway = container.resolve(LLMGateway)
        channels: dict[str, dict] = {}
        overall = "ok"

        for channel in ("qwen_cloud", "vllm"):
            cb_name = f"llm_{channel}" if channel == "vllm" else "llm_text"
            try:
                cb = get_circuit_breaker(cb_name)
                state = cb.state.value if cb else "unknown"
                if state == "open":
                    overall = "degraded"
                channels[channel] = {"status": state, "latency_ms": None}
            except Exception:
                channels[channel] = {"status": "unknown", "latency_ms": None}

        return {"status": overall, "channels": channels}
    except Exception as exc:
        logger.warning("health.llm_check_failed", error=str(exc))
        return {"status": "degraded", "channels": {}}