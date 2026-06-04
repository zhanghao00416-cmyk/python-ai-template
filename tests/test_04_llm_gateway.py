from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import AppError, ErrorCode, SystemError
from app.infra.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_circuit_breaker,
    reset_circuit_breakers,
)
from app.infra.semaphore_manager import (
    SemaphoreManager,
    reset_semaphore_manager,
)
from app.schemas.llm import LLMRequest, LLMResponse, LLMChunk, Message
from app.services.llm.gateway import LLMGateway
from app.services.llm.providers.base import LLMProvider
from app.services.llm.providers.qwen_cloud import QwenCloudProvider
from app.services.llm.providers.vllm import VLLMProvider
from app.services.llm.router import LLMRouter, reset_routing_cache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_state():
    reset_circuit_breakers()
    reset_semaphore_manager()
    reset_routing_cache()
    yield
    reset_circuit_breakers()
    reset_semaphore_manager()
    reset_routing_cache()


def _make_request(task_type: str = "chat", stream: bool = False, model: str | None = None) -> LLMRequest:
    return LLMRequest(
        messages=[Message(role="user", content="hello")],
        task_type=task_type,
        stream=stream,
        model=model,
    )


class _OkProvider(LLMProvider):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="world",
            model=request.model or "test-model",
            input_tokens=5,
            output_tokens=1,
            finish_reason="stop",
        )

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        yield LLMChunk(content="wor", finish_reason=None)
        yield LLMChunk(content="ld", finish_reason=None)
        yield LLMChunk(content=None, finish_reason="stop", input_tokens=5, output_tokens=2)


class _FailProvider(LLMProvider):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("provider error")

    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        raise RuntimeError("provider stream error")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TestLLMSchemas:
    def test_message_creation(self):
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"

    def test_llm_request_defaults(self):
        r = LLMRequest(messages=[Message(role="user", content="hi")])
        assert r.task_type == "chat"
        assert r.stream is False
        assert r.model is None
        assert r.temperature == 0.7
        assert r.max_tokens == 4096
        assert r.timeout == 30.0
        assert r.metadata == {}

    def test_llm_request_with_model(self):
        r = LLMRequest(messages=[Message(role="user", content="hi")], model="qwen-plus")
        assert r.model == "qwen-plus"

    def test_llm_response(self):
        r = LLMResponse(content="answer", model="qwen-plus", input_tokens=10, output_tokens=5)
        assert r.content == "answer"
        assert r.input_tokens == 10

    def test_llm_chunk(self):
        c = LLMChunk(content="delta", finish_reason=None)
        assert c.content == "delta"
        assert c.finish_reason is None

    def test_llm_chunk_final(self):
        c = LLMChunk(content=None, finish_reason="stop", input_tokens=10, output_tokens=5)
        assert c.input_tokens == 10
        assert c.output_tokens == 5


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        cb = CircuitBreaker("test_cb")
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_allow_request_when_closed(self):
        cb = CircuitBreaker("test_cb")
        assert await cb.allow_request() is True

    @pytest.mark.asyncio
    async def test_transitions_to_open_after_threshold(self):
        cb = CircuitBreaker("test_cb", failure_threshold=3)
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_rejects_request_when_open(self):
        cb = CircuitBreaker("test_cb", failure_threshold=2)
        await cb.record_failure()
        await cb.record_failure()
        assert await cb.allow_request() is False

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker("test_cb", failure_threshold=1, recovery_timeout=0.01)
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(0.02)
        state = await cb._check_state()
        assert state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_allows_limited_requests(self):
        cb = CircuitBreaker("test_cb", failure_threshold=1, recovery_timeout=0.01, half_open_max_calls=1)
        await cb.record_failure()
        await asyncio.sleep(0.02)
        assert await cb.allow_request() is True
        assert await cb.allow_request() is False

    @pytest.mark.asyncio
    async def test_success_closes_from_half_open(self):
        cb = CircuitBreaker("test_cb", failure_threshold=1, recovery_timeout=0.01)
        await cb.record_failure()
        await asyncio.sleep(0.02)
        await cb.allow_request()
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_reopens_from_half_open(self):
        cb = CircuitBreaker("test_cb", failure_threshold=1, recovery_timeout=0.01)
        await cb.record_failure()
        await asyncio.sleep(0.02)
        await cb.allow_request()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_registry_returns_same_instance(self):
        cb1 = get_circuit_breaker("llm_text")
        cb2 = get_circuit_breaker("llm_text")
        assert cb1 is cb2

    @pytest.mark.asyncio
    async def test_registry_creates_different_instances(self):
        cb1 = get_circuit_breaker("llm_text")
        cb2 = get_circuit_breaker("llm_vllm")
        assert cb1 is not cb2

    @pytest.mark.asyncio
    async def test_reset_clears_registry(self):
        get_circuit_breaker("test_reset")
        reset_circuit_breakers()
        from app.infra.circuit_breaker import _registry
        assert len(_registry) == 0


# ---------------------------------------------------------------------------
# Semaphore Manager
# ---------------------------------------------------------------------------

class TestSemaphoreManager:
    def test_initialize(self):
        mgr = SemaphoreManager()
        mgr.initialize(llm=5, multimodal=3, embedding=10, acquire_timeout=60.0)
        assert mgr._initialized is True
        assert "llm" in mgr._semaphores

    def test_initialize_idempotent(self):
        mgr = SemaphoreManager()
        mgr.initialize(llm=5, multimodal=3, embedding=10)
        mgr.initialize(llm=10, multimodal=20, embedding=30)
        assert mgr._semaphores["llm"]._value == 5

    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        mgr = SemaphoreManager()
        mgr.initialize(llm=2, multimodal=1, embedding=5, acquire_timeout=5.0)
        async with mgr.acquire("llm"):
            assert mgr._semaphores["llm"]._value == 1

    @pytest.mark.asyncio
    async def test_acquire_unknown_name_raises(self):
        mgr = SemaphoreManager()
        mgr.initialize()
        with pytest.raises(ValueError, match="Unknown semaphore"):
            async with mgr.acquire("unknown"):
                pass

    @pytest.mark.asyncio
    async def test_acquire_timeout_raises_app_error(self):
        mgr = SemaphoreManager()
        mgr.initialize(llm=1, multimodal=1, embedding=1, acquire_timeout=0.01)
        async with mgr.acquire("llm"):
            with pytest.raises(AppError) as exc_info:
                async with mgr.acquire("llm"):
                    pass
            assert exc_info.value.code == ErrorCode.TIMEOUT_ERROR


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class TestLLMRouter:
    def test_select_provider_chat_default(self):
        router = LLMRouter()
        provider = router.select_provider("chat")
        assert isinstance(provider, QwenCloudProvider)

    def test_select_provider_with_model_override(self):
        router = LLMRouter()
        provider = router.select_provider("chat", model="qwen-max")
        assert isinstance(provider, QwenCloudProvider)

    def test_select_provider_embedding(self):
        router = LLMRouter()
        provider = router.select_provider("embedding")
        assert isinstance(provider, QwenCloudProvider)

    @patch("app.services.llm.router.VLLMProvider")
    def test_fallback_provider_for_qwen_cloud(self, mock_vllm_cls):
        router = LLMRouter()
        fallback = router.select_fallback_provider("chat")
        assert fallback is not None

    def test_fallback_provider_multimodal_returns_none(self):
        router = LLMRouter()
        fallback = router.select_fallback_provider("multimodal")
        assert fallback is None

    def test_routing_cache_reset(self):
        reset_routing_cache()
        from app.services.llm.router import _ROUTING_CACHE
        assert _ROUTING_CACHE is None


# ---------------------------------------------------------------------------
# Gateway — non-stream
# ---------------------------------------------------------------------------

class TestLLMGatewayNonStream:
    @pytest.mark.asyncio
    async def test_generate_success(self):
        router = LLMRouter()
        router.select_provider = MagicMock(return_value=_OkProvider())
        sem = SemaphoreManager()
        sem.initialize(llm=20, multimodal=10, embedding=20, acquire_timeout=120.0)
        gateway = LLMGateway(router=router, sem_manager=sem)
        request = _make_request(task_type="chat")
        response = await gateway.generate(request)
        assert response.content == "world"

    @pytest.mark.asyncio
    async def test_generate_circuit_breaker_fallback(self):
        cb_text = get_circuit_breaker("llm_text", failure_threshold=1)
        await cb_text.record_failure()
        await cb_text.record_failure()
        assert cb_text.state == CircuitState.OPEN

        primary = MagicMock(spec=QwenCloudProvider)
        primary.generate = AsyncMock(return_value=LLMResponse(content="primary", model="qwen"))
        fallback = MagicMock(spec=VLLMProvider)
        fallback.generate = AsyncMock(return_value=LLMResponse(content="fallback", model="vllm"))

        router = LLMRouter()
        router.select_provider = MagicMock(return_value=primary)
        router.select_fallback_provider = MagicMock(return_value=fallback)

        sem = SemaphoreManager()
        sem.initialize(llm=20, multimodal=10, embedding=20, acquire_timeout=120.0)
        gateway = LLMGateway(router=router, sem_manager=sem)
        request = _make_request(task_type="chat")
        response = await gateway.generate(request)
        assert response.content == "fallback"

    @pytest.mark.asyncio
    async def test_generate_both_circuits_open_raises(self):
        cb_text = get_circuit_breaker("llm_text", failure_threshold=1)
        cb_vllm = get_circuit_breaker("llm_vllm", failure_threshold=1)
        for _ in range(5):
            await cb_text.record_failure()
            await cb_vllm.record_failure()

        router = LLMRouter()
        router.select_provider = MagicMock(return_value=_OkProvider())
        router.select_fallback_provider = MagicMock(return_value=_OkProvider())

        sem = SemaphoreManager()
        sem.initialize(llm=20, multimodal=10, embedding=20, acquire_timeout=120.0)
        gateway = LLMGateway(router=router, sem_manager=sem)
        request = _make_request(task_type="chat")

        with pytest.raises(AppError) as exc_info:
            await gateway.generate(request)
        assert exc_info.value.code == ErrorCode.SERVICE_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_generate_multimodal_no_fallback_raises(self):
        cb_mm = get_circuit_breaker("multimodal", failure_threshold=1)
        for _ in range(5):
            await cb_mm.record_failure()

        router = LLMRouter()
        router.select_provider = MagicMock(return_value=_OkProvider())
        router.select_fallback_provider = MagicMock(return_value=None)

        sem = SemaphoreManager()
        sem.initialize(llm=20, multimodal=10, embedding=20, acquire_timeout=120.0)
        gateway = LLMGateway(router=router, sem_manager=sem)
        request = _make_request(task_type="multimodal")

        with pytest.raises(AppError) as exc_info:
            await gateway.generate(request)
        assert exc_info.value.code in (ErrorCode.CLOUD_MODEL_ERROR, ErrorCode.LOCAL_MODEL_UNAVAILABLE)

    @pytest.mark.asyncio
    async def test_generate_provider_failure_recorded(self):
        cb_text = get_circuit_breaker("llm_text", failure_threshold=5)
        assert cb_text.state == CircuitState.CLOSED

        fail_provider = MagicMock(spec=QwenCloudProvider)
        fail_provider.generate = AsyncMock(side_effect=RuntimeError("provider error"))

        router = LLMRouter()
        router.select_provider = MagicMock(return_value=fail_provider)
        router.select_fallback_provider = MagicMock(return_value=None)

        sem = SemaphoreManager()
        sem.initialize(llm=20, multimodal=10, embedding=20, acquire_timeout=120.0)
        gateway = LLMGateway(router=router, sem_manager=sem)
        request = _make_request(task_type="chat")

        with pytest.raises(AppError):
            await gateway.generate(request)

        assert cb_text._failure_count >= 1


# ---------------------------------------------------------------------------
# Gateway — stream
# ---------------------------------------------------------------------------

class TestLLMGatewayStream:
    @pytest.mark.asyncio
    async def test_generate_stream_yields_chunks(self):
        router = LLMRouter()
        router.select_provider = MagicMock(return_value=_OkProvider())
        sem = SemaphoreManager()
        sem.initialize(llm=20, multimodal=10, embedding=20, acquire_timeout=120.0)
        gateway = LLMGateway(router=router, sem_manager=sem)
        request = _make_request(task_type="chat", stream=True)

        chunks = []
        async for chunk in gateway.generate_stream(request):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0].content == "wor"
        assert chunks[1].content == "ld"
        assert chunks[2].finish_reason == "stop"
        assert chunks[2].input_tokens == 5

    @pytest.mark.asyncio
    async def test_generate_stream_circuit_open_fallback(self):
        cb_text = get_circuit_breaker("llm_text", failure_threshold=1)
        for _ in range(5):
            await cb_text.record_failure()

        async def _stream_fallback(request):
            yield LLMChunk(content="fb", finish_reason=None)
            yield LLMChunk(content=None, finish_reason="stop", input_tokens=1, output_tokens=1)

        primary = MagicMock(spec=QwenCloudProvider)
        fallback = MagicMock(spec=VLLMProvider)
        fallback.generate_stream = _stream_fallback

        router = LLMRouter()
        router.select_provider = MagicMock(return_value=primary)
        router.select_fallback_provider = MagicMock(return_value=fallback)

        sem = SemaphoreManager()
        sem.initialize(llm=20, multimodal=10, embedding=20, acquire_timeout=120.0)
        gateway = LLMGateway(router=router, sem_manager=sem)
        request = _make_request(task_type="chat", stream=True)

        chunks = []
        async for chunk in gateway.generate_stream(request):
            chunks.append(chunk)
        assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_generate_stream_failure_raises(self):
        cb = get_circuit_breaker("llm_text", failure_threshold=5)
        router = LLMRouter()
        router.select_provider = MagicMock(return_value=_FailProvider())
        router.select_fallback_provider = MagicMock(return_value=None)

        sem = SemaphoreManager()
        sem.initialize(llm=20, multimodal=10, embedding=20, acquire_timeout=120.0)
        gateway = LLMGateway(router=router, sem_manager=sem)
        request = _make_request(task_type="chat", stream=True)

        with pytest.raises(AppError):
            async for _ in gateway.generate_stream(request):
                pass


# ---------------------------------------------------------------------------
# Provider integration (mocked litellm)
# ---------------------------------------------------------------------------

class TestQwenCloudProvider:
    @pytest.mark.asyncio
    @patch("app.services.llm.providers.qwen_cloud.litellm.acompletion")
    async def test_generate_success(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "hello response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
        mock_completion.return_value = mock_response

        provider = QwenCloudProvider(api_key="test-key", api_base="http://test", default_model="qwen-test")
        request = _make_request()
        response = await provider.generate(request)
        assert response.content == "hello response"
        assert response.input_tokens == 5

    @pytest.mark.asyncio
    @patch("app.services.llm.providers.qwen_cloud.litellm.acompletion")
    async def test_generate_timeout_raises_model_timeout(self, mock_completion):
        mock_completion.side_effect = asyncio.TimeoutError()
        provider = QwenCloudProvider(api_key="test-key", api_base="http://test", default_model="qwen-test")
        request = _make_request()
        with pytest.raises(AppError) as exc_info:
            await provider.generate(request)
        assert exc_info.value.code == ErrorCode.MODEL_TIMEOUT

    @pytest.mark.asyncio
    @patch("app.services.llm.providers.qwen_cloud.litellm.acompletion")
    async def test_generate_failure_raises_cloud_error(self, mock_completion):
        mock_completion.side_effect = Exception("api error")
        provider = QwenCloudProvider(api_key="test-key", api_base="http://test", default_model="qwen-test")
        request = _make_request()
        with pytest.raises(AppError) as exc_info:
            await provider.generate(request)
        assert exc_info.value.code == ErrorCode.CLOUD_MODEL_ERROR


class TestVLLMProvider:
    @pytest.mark.asyncio
    @patch("app.services.llm.providers.vllm.litellm.acompletion")
    async def test_generate_success(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "vllm response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=3)
        mock_completion.return_value = mock_response

        provider = VLLMProvider(api_base="http://localhost:8000", model="test-model", api_key="EMPTY")
        request = _make_request()
        response = await provider.generate(request)
        assert response.content == "vllm response"

    @pytest.mark.asyncio
    @patch("app.services.llm.providers.vllm.litellm.acompletion")
    async def test_generate_missing_base_url_raises(self, mock_completion):
        provider = VLLMProvider(api_base="", model="test-model", api_key="EMPTY")
        request = _make_request()
        with pytest.raises(AppError) as exc_info:
            await provider.generate(request)
        assert exc_info.value.code in (ErrorCode.CLOUD_MODEL_ERROR, ErrorCode.LOCAL_MODEL_UNAVAILABLE)

    @pytest.mark.asyncio
    @patch("app.services.llm.providers.vllm.litellm.acompletion")
    async def test_generate_timeout_raises(self, mock_completion):
        mock_completion.side_effect = asyncio.TimeoutError()
        provider = VLLMProvider(api_base="http://localhost:8000", model="test-model", api_key="EMPTY")
        request = _make_request()
        with pytest.raises(AppError) as exc_info:
            await provider.generate(request)
        assert exc_info.value.code == ErrorCode.MODEL_TIMEOUT

    @pytest.mark.asyncio
    @patch("app.services.llm.providers.vllm.litellm.acompletion")
    async def test_generate_failure_raises_local_unavailable(self, mock_completion):
        mock_completion.side_effect = Exception("connection refused")
        provider = VLLMProvider(api_base="http://localhost:8000", model="test-model", api_key="EMPTY")
        request = _make_request()
        with pytest.raises(AppError) as exc_info:
            await provider.generate(request)
        assert exc_info.value.code == ErrorCode.LOCAL_MODEL_UNAVAILABLE


# ---------------------------------------------------------------------------
# Error code mapping
# ---------------------------------------------------------------------------

class TestErrorCodeMapping:
    def test_make_error_model_timeout_is_system_error(self):
        from app.core.errors import make_error
        err = make_error(1101, "timeout")
        assert isinstance(err, SystemError)
        assert err.code == 1101

    def test_make_error_cloud_model_is_system_error(self):
        from app.core.errors import make_error
        err = make_error(1104, "cloud failed")
        assert isinstance(err, SystemError)
        assert err.code == 1104

    def test_make_error_local_model_is_system_error(self):
        from app.core.errors import make_error
        err = make_error(1102, "local failed")
        assert isinstance(err, SystemError)
        assert err.code == 1102

    def test_format_error_code_model_codes(self):
        from app.core.errors import format_error_code
        assert format_error_code(ErrorCode.MODEL_TIMEOUT) == "AI_1101"
        assert format_error_code(ErrorCode.LOCAL_MODEL_UNAVAILABLE) == "AI_1102"
        assert format_error_code(ErrorCode.MODEL_FORMAT_ERROR) == "AI_1103"
        assert format_error_code(ErrorCode.CLOUD_MODEL_ERROR) == "AI_1104"

    def test_timeout_error_for_semaphore(self):
        from app.core.errors import make_error
        err = make_error(ErrorCode.TIMEOUT_ERROR, "semaphore acquire timed out")
        assert err.code == 4
        assert isinstance(err, SystemError)


# ---------------------------------------------------------------------------
# AppError domain mapping for 11xx
# ---------------------------------------------------------------------------

class TestMakeError11xx:
    def test_1101_maps_to_system_error(self):
        from app.core.errors import make_error
        err = make_error(1101, "timeout")
        assert isinstance(err, SystemError)

    def test_1102_maps_to_system_error(self):
        from app.core.errors import make_error
        err = make_error(1102, "local unavailable")
        assert isinstance(err, SystemError)

    def test_1104_maps_to_system_error(self):
        from app.core.errors import make_error
        err = make_error(1104, "cloud error")
        assert isinstance(err, SystemError)