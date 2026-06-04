from __future__ import annotations

import asyncio
import functools
import time
from enum import Enum
from typing import Any, Callable, TypeVar

import structlog

from app.core.errors import AppError, ErrorCode

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._half_open_call_count: int = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def record_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.CLOSED)

    async def record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._failure_count >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._half_open_call_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_call_count = 0

        logger.info(
            "circuit_breaker_state_change",
            name=self.name,
            old_state=old_state.value,
            new_state=new_state.value,
            failure_count=self._failure_count,
        )

    async def _check_state(self) -> CircuitState:
        async with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    async def allow_request(self) -> bool:
        current = await self._check_state()
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            async with self._lock:
                if self._half_open_call_count < self.half_open_max_calls:
                    self._half_open_call_count += 1
                    return True
            return False
        return False


_registry: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    half_open_max_calls: int = 1,
) -> CircuitBreaker:
    if name not in _registry:
        _registry[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
        )
    return _registry[name]


def reset_circuit_breakers() -> None:
    global _registry
    _registry.clear()


def with_circuit_breaker(name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cb = get_circuit_breaker(name)
            allowed = await cb.allow_request()
            if not allowed:
                logger.warning(
                    "circuit_breaker_rejected",
                    name=cb.name,
                    state=cb.state.value,
                )
                raise AppError(
                    ErrorCode.SERVICE_UNAVAILABLE,
                    "服务暂时不可用（熔断器开启）",
                )

            try:
                result = await func(*args, **kwargs)
                await cb.record_success()
                return result
            except AppError:
                await cb.record_failure()
                raise
            except Exception as exc:
                await cb.record_failure()
                logger.error(
                    "circuit_breaker_caught_exception",
                    name=cb.name,
                    error=str(exc),
                )
                raise AppError(
                    ErrorCode.SERVICE_UNAVAILABLE,
                    "服务暂时不可用",
                ) from exc

        return wrapper

    return decorator