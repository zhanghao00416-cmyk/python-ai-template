from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog

from app.core.errors import AppError, ErrorCode
from app.core.config import get_settings
from app.infra.circuit_breaker import CircuitBreaker, get_circuit_breaker
from app.infra.semaphore_manager import SemaphoreManager, get_semaphore_manager
from app.schemas.llm import LLMRequest, LLMResponse, LLMChunk
from app.services.llm.router import LLMRouter
from app.services.llm.providers.base import LLMProvider
from app.services.llm.providers.vllm import VLLMProvider

logger = structlog.get_logger(__name__)


def _provider_to_sem_name(provider: LLMProvider, task_type: str) -> str:
    if task_type == "multimodal":
        return "multimodal"
    if task_type == "embedding":
        return "embedding"
    return "llm"


def _provider_to_cb_name(provider: LLMProvider, task_type: str) -> str:
    if task_type == "multimodal":
        return "multimodal"
    if task_type == "embedding":
        return "embedding"
    if isinstance(provider, VLLMProvider):
        return "llm_vllm"
    return "llm_text"


def _cb_open_error_code(cb_name: str, task_type: str) -> int:
    if task_type in ("multimodal", "embedding"):
        return ErrorCode.CLOUD_MODEL_ERROR
    if cb_name == "llm_text":
        return ErrorCode.CLOUD_MODEL_ERROR
    return ErrorCode.LOCAL_MODEL_UNAVAILABLE


class LLMGateway:
    def __init__(
        self,
        router: LLMRouter | None = None,
        sem_manager: SemaphoreManager | None = None,
        settings: Any | None = None,
    ) -> None:
        self._router = router or LLMRouter()
        self._sem_manager = sem_manager or get_semaphore_manager()
        self._settings = settings or get_settings()

    async def generate(self, request: LLMRequest) -> LLMResponse:
        provider = self._router.select_provider(request.task_type, model=request.model)
        cb_name = _provider_to_cb_name(provider, request.task_type)
        sem_name = _provider_to_sem_name(provider, request.task_type)
        cb = get_circuit_breaker(cb_name)

        if not await cb.allow_request():
            fallback = self._router.select_fallback_provider(request.task_type)
            if fallback is not None:
                fb_cb_name = _provider_to_cb_name(fallback, request.task_type)
                fb_cb = get_circuit_breaker(fb_cb_name)
                if await fb_cb.allow_request():
                    provider = fallback
                    cb = fb_cb
                    sem_name = _provider_to_sem_name(provider, request.task_type)
                else:
                    raise AppError(
                        ErrorCode.SERVICE_UNAVAILABLE,
                        "主通道和降级通道均不可用",
                    )
            else:
                raise AppError(
                    _cb_open_error_code(cb_name, request.task_type),
                    "服务暂时不可用（熔断器开启）",
                )

        async with self._sem_manager.acquire(sem_name):
            try:
                result = await provider.generate(request)
                await cb.record_success()
                return result
            except AppError:
                await cb.record_failure()
                raise
            except Exception as exc:
                await cb.record_failure()
                logger.error(
                    "gateway_generate_failed",
                    provider=type(provider).__name__,
                    task_type=request.task_type,
                    error=str(exc),
                )
                raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "LLM 调用失败") from exc

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        provider = self._router.select_provider(request.task_type, model=request.model)
        cb_name = _provider_to_cb_name(provider, request.task_type)
        sem_name = _provider_to_sem_name(provider, request.task_type)
        cb = get_circuit_breaker(cb_name)

        if not await cb.allow_request():
            fallback = self._router.select_fallback_provider(request.task_type)
            if fallback is not None:
                fb_cb_name = _provider_to_cb_name(fallback, request.task_type)
                fb_cb = get_circuit_breaker(fb_cb_name)
                if await fb_cb.allow_request():
                    provider = fallback
                    cb = fb_cb
                    sem_name = _provider_to_sem_name(provider, request.task_type)
                else:
                    raise AppError(
                        ErrorCode.SERVICE_UNAVAILABLE,
                        "主通道和降级通道均不可用",
                    )
            else:
                raise AppError(
                    _cb_open_error_code(cb_name, request.task_type),
                    "服务暂时不可用（熔断器开启）",
                )

        async with self._sem_manager.acquire(sem_name):
            try:
                stream = provider.generate_stream(request)
                async for chunk in stream:
                    yield chunk
                await cb.record_success()
            except AppError:
                await cb.record_failure()
                raise
            except Exception as exc:
                await cb.record_failure()
                logger.error(
                    "gateway_stream_failed",
                    provider=type(provider).__name__,
                    task_type=request.task_type,
                    error=str(exc),
                )
                raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "LLM 调用失败") from exc