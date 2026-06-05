from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import structlog

from app.core.errors import AppError, ErrorCode
from app.core.config import get_settings
from app.core.metrics import record_llm_call, record_circuit_breaker_state
from app.infra.circuit_breaker import CircuitBreaker, CircuitState, get_circuit_breaker
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

        start = time.perf_counter()
        provider_name = type(provider).__name__
        model_name = request.model or ""
        task_type = request.task_type
        cb_state_map = {CircuitState.CLOSED: 0, CircuitState.OPEN: 1, CircuitState.HALF_OPEN: 2}
        record_circuit_breaker_state(
            channel=cb_name,
            state_value=cb_state_map.get(cb.state, 0),
            provider=provider_name,
        )

        async with self._sem_manager.acquire(sem_name):
            try:
                result = await provider.generate(request)
                await cb.record_success()
                duration = time.perf_counter() - start
                record_llm_call(
                    provider=provider_name,
                    model=model_name,
                    task_type=task_type,
                    duration=duration,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
                logger.info(
                    "gateway_generate_complete",
                    provider=provider_name,
                    model=model_name,
                    task_type=task_type,
                    duration=round(duration, 3),
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
                return result
            except AppError:
                await cb.record_failure()
                duration = time.perf_counter() - start
                record_llm_call(
                    provider=provider_name,
                    model=model_name,
                    task_type=task_type,
                    duration=duration,
                )
                raise
            except Exception as exc:
                await cb.record_failure()
                duration = time.perf_counter() - start
                record_llm_call(
                    provider=provider_name,
                    model=model_name,
                    task_type=task_type,
                    duration=duration,
                )
                logger.error(
                    "gateway_generate_failed",
                    provider=provider_name,
                    task_type=task_type,
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

        start = time.perf_counter()
        provider_name = type(provider).__name__
        model_name = request.model or ""
        task_type = request.task_type
        total_input_tokens = 0
        total_output_tokens = 0
        cb_state_map = {CircuitState.CLOSED: 0, CircuitState.OPEN: 1, CircuitState.HALF_OPEN: 2}
        record_circuit_breaker_state(
            channel=cb_name,
            state_value=cb_state_map.get(cb.state, 0),
            provider=provider_name,
        )

        async with self._sem_manager.acquire(sem_name):
            try:
                stream = provider.generate_stream(request)
                async for chunk in stream:
                    if chunk.input_tokens is not None:
                        total_input_tokens = chunk.input_tokens
                    if chunk.output_tokens is not None:
                        total_output_tokens = chunk.output_tokens
                    yield chunk
                await cb.record_success()
                duration = time.perf_counter() - start
                record_llm_call(
                    provider=provider_name,
                    model=model_name,
                    task_type=task_type,
                    duration=duration,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )
                logger.info(
                    "gateway_stream_complete",
                    provider=provider_name,
                    model=model_name,
                    task_type=task_type,
                    duration=round(duration, 3),
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )
            except AppError:
                await cb.record_failure()
                duration = time.perf_counter() - start
                record_llm_call(
                    provider=provider_name,
                    model=model_name,
                    task_type=task_type,
                    duration=duration,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )
                raise
            except Exception as exc:
                await cb.record_failure()
                duration = time.perf_counter() - start
                record_llm_call(
                    provider=provider_name,
                    model=model_name,
                    task_type=task_type,
                    duration=duration,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )
                logger.error(
                    "gateway_stream_failed",
                    provider=provider_name,
                    task_type=task_type,
                    error=str(exc),
                )
                raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "LLM 调用失败") from exc