from __future__ import annotations

import redis.asyncio as aioredis
import structlog

from app.core.errors import ErrorCode, InfraError

logger = structlog.get_logger("infra.redis_client")


class RedisClient:
    """Async Redis client wrapper with health check and basic operations."""

    def __init__(self, url: str, db: int = 0) -> None:
        self._url = url
        self._db = db
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        """Create the Redis connection and verify with PING."""
        self._client = aioredis.from_url(self._url, db=self._db, decode_responses=True)
        await self._client.ping()
        logger.info("redis.connected", url=self._url)

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("redis.closed")

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise InfraError(ErrorCode.REDIS_ERROR, "Redis client not initialized")
        return self._client

    async def ping(self) -> bool:
        """Health check: returns True if Redis is reachable."""
        try:
            return await self.client.ping()
        except Exception as exc:
            logger.warning("redis.ping_failed", error=str(exc))
            return False

    async def get(self, key: str) -> str | None:
        """Get value by key."""
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """Set value with optional TTL in seconds."""
        await self.client.set(key, value, ex=ex)

    async def delete(self, key: str) -> int:
        """Delete key. Returns number of keys removed."""
        return await self.client.delete(key)

    async def incr(self, key: str) -> int:
        """Increment counter (for rate limiting)."""
        return await self.client.incr(key)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set TTL on a key. Returns True if TTL was set."""
        return await self.client.expire(key, seconds)

    async def hgetall(self, name: str) -> dict[str, str]:
        """Get all fields and values in a hash."""
        return await self.client.hgetall(name)

    async def hset(self, name: str, mapping: dict[str, str]) -> int:
        """Set fields in a hash."""
        return await self.client.hset(name, mapping=mapping)

    async def hdelete(self, name: str, *keys: str) -> int:
        """Delete fields from a hash. Returns number of fields removed."""
        return await self.client.hdel(name, *keys)
