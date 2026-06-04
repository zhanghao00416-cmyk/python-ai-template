from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import litellm
import structlog

from app.core.errors import AppError, ErrorCode
from app.core.config import get_settings
from app.schemas.llm import LLMRequest, LLMResponse, LLMChunk
from app.services.llm.providers.base import LLMProvider

litellm.suppress_debug_info = True

logger = structlog.get_logger(__name__)


def _extract_content(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        logger.warning("vllm_completion_empty_choices")
        return ""
    msg = getattr(choices[0], "message", None)
    if msg is None:
        return ""
    return getattr(msg, "content", None) or ""


def _extract_stream_delta(chunk: Any) -> str | None:
    choices = getattr(chunk, "choices", None)
    if not choices:
        return None
    try:
        delta_obj = getattr(choices[0], "delta", None)
    except (IndexError, TypeError):
        return None
    if delta_obj is None:
        return None
    return getattr(delta_obj, "content", None)


def _extract_usage(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0


class VLLMProvider(LLMProvider):
    def __init__(
        self,
        api_base: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
    ) -> None:
        settings = get_settings()
        self._api_base = api_base or settings.text_model.text_vllm_base_url
        self._model = model or settings.text_model.text_vllm_model
        self._api_key = api_key or (getattr(settings.text_model, "vllm_api_key", "") or "").strip() or "EMPTY"
        self._timeout = timeout or settings.text_model.text_timeout

    async def generate(self, request: LLMRequest) -> LLMResponse:
        model_id = request.model or self._model
        api_base = self._api_base
        if not api_base:
            raise AppError(ErrorCode.CLOUD_MODEL_ERROR, "配置错误：vLLM 需要设置 TEXT_VLLM_BASE_URL")

        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        start = time.monotonic()
        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=f"openai/{model_id}",
                    messages=messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    api_base=api_base,
                    api_key=self._api_key,
                    stream=False,
                ),
                timeout=request.timeout or self._timeout,
            )
            content = _extract_content(response)
            input_tokens, output_tokens = _extract_usage(response)
            elapsed = time.monotonic() - start

            logger.info(
                "vllm_generate_completed",
                model=model_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                elapsed_ms=round(elapsed * 1000, 2),
                stream=False,
            )

            return LLMResponse(
                content=content,
                model=model_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=str(getattr(response.choices[0], "finish_reason", ""))
                if response.choices
                else "",
                metadata=request.metadata,
            )
        except asyncio.TimeoutError:
            raise AppError(ErrorCode.MODEL_TIMEOUT, "模型调用超时")
        except AppError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "vllm_generate_failed",
                model=model_id,
                elapsed_ms=round(elapsed * 1000, 2),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise AppError(ErrorCode.LOCAL_MODEL_UNAVAILABLE, "模型服务不可用") from exc

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        model_id = request.model or self._model
        api_base = self._api_base
        if not api_base:
            raise AppError(ErrorCode.CLOUD_MODEL_ERROR, "配置错误：vLLM 需要设置 TEXT_VLLM_BASE_URL")

        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        timeout = request.timeout or self._timeout
        idle_timeout = max(timeout * 0.5, 30)

        start = time.monotonic()
        try:
            try:
                response = await asyncio.wait_for(
                    litellm.acompletion(
                        model=f"openai/{model_id}",
                        messages=messages,
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                        api_base=api_base,
                        api_key=self._api_key,
                        stream=True,
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise AppError(ErrorCode.MODEL_TIMEOUT, "模型调用超时")

            input_tokens: int | None = None
            output_tokens: int | None = None
            finish_reason: str | None = None

            while True:
                try:
                    chunk = await asyncio.wait_for(
                        response.__anext__(),
                        timeout=idle_timeout,
                    )
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    raise AppError(ErrorCode.MODEL_TIMEOUT, "模型调用超时")

                delta = _extract_stream_delta(chunk)
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    input_tokens = getattr(chunk_usage, "prompt_tokens", None)
                    output_tokens = getattr(chunk_usage, "completion_tokens", None)

                chunk_finish = None
                if chunk.choices:
                    fr = getattr(chunk.choices[0], "finish_reason", None)
                    if fr is not None:
                        chunk_finish = str(fr)
                        finish_reason = chunk_finish

                if delta or chunk_finish:
                    yield LLMChunk(
                        content=delta,
                        finish_reason=chunk_finish,
                        input_tokens=None,
                        output_tokens=None,
                    )

            elapsed = time.monotonic() - start
            logger.info(
                "vllm_stream_completed",
                model=model_id,
                elapsed_ms=round(elapsed * 1000, 2),
                stream=True,
            )

            yield LLMChunk(
                content=None,
                finish_reason=finish_reason or "stop",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except AppError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "vllm_stream_failed",
                model=model_id,
                elapsed_ms=round(elapsed * 1000, 2),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise AppError(ErrorCode.LOCAL_MODEL_UNAVAILABLE, "模型服务不可用") from exc