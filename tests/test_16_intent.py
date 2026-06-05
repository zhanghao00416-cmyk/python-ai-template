"""Tests for F16: Intent classification domain."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import ErrorCode, IntentError
from app.domain.intent.service import (
    IntentDomainService,
    KeywordMatcher,
    LLMClassifier,
    SimilarityMatcher,
    _cosine_similarity,
    _parse_llm_json,
)
from app.schemas.intent import IntentResultData, SubIntent
from app.schemas.llm import LLMResponse


# ===========================================================================
# Helpers
# ===========================================================================

def _make_settings(
    keyword_enabled: bool = True,
    similarity_enabled: bool = True,
    llm_enabled: bool = True,
    multi_intent_enabled: bool = True,
) -> dict[str, Any]:
    return {
        "intent": {
            "layers": {
                "keyword": {
                    "enabled": keyword_enabled,
                    "rules": [
                        {"intent": "qa", "keywords": ["什么是", "怎么用", "如何", "解释"]},
                        {"intent": "task", "keywords": ["帮我", "执行", "创建", "删除"]},
                        {"intent": "chat", "keywords": ["你好", "闲聊", "聊聊"]},
                        {"intent": "retrieve_only", "keywords": ["搜索", "查找", "检索"]},
                    ],
                    "confidence_threshold": 0.2,
                },
                "similarity": {
                    "enabled": similarity_enabled,
                    "top_k": 3,
                    "score_threshold": 0.85,
                    "representatives": {
                        "qa": "知识问答，解释概念，如何使用",
                        "task": "执行任务，帮我做某事，创建或删除",
                        "chat": "闲聊，打招呼，日常对话",
                        "retrieve_only": "搜索文档，查找信息，检索资料",
                    },
                },
                "llm": {
                    "enabled": llm_enabled,
                    "model_routing": "intent",
                },
            },
            "multi_intent": {
                "enabled": multi_intent_enabled,
                "max_intents": 3,
            },
            "fallback_intent": "chat",
            "max_input_length": 1000,
            "timeout": 5.0,
        }
    }


class FakeLLMGateway:
    def __init__(self, response_json: dict[str, Any] | None = None):
        self._response_json = response_json or {
            "primary_intent": "qa",
            "confidence": 0.95,
            "reasoning": "test",
            "sub_intents": [],
            "query": "test query",
        }

    async def generate(self, request):
        return LLMResponse(
            content=json.dumps(self._response_json, ensure_ascii=False),
            model="qwen-plus",
            input_tokens=10,
            output_tokens=5,
        )


class FakePromptManager:
    def render(self, name: str, variables: dict[str, Any] | None = None) -> str:
        return "prompt"


class FakeEmbeddingService:
    def __init__(self, vectors: dict[str, list[float]] | None = None):
        self._vectors = vectors or {}

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors.get(t, [1.0, 0.0, 0.0]) for t in texts]


# ===========================================================================
# Unit: _cosine_similarity
# ===========================================================================

def test_cosine_similarity_identical():
    v = [1.0, 2.0, 3.0]
    assert _cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_mismatched_dims():
    assert _cosine_similarity([1.0], [1.0, 0.0]) == 0.0


# ===========================================================================
# Unit: _parse_llm_json
# ===========================================================================

def test_parse_llm_json_plain():
    raw = '{"intent": "qa", "confidence": 0.9}'
    result = _parse_llm_json(raw)
    assert result == {"intent": "qa", "confidence": 0.9}


def test_parse_llm_json_markdown_fence():
    raw = "```json\n{\"intent\": \"qa\"}\n```"
    result = _parse_llm_json(raw)
    assert result == {"intent": "qa"}


def test_parse_llm_json_embedded():
    raw = "Some text\n{\"intent\": \"qa\"}\nMore text"
    result = _parse_llm_json(raw)
    assert result == {"intent": "qa"}


def test_parse_llm_json_invalid():
    assert _parse_llm_json("not json") is None


# ===========================================================================
# Unit: KeywordMatcher
# ===========================================================================

def test_keyword_match_qa():
    matcher = KeywordMatcher(
        rules=[{"intent": "qa", "keywords": ["什么是", "解释"]}],
        threshold=0.4,
    )
    result = matcher.match("什么是 RAG")
    assert result is not None
    assert result.intent == "qa"
    assert result.confidence == pytest.approx(0.5)


def test_keyword_no_match():
    matcher = KeywordMatcher(
        rules=[{"intent": "qa", "keywords": ["什么是"]}],
        threshold=0.9,
    )
    assert matcher.match("hello world") is None


def test_keyword_below_threshold():
    matcher = KeywordMatcher(
        rules=[
            {"intent": "qa", "keywords": ["什么是", "怎么用", "如何", "解释"]},
        ],
        threshold=0.9,
    )
    result = matcher.match("什么是")
    assert result is None  # 1/4 = 0.25 < 0.9


# ===========================================================================
# Unit: SimilarityMatcher
# ===========================================================================

@pytest.mark.asyncio
async def test_similarity_match():
    embedding = FakeEmbeddingService(vectors={
        "query": [1.0, 0.0, 0.0],
        "qa rep": [1.0, 0.0, 0.0],
        "task rep": [0.0, 1.0, 0.0],
    })
    matcher = SimilarityMatcher(
        embedding_service=embedding,
        representatives={"qa": "qa rep", "task": "task rep"},
        threshold=0.85,
    )
    result = await matcher.match("query")
    assert result is not None
    assert result.intent == "qa"
    assert result.confidence == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_similarity_no_match():
    embedding = FakeEmbeddingService(vectors={
        "query": [1.0, 0.0, 0.0],
        "qa rep": [0.0, 1.0, 0.0],
    })
    matcher = SimilarityMatcher(
        embedding_service=embedding,
        representatives={"qa": "qa rep"},
        threshold=0.85,
    )
    result = await matcher.match("query")
    assert result is None


# ===========================================================================
# Unit: LLMClassifier
# ===========================================================================

@pytest.mark.asyncio
async def test_llm_classifier_success():
    gateway = FakeLLMGateway({
        "primary_intent": "task",
        "confidence": 0.92,
        "query": "帮我创建知识库",
        "sub_intents": [],
    })
    classifier = LLMClassifier(
        llm_gateway=gateway,
        prompt_manager=FakePromptManager(),
    )
    result = await classifier.classify("帮我创建知识库")
    assert result.intent == "task"
    assert result.confidence == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_llm_classifier_multi_intent():
    gateway = FakeLLMGateway({
        "primary_intent": "task",
        "confidence": 0.95,
        "query": "帮我创建知识库",
        "sub_intents": [
            {
                "intent": "qa",
                "confidence": 0.88,
                "query": "解释 RAG",
                "original_query": "顺便解释 RAG",
            }
        ],
    })
    classifier = LLMClassifier(
        llm_gateway=gateway,
        prompt_manager=FakePromptManager(),
        max_intents=3,
    )
    result = await classifier.classify("帮我创建知识库")
    assert result.intent == "task"
    assert len(result.sub_intents) == 1
    assert result.sub_intents[0].intent == "qa"


@pytest.mark.asyncio
async def test_llm_classifier_unknown_intent():
    gateway = FakeLLMGateway({
        "primary_intent": "unknown",
        "confidence": 0.5,
        "query": "???",
        "sub_intents": [],
    })
    classifier = LLMClassifier(
        llm_gateway=gateway,
        prompt_manager=FakePromptManager(),
    )
    with pytest.raises(IntentError) as exc_info:
        await classifier.classify("???")
    assert exc_info.value.code == ErrorCode.INTENT_UNKNOWN


@pytest.mark.asyncio
async def test_llm_classifier_unparseable():
    class BadGateway:
        async def generate(self, request):
            return LLMResponse(
                content="not json at all",
                model="qwen-plus",
                input_tokens=1,
                output_tokens=1,
            )

    classifier = LLMClassifier(
        llm_gateway=BadGateway(),
        prompt_manager=FakePromptManager(),
    )
    with pytest.raises(IntentError) as exc_info:
        await classifier.classify("test")
    assert exc_info.value.code == ErrorCode.INTENT_CLASSIFY_FAILED


# ===========================================================================
# Integration: IntentDomainService
# ===========================================================================

def _make_service(
    llm_gateway=None,
    prompt_manager=None,
    embedding_service=None,
    settings=None,
):
    settings = settings or _make_settings()
    with patch("app.domain.intent.service.get_settings", return_value=MagicMock(**settings)):
        service = IntentDomainService(
            llm_gateway=llm_gateway or FakeLLMGateway(),
            prompt_manager=prompt_manager or FakePromptManager(),
            embedding_service=embedding_service,
        )
    return service


@pytest.mark.asyncio
async def test_service_l1_keyword():
    service = _make_service()
    result = await service.classify(query="什么是 RAG")
    assert isinstance(result, IntentResultData)
    assert result.intent == "qa"
    assert result.layer_used == "keyword"
    assert result.confidence == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_service_l2_similarity():
    # Disable keyword layer to force L2
    settings = _make_settings(keyword_enabled=False)
    embedding = FakeEmbeddingService(vectors={
        "执行任务": [1.0, 0.0, 0.0],
        "task rep": [1.0, 0.0, 0.0],
        "qa rep": [0.0, 1.0, 0.0],
    })
    service = _make_service(
        settings=settings,
        embedding_service=embedding,
    )
    result = await service.classify(query="执行任务")
    assert result.intent == "task"
    assert result.layer_used == "similarity"


@pytest.mark.asyncio
async def test_service_l3_llm():
    # Disable L1 and L2 to force L3
    settings = _make_settings(keyword_enabled=False, similarity_enabled=False)
    gateway = FakeLLMGateway({
        "primary_intent": "retrieve_only",
        "confidence": 0.88,
        "query": "搜索文档",
        "sub_intents": [],
    })
    service = _make_service(
        settings=settings,
        llm_gateway=gateway,
    )
    result = await service.classify(query="搜索文档")
    assert result.intent == "retrieve_only"
    assert result.layer_used == "llm"


@pytest.mark.asyncio
async def test_service_multi_intent():
    settings = _make_settings(keyword_enabled=False, similarity_enabled=False)
    gateway = FakeLLMGateway({
        "primary_intent": "task",
        "confidence": 0.95,
        "query": "帮我创建知识库",
        "sub_intents": [
            {
                "intent": "qa",
                "confidence": 0.88,
                "query": "解释 RAG",
                "original_query": "顺便解释 RAG",
            }
        ],
    })
    service = _make_service(
        settings=settings,
        llm_gateway=gateway,
    )
    result = await service.classify(query="帮我创建知识库，顺便解释 RAG")
    assert result.intent == "task"
    assert len(result.sub_intents) == 1
    assert result.sub_intents[0].intent == "qa"


@pytest.mark.asyncio
async def test_service_fallback_short_input():
    service = _make_service()
    result = await service.classify(query="hi")
    assert result.intent == "chat"  # fallback
    assert result.layer_used == "fallback"


@pytest.mark.asyncio
async def test_service_fallback_all_disabled():
    settings = _make_settings(
        keyword_enabled=False,
        similarity_enabled=False,
        llm_enabled=False,
    )
    service = _make_service(settings=settings)
    result = await service.classify(query="anything")
    assert result.intent == "chat"
    assert result.layer_used == "fallback"


@pytest.mark.asyncio
async def test_service_llm_timeout():
    settings = _make_settings(keyword_enabled=False, similarity_enabled=False)
    settings["intent"]["timeout"] = 0.01

    class SlowGateway:
        async def generate(self, request):
            await asyncio.sleep(10)
            return LLMResponse(content="", model="")

    service = _make_service(
        settings=settings,
        llm_gateway=SlowGateway(),
    )
    result = await service.classify(query="test")
    assert result.intent == "chat"
    assert result.layer_used == "fallback"


@pytest.mark.asyncio
async def test_service_candidates_restriction():
    # Disable L1/L2 to force L3 and verify candidates restriction
    settings = _make_settings(keyword_enabled=False, similarity_enabled=False)
    gateway = FakeLLMGateway({
        "primary_intent": "task",
        "confidence": 0.9,
        "query": "test",
        "sub_intents": [],
    })
    service = _make_service(
        settings=settings,
        llm_gateway=gateway,
    )
    result = await service.classify(
        query="帮我做某事",
        candidates=["task", "chat"],
    )
    assert result.intent == "task"


@pytest.mark.asyncio
async def test_service_max_input_length():
    settings = _make_settings()
    settings["intent"]["max_input_length"] = 10
    service = _make_service(settings=settings)
    long_query = "a" * 100
    result = await service.classify(query=long_query)
    # Should not crash; truncated input is handled gracefully
    assert isinstance(result, IntentResultData)


@pytest.mark.asyncio
async def test_service_routing_info():
    service = _make_service()
    result = await service.classify(query="什么是 RAG")
    assert result.routing.workflow_id == "rag_qa"
    assert result.routing.model == "qwen-plus"


# ===========================================================================
# API endpoint tests
# ===========================================================================

def _mock_session_factory():
    class _MockSession:
        async def __aenter__(self):
            return AsyncMock()
        async def __aexit__(self, *args):
            pass
    class _Factory:
        def __call__(self):
            return _MockSession()
    return _Factory()


def test_api_intent_success(monkeypatch):
    """Test POST /api/v1/intent success."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_result = IntentResultData(
        intent="qa",
        confidence=0.95,
        query="什么是 RAG",
        layer_used="keyword",
        routing={"workflow_id": "rag_qa", "model": "qwen-plus"},
        sub_intents=[],
    )

    with patch("app.api.v1.intent._get_intent_service") as mock_factory:
        mock_service = MagicMock()
        mock_service.classify = AsyncMock(return_value=mock_result)
        mock_factory.return_value = mock_service

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/intent",
            json={
                "user_id": "u1",
                "session_id": "s1",
                "query": "什么是 RAG",
                "options": {
                    "keyword_enabled": True,
                    "similarity_enabled": True,
                    "multi_intent_enabled": True,
                },
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["intent"] == "qa"
    assert data["data"]["layer_used"] == "keyword"


def test_api_intent_error(monkeypatch):
    """Test POST /api/v1/intent error handling."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    with patch("app.api.v1.intent._get_intent_service") as mock_factory:
        mock_service = MagicMock()
        mock_service.classify = AsyncMock(side_effect=IntentError(
            code=ErrorCode.INTENT_CLASSIFY_FAILED,
            message="LLM failed",
        ))
        mock_factory.return_value = mock_service

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/intent",
            json={
                "user_id": "u1",
                "session_id": "s1",
                "query": "test",
            },
        )

    data = response.json()
    if isinstance(data, list) and len(data) == 2 and isinstance(data[0], dict):
        data = data[0]
    assert data["code"] == ErrorCode.INTENT_CLASSIFY_FAILED
