"""Tests for F18: Observability (Tracing + Token stats + Metrics).

Coverage:
- 10 Prometheus metrics exist and have correct type/labels
- LLM gateway records metrics on generate/generate_stream
- HTTP middleware records request count + latency
- KB operations record query latency + document count
- Agent steps record step count + latency
- /metrics endpoint returns valid Prometheus text
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agent.react import ReactAgent
from app.core.di import container
from app.core.errors import ErrorCode
from app.infra.circuit_breaker import CircuitBreaker, CircuitState, reset_circuit_breakers
from app.main import app
from app.schemas.llm import LLMChunk, LLMRequest, LLMResponse
from app.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_di():
    """Reset DI container and circuit breakers between tests."""
    container.reset()
    reset_circuit_breakers()
    yield
    container.reset()
    reset_circuit_breakers()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_provider():
    """Return a mock LLM provider with async generate/generate_stream."""
    provider = MagicMock()
    provider.generate = AsyncMock()
    provider.generate_stream = AsyncMock()
    return provider


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------

def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "text/plain" in content_type or "prometheus" in content_type


def test_metrics_contains_all_declared_metrics(client: TestClient) -> None:
    """Verify all 10 declared metric names appear in /metrics output."""
    response = client.get("/metrics")
    text = response.text
    expected_names = [
        "llm_request_total",
        "llm_request_duration_seconds",
        "llm_tokens_total",
        "llm_circuit_breaker_state",
        "http_request_total",
        "http_request_duration_seconds",
        "kb_document_count",
        "kb_query_duration_seconds",
        "agent_step_total",
        "agent_step_duration_seconds",
    ]
    for name in expected_names:
        assert name in text, f"Metric {name} missing from /metrics"


# ---------------------------------------------------------------------------
# HTTP metrics via middleware
# ---------------------------------------------------------------------------

def test_http_request_metrics_recorded(client: TestClient) -> None:
    """A GET to /api/v1/health should produce http_request_total and http_request_duration_seconds."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    metrics_resp = client.get("/metrics")
    text = metrics_resp.text
    assert 'http_request_total{method="GET",path="/api/v1/health",status="200"}' in text or \
           'http_request_total{method="GET",path="/api/v1/health",status="200"} ' in text or \
           re.search(r'http_request_total\{method="GET",path="/api/v1/health",status="200"\}\s+\d+', text)
    assert "http_request_duration_seconds_bucket{" in text or \
           "http_request_duration_seconds_sum{" in text


# ---------------------------------------------------------------------------
# LLM gateway metrics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_generate_records_metrics(mock_provider: Any) -> None:
    from app.services.llm.gateway import LLMGateway
    from app.services.llm.router import LLMRouter

    # Setup
    mock_provider.generate.return_value = LLMResponse(
        content="hello",
        model="qwen-plus",
        input_tokens=10,
        output_tokens=5,
    )

    router = LLMRouter()
    router.select_provider = MagicMock(return_value=mock_provider)
    router.select_fallback_provider = MagicMock(return_value=None)

    gateway = LLMGateway(router=router)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="qwen-plus")

    response = await gateway.generate(request)
    assert response.input_tokens == 10
    assert response.output_tokens == 5

    # Verify metrics were recorded via checking /metrics endpoint
    client = TestClient(app)
    metrics_resp = client.get("/metrics")
    text = metrics_resp.text
    assert "llm_request_total{" in text
    assert "llm_request_duration_seconds_sum{" in text
    assert "llm_tokens_total{" in text


@pytest.mark.asyncio
async def test_llm_generate_stream_records_metrics(mock_provider: Any) -> None:
    from app.services.llm.gateway import LLMGateway
    from app.services.llm.router import LLMRouter

    async def _mock_stream(request):
        yield LLMChunk(content="hello", input_tokens=8, output_tokens=4)
        yield LLMChunk(content=" world", input_tokens=8, output_tokens=4)

    mock_provider.generate_stream = _mock_stream

    router = LLMRouter()
    router.select_provider = MagicMock(return_value=mock_provider)
    router.select_fallback_provider = MagicMock(return_value=None)

    gateway = LLMGateway(router=router)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="qwen-plus", stream=True)

    chunks = []
    async for chunk in gateway.generate_stream(request):
        chunks.append(chunk)

    assert len(chunks) == 2

    client = TestClient(app)
    metrics_resp = client.get("/metrics")
    text = metrics_resp.text
    assert "llm_request_total{" in text
    assert "llm_tokens_total{" in text


@pytest.mark.asyncio
async def test_llm_generate_failure_records_metrics(mock_provider: Any) -> None:
    from app.services.llm.gateway import LLMGateway
    from app.services.llm.router import LLMRouter

    mock_provider.generate.side_effect = Exception("model error")

    router = LLMRouter()
    router.select_provider = MagicMock(return_value=mock_provider)
    router.select_fallback_provider = MagicMock(return_value=None)

    gateway = LLMGateway(router=router)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="qwen-plus")

    with pytest.raises(Exception):
        await gateway.generate(request)

    client = TestClient(app)
    metrics_resp = client.get("/metrics")
    text = metrics_resp.text
    assert "llm_request_total{" in text


# ---------------------------------------------------------------------------
# Circuit breaker state metric
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_breaker_state_metric(mock_provider: Any) -> None:
    from app.services.llm.gateway import LLMGateway
    from app.services.llm.router import LLMRouter

    mock_provider.generate.return_value = LLMResponse(
        content="ok",
        model="qwen-plus",
        input_tokens=1,
        output_tokens=1,
    )

    router = LLMRouter()
    router.select_provider = MagicMock(return_value=mock_provider)
    router.select_fallback_provider = MagicMock(return_value=None)

    gateway = LLMGateway(router=router)
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="qwen-plus")

    await gateway.generate(request)

    client = TestClient(app)
    metrics_resp = client.get("/metrics")
    text = metrics_resp.text
    assert "llm_circuit_breaker_state{" in text


# ---------------------------------------------------------------------------
# Agent step metrics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_step_metrics() -> None:
    registry = ToolRegistry()

    async def _think_fn(user_input, history, context):
        return (f"thought: {user_input}", None, MagicMock(input_tokens=3, output_tokens=2))

    agent = ReactAgent(
        name="test_agent",
        tool_registry=registry,
        max_iterations=3,
        think_fn=_think_fn,
    )

    result = await agent.run("hello")
    assert result.content == "thought: hello"

    client = TestClient(app)
    metrics_resp = client.get("/metrics")
    text = metrics_resp.text
    assert 'agent_step_total{agent_name="test_agent",agent_type="react"}' in text or \
           re.search(r'agent_step_total\{agent_name="test_agent",agent_type="react"\}\s+\d+', text)
    assert "agent_step_duration_seconds_sum{" in text


# ---------------------------------------------------------------------------
# KB metrics (integration-style via mocks)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kb_query_metric_recorded() -> None:
    """KB query latency metric should appear after a search call."""
    from app.infra.vector_store.qdrant_store import QdrantVectorStore
    from app.schemas.vector_store import SearchResult

    store = QdrantVectorStore(url="http://fake:6333")
    # Mock the Qdrant client to avoid network calls
    fake_client = AsyncMock()
    fake_response = MagicMock()
    fake_response.points = []
    fake_client.query_points = AsyncMock(return_value=fake_response)
    fake_client.collection_exists = AsyncMock(return_value=True)
    store._client = fake_client

    await store.search("test_collection", [0.1, 0.2, 0.3])

    client = TestClient(app)
    metrics_resp = client.get("/metrics")
    text = metrics_resp.text
    assert "kb_query_duration_seconds_sum{" in text


@pytest.mark.asyncio
async def test_kb_document_count_metric_recorded() -> None:
    from app.infra.vector_store.qdrant_store import QdrantVectorStore

    store = QdrantVectorStore(url="http://fake:6333")
    fake_client = AsyncMock()
    fake_info = MagicMock()
    fake_info.config.params.vectors.size = 768
    fake_info.status = "green"
    fake_info.points_count = 42
    fake_client.get_collection = AsyncMock(return_value=fake_info)
    fake_client.collection_exists = AsyncMock(return_value=True)
    store._client = fake_client

    info = await store.get_collection_info("test_collection")
    assert info is not None
    assert info["points_count"] == 42

    client = TestClient(app)
    metrics_resp = client.get("/metrics")
    text = metrics_resp.text
    assert 'kb_document_count{collection="test_collection"} 42' in text


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------

def test_metrics_module_graceful_without_prometheus() -> None:
    """If prometheus_client is unavailable, helpers should not crash."""
    with patch("app.core.metrics._PROMETHEUS_AVAILABLE", False):
        from app.core.metrics import record_llm_call, record_http_request, record_agent_step
        # These should not raise
        record_llm_call(provider="p", model="m", task_type="t", duration=0.1)
        record_http_request(method="GET", path="/", status=200, duration=0.01)
        record_agent_step(agent_name="a", agent_type="react", duration=0.05)
