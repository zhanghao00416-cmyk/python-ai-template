from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import TracebackType
from typing import AsyncGenerator

import structlog

from app.core.errors import AppError, ErrorCode

logger = structlog.get_logger(__name__)

_SEMAPHORE_NAMES: dict[str, str] = {
    "llm": "llm_semaphore_size",
    "multimodal": "multimodal_semaphore_size",
    "embedding": "embedding_semaphore_size",
}


class _SemaphoreAcquire:
    def __init__(
        self,
        semaphore: asyncio.Semaphore,
        name: str,
        timeout: float,
    ) -> None:
        self._semaphore = semaphore
        self._name = name
        self._timeout = timeout

    async def __aenter__(self) -> "_SemaphoreAcquire":
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "semaphore_acquire_timeout",
                semaphore_name=self._name,
                timeout=self._timeout,
            )
            raise AppError(
                ErrorCode.TIMEOUT_ERROR,
                "并发超限，请稍后重试",
            )
        logger.debug("semaphore_acquired", semaphore_name=self._name)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._semaphore.release()
        logger.debug("semaphore_released", semaphore_name=self._name)


class SemaphoreManager:
    def __init__(self) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._timeouts: dict[str, float] = {}
        self._initialized = False

    def initialize(
        self,
        llm: int = 20,
        multimodal: int = 10,
        embedding: int = 20,
        acquire_timeout: float = 120.0,
    ) -> None:
        if self._initialized:
            return

        size_map: dict[str, int] = {
            "llm": llm,
            "multimodal": multimodal,
            "embedding": embedding,
        }

        for name, size in size_map.items():
            self._semaphores[name] = asyncio.Semaphore(size)
            self._timeouts[name] = acquire_timeout
            logger.info(
                "semaphore_initialized",
                semaphore_name=name,
                max_size=size,
                timeout=acquire_timeout,
            )

        self._initialized = True

    @asynccontextmanager
    async def acquire(self, name: str) -> AsyncGenerator[_SemaphoreAcquire, None]:
        if not self._initialized:
            self.initialize()

        if name not in self._semaphores:
            raise ValueError(f"Unknown semaphore name: {name}")

        timeout = self._timeouts[name]
        acquirer = _SemaphoreAcquire(
            semaphore=self._semaphores[name],
            name=name,
            timeout=timeout,
        )
        async with acquirer:
            yield acquirer


_semaphore_manager: SemaphoreManager | None = None


def get_semaphore_manager() -> SemaphoreManager:
    global _semaphore_manager
    if _semaphore_manager is None:
        from app.core.config import get_settings

        settings = get_settings()
        _semaphore_manager = SemaphoreManager()
        _semaphore_manager.initialize(
            llm=settings.concurrency.llm_semaphore_size,
            multimodal=settings.concurrency.multimodal_semaphore_size,
            embedding=settings.concurrency.embedding_semaphore_size,
            acquire_timeout=float(settings.concurrency.semaphore_acquire_timeout),
        )
    return _semaphore_manager


def reset_semaphore_manager() -> None:
    global _semaphore_manager
    _semaphore_manager = None