"""Prometheus metrics registry — global kernel layer (core/).

Exposes 10 metrics as declared in API_CONTRACT.md §Observability.
All helpers are no-ops if prometheus_client is unavailable (defensive).
"""

from __future__ import annotations

import time
from typing import Any

try:
    from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
    _PROMETHEUS_AVAILABLE = True
except Exception:  # pragma: no cover
    _PROMETHEUS_AVAILABLE = False

from app.core.logging import get_logger

logger = get_logger("core.metrics")

# ---------------------------------------------------------------------------
# Registry singleton
# ---------------------------------------------------------------------------

_registry: Any | None = None


def get_registry() -> Any:
    """Return the global Prometheus CollectorRegistry (lazy init)."""
    global _registry
    if _registry is None:
        if _PROMETHEUS_AVAILABLE:
            _registry = CollectorRegistry()
        else:
            _registry = None
    return _registry


# ---------------------------------------------------------------------------
# Metric definitions (aligned with API_CONTRACT.md)
# ---------------------------------------------------------------------------

_llm_request_total: Any | None = None
_llm_request_duration_seconds: Any | None = None
_llm_tokens_total: Any | None = None
_llm_circuit_breaker_state: Any | None = None
_http_request_total: Any | None = None
_http_request_duration_seconds: Any | None = None
_kb_document_count: Any | None = None
_kb_query_duration_seconds: Any | None = None
_agent_step_total: Any | None = None
_agent_step_duration_seconds: Any | None = None


def _init_metrics() -> None:
    """Lazy-init all metric objects."""
    global _llm_request_total
    global _llm_request_duration_seconds
    global _llm_tokens_total
    global _llm_circuit_breaker_state
    global _http_request_total
    global _http_request_duration_seconds
    global _kb_document_count
    global _kb_query_duration_seconds
    global _agent_step_total
    global _agent_step_duration_seconds
    if not _PROMETHEUS_AVAILABLE:
        return

    reg = get_registry()

    _llm_request_total = Counter(
        "llm_request_total",
        "Total LLM calls",
        ["provider", "model", "task_type"],
        registry=reg,
    )
    _llm_request_duration_seconds = Histogram(
        "llm_request_duration_seconds",
        "LLM call latency in seconds",
        ["provider", "model"],
        registry=reg,
    )
    _llm_tokens_total = Counter(
        "llm_tokens_total",
        "Token consumption by LLM calls",
        ["provider", "model", "direction"],
        registry=reg,
    )
    _llm_circuit_breaker_state = Gauge(
        "llm_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=open, 2=half_open)",
        ["provider", "channel"],
        registry=reg,
    )
    _http_request_total = Counter(
        "http_request_total",
        "Total HTTP requests",
        ["method", "path", "status"],
        registry=reg,
    )
    _http_request_duration_seconds = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "path"],
        registry=reg,
    )
    _kb_document_count = Gauge(
        "kb_document_count",
        "Number of documents per collection",
        ["collection"],
        registry=reg,
    )
    _kb_query_duration_seconds = Histogram(
        "kb_query_duration_seconds",
        "KB query latency in seconds",
        ["collection", "strategy"],
        registry=reg,
    )
    _agent_step_total = Counter(
        "agent_step_total",
        "Total agent execution steps",
        ["agent_name", "agent_type"],
        registry=reg,
    )
    _agent_step_duration_seconds = Histogram(
        "agent_step_duration_seconds",
        "Agent single-step latency in seconds",
        ["agent_name"],
        registry=reg,
    )


def _ensure_metrics() -> None:
    if _llm_request_total is None:
        _init_metrics()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def record_llm_call(
    *,
    provider: str,
    model: str,
    task_type: str,
    duration: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Record a completed LLM call (success or failure — caller decides)."""
    _ensure_metrics()
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        _llm_request_total.labels(provider=provider, model=model, task_type=task_type).inc()
        _llm_request_duration_seconds.labels(provider=provider, model=model).observe(duration)
        if input_tokens:
            _llm_tokens_total.labels(provider=provider, model=model, direction="input").inc(input_tokens)
        if output_tokens:
            _llm_tokens_total.labels(provider=provider, model=model, direction="output").inc(output_tokens)
    except Exception as exc:
        logger.warning("metrics.record_llm_call_failed", error=str(exc))


def record_circuit_breaker_state(*, channel: str, state_value: int, provider: str = "") -> None:
    """Record circuit breaker state (0=closed, 1=open, 2=half_open)."""
    _ensure_metrics()
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        _llm_circuit_breaker_state.labels(provider=provider, channel=channel).set(state_value)
    except Exception as exc:
        logger.warning("metrics.record_cb_state_failed", error=str(exc))


def record_http_request(*, method: str, path: str, status: int, duration: float) -> None:
    """Record a completed HTTP request."""
    _ensure_metrics()
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        _http_request_total.labels(method=method, path=path, status=str(status)).inc()
        _http_request_duration_seconds.labels(method=method, path=path).observe(duration)
    except Exception as exc:
        logger.warning("metrics.record_http_request_failed", error=str(exc))


def record_kb_document_count(*, collection: str, count: int) -> None:
    """Record document count for a collection."""
    _ensure_metrics()
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        _kb_document_count.labels(collection=collection).set(count)
    except Exception as exc:
        logger.warning("metrics.record_kb_doc_count_failed", error=str(exc))


def record_kb_query(*, collection: str, strategy: str, duration: float) -> None:
    """Record KB query latency."""
    _ensure_metrics()
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        _kb_query_duration_seconds.labels(collection=collection, strategy=strategy).observe(duration)
    except Exception as exc:
        logger.warning("metrics.record_kb_query_failed", error=str(exc))


def record_agent_step(*, agent_name: str, agent_type: str, duration: float) -> None:
    """Record a single agent step."""
    _ensure_metrics()
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        _agent_step_total.labels(agent_name=agent_name, agent_type=agent_type).inc()
        _agent_step_duration_seconds.labels(agent_name=agent_name).observe(duration)
    except Exception as exc:
        logger.warning("metrics.record_agent_step_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Prometheus exposition
# ---------------------------------------------------------------------------

def get_metrics_response() -> tuple[bytes, str]:
    """Return (body_bytes, content_type) for the /metrics endpoint."""
    _ensure_metrics()
    if not _PROMETHEUS_AVAILABLE:
        return b"# Prometheus client unavailable\n", "text/plain"
    try:
        body = generate_latest(get_registry())
        return body, CONTENT_TYPE_LATEST
    except Exception as exc:
        logger.error("metrics.generate_latest_failed", error=str(exc))
        return f"# Error generating metrics: {exc}\n".encode(), "text/plain"
