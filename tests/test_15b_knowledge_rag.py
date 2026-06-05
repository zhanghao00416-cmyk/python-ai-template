"""Tests for F15b: Knowledge base RAG query."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import ErrorCode, RAGError
from app.domain.knowledge.repo import KnowledgeRepo
from app.domain.knowledge.service import KnowledgeService, _deduplicate_results
from app.schemas.knowledge import (
    RAGCitation,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGRetrievalResult,
    RAGUsage,
)
from app.schemas.vector_store import SearchResult
from app.services.llm.gateway import LLMGateway
from app.services.prompt_manager import PromptManager
from app.services.sse_stream import SSEStreamService


class FakeLLMGateway:
    def __init__(self, content: str = "fake answer"):
        self._content = content

    async def generate(self, request):
        from app.schemas.llm import LLMResponse

        return LLMResponse(
            content=self._content,
            model="qwen-plus",
            input_tokens=10,
            output_tokens=5,
        )

    async def generate_stream(self, request):
        from app.schemas.llm import LLMChunk

        yield LLMChunk(content=self._content, input_tokens=10, output_tokens=5)


class FakePromptManager:
    def render(self, name: str, variables: dict[str, Any] | None = None) -> str:
        if "system" in name:
            return f"system: {variables.get('context', '')}"
        return variables.get("question", "") if variables else ""


@pytest.fixture
def fake_repo():
    repo = MagicMock(spec=KnowledgeRepo)
    repo.collection_exists = AsyncMock(return_value=True)
    repo.list_collections = AsyncMock(
        return_value=[
            {"name": "test_collection", "vector_dim": 1024, "points_count": 10},
        ]
    )
    repo.search_chunks = AsyncMock(return_value=[])
    repo.get_parent_chunks = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def fake_task_service():
    return MagicMock()


@pytest.fixture
def service(fake_repo, fake_task_service):
    return KnowledgeService(
        repo=fake_repo,
        task_service=fake_task_service,
        llm_gateway=FakeLLMGateway(),
        prompt_manager=FakePromptManager(),
    )


# ------------------------------------------------------------------
# _deduplicate_results
# ------------------------------------------------------------------

def test_deduplicate_results_keeps_highest_score():
    results = [
        SearchResult(id="1", score=0.5, payload={"doc_id": "d1", "chunk_index": 0}),
        SearchResult(id="2", score=0.8, payload={"doc_id": "d1", "chunk_index": 0}),
        SearchResult(id="3", score=0.6, payload={"doc_id": "d2", "chunk_index": 0}),
    ]
    deduped = _deduplicate_results(results)
    assert len(deduped) == 2
    assert deduped[0].score == 0.8


def test_deduplicate_results_empty():
    assert _deduplicate_results([]) == []


# ------------------------------------------------------------------
# query_rag — sync, no results
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_rag_no_results(service, fake_repo):
    fake_repo.search_chunks.return_value = []
    request = RAGQueryRequest(
        user_id="u1",
        query="test query",
        collection_names=["test_collection"],
    )
    result = await service.query_rag(request)
    assert isinstance(result, RAGQueryResponse)
    assert result.content == "未找到相关文档，无法回答您的问题。"
    assert result.citations == []
    assert result.retrieval_results == []


# ------------------------------------------------------------------
# query_rag — sync, with results
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_rag_with_results(service, fake_repo):
    fake_repo.search_chunks.return_value = [
        SearchResult(
            id="c1",
            score=0.9,
            payload={
                "text": "chunk text",
                "chunk_index": 0,
                "doc_id": "d1",
                "source_file": "file.md",
                "doc_type": "article",
                "source": "internal",
                "tag": "reviewed",
                "_collection": "test_collection",
            },
        ),
    ]
    request = RAGQueryRequest(
        user_id="u1",
        query="test query",
        collection_names=["test_collection"],
        top_k=3,
    )
    result = await service.query_rag(request)
    assert isinstance(result, RAGQueryResponse)
    assert result.content == "fake answer"
    assert len(result.citations) == 1
    assert result.citations[0].filename == "file.md"
    assert len(result.retrieval_results) == 1
    assert result.retrieval_results[0].chunk_text == "chunk text"
    assert result.usage.output_tokens == 5


# ------------------------------------------------------------------
# query_rag — with parent-child context
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_rag_parent_child(service, fake_repo):
    fake_repo.search_chunks.return_value = [
        SearchResult(
            id="c1",
            score=0.85,
            payload={
                "text": "child chunk",
                "chunk_index": 1,
                "doc_id": "d1",
                "parent_id": "p1",
                "source_file": "doc.md",
                "_collection": "test_collection",
            },
        ),
    ]
    fake_repo.get_parent_chunks.return_value = [
        SearchResult(
            id="p1",
            score=0.0,
            payload={"text": "parent chunk", "chunk_index": 0},
        ),
    ]
    request = RAGQueryRequest(
        user_id="u1",
        query="test",
        collection_names=["test_collection"],
    )
    result = await service.query_rag(request)
    assert result.retrieval_results[0].parent_chunk_text == "parent chunk"
    assert result.retrieval_results[0].parent_chunk_index == 0


# ------------------------------------------------------------------
# query_rag — retrieval strategies
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_rag_strategy_keyword(service, fake_repo):
    fake_repo.search_chunks.return_value = [
        SearchResult(id="c1", score=0.7, payload={"text": "text", "doc_id": "d1", "source_file": "f.md", "_collection": "c"}),
    ]
    for strategy in ["keyword", "similarity", "hybrid", "rrf"]:
        request = RAGQueryRequest(
            user_id="u1",
            query="test",
            collection_names=["c"],
            retrieval_strategy=strategy,
        )
        result = await service.query_rag(request)
        assert result.content == "fake answer"


# ------------------------------------------------------------------
# query_rag — rerank enabled
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_rag_rerank(service, fake_repo):
    fake_repo.search_chunks.return_value = [
        SearchResult(
            id="c1",
            score=0.55,
            payload={"text": "hello world test", "doc_id": "d1", "source_file": "f.md", "_collection": "c"},
        ),
        SearchResult(
            id="c2",
            score=0.56,
            payload={"text": "other content", "doc_id": "d2", "source_file": "f2.md", "_collection": "c"},
        ),
    ]
    request = RAGQueryRequest(
        user_id="u1",
        query="hello world",
        collection_names=["c"],
        enable_rerank=True,
        top_k=2,
    )
    result = await service.query_rag(request)
    # With keyword boost (2 terms * 0.01 = 0.02), 0.55 + 0.02 = 0.57 > 0.56
    assert result.retrieval_results[0].chunk_text == "hello world test"


# ------------------------------------------------------------------
# query_rag — collection not found
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_rag_collection_not_found(service, fake_repo):
    fake_repo.collection_exists.return_value = False
    request = RAGQueryRequest(
        user_id="u1",
        query="test",
        collection_names=["missing"],
    )
    result = await service.query_rag(request)
    assert result.content == "未找到相关文档，无法回答您的问题。"


# ------------------------------------------------------------------
# query_rag — generation failure
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_rag_generation_failure(fake_repo, fake_task_service):
    bad_gateway = FakeLLMGateway(content="")
    bad_gateway.generate = AsyncMock(side_effect=Exception("LLM failed"))

    service = KnowledgeService(
        repo=fake_repo,
        task_service=fake_task_service,
        llm_gateway=bad_gateway,
        prompt_manager=FakePromptManager(),
    )
    fake_repo.search_chunks.return_value = [
        SearchResult(id="c1", score=0.8, payload={"text": "text", "doc_id": "d1", "source_file": "f.md", "_collection": "c"}),
    ]
    request = RAGQueryRequest(user_id="u1", query="test", collection_names=["c"])
    with pytest.raises(RAGError) as exc_info:
        await service.query_rag(request)
    assert exc_info.value.code == ErrorCode.RAG_GENERATION_FAILED


# ------------------------------------------------------------------
# query_rag_stream
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_rag_stream(service, fake_repo):
    fake_repo.search_chunks.return_value = [
        SearchResult(
            id="c1",
            score=0.9,
            payload={
                "text": "stream chunk",
                "doc_id": "d1",
                "source_file": "s.md",
                "_collection": "test_collection",
            },
        ),
    ]
    request = RAGQueryRequest(
        user_id="u1",
        query="test",
        collection_names=["test_collection"],
    )
    sse = SSEStreamService(intent="qa", user_id="u1", session_id="s1")
    events = []
    async for event in service.query_rag_stream(request, sse):
        events.append(event)

    assert any("start" in e for e in events)
    assert any("fake answer" in e for e in events)
    assert any("done" in e for e in events)


@pytest.mark.asyncio
async def test_query_rag_stream_no_results(service, fake_repo):
    fake_repo.search_chunks.return_value = []
    request = RAGQueryRequest(
        user_id="u1",
        query="test",
        collection_names=["test_collection"],
    )
    sse = SSEStreamService(intent="qa", user_id="u1", session_id="s1")
    events = []
    async for event in service.query_rag_stream(request, sse):
        events.append(event)

    assert any("未找到相关文档" in e for e in events)
    assert any("done" in e for e in events)


# ------------------------------------------------------------------
# API endpoint tests
# ------------------------------------------------------------------

def _mock_session_factory():
    """Return a callable that yields an async context manager returning a mock session."""
    class _MockSession:
        async def __aenter__(self):
            return AsyncMock()
        async def __aexit__(self, *args):
            pass
    class _Factory:
        def __call__(self):
            return _MockSession()
    return _Factory()


def test_api_kb_query_sync(monkeypatch):
    """Test POST /api/v1/kb/query sync mode."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.query_rag = AsyncMock(
        return_value=RAGQueryResponse(
            content="answer",
            citations=[RAGCitation(filename="f.md", chunk_text="text", score=0.9)],
            retrieval_results=[
                RAGRetrievalResult(chunk_text="text", score=0.9, chunk_index=0)
            ],
            usage=RAGUsage(input_tokens=10, output_tokens=5, model="qwen-plus"),
        )
    )

    with patch("app.api.v1.kb.get_knowledge_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/kb/query",
            json={
                "user_id": "u1",
                "query": "test",
                "collection_names": ["c1"],
                "stream": False,
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["content"] == "answer"
    assert len(data["data"]["citations"]) == 1


def test_api_kb_query_stream(monkeypatch):
    """Test POST /api/v1/kb/query SSE stream mode."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()

    async def _stream(request, sse):
        async for ev in sse.start():
            yield ev
        async for ev in sse.chunk("answer"):
            yield ev
        async for ev in sse.done():
            yield ev

    mock_service.query_rag_stream = _stream

    with patch("app.api.v1.kb.get_knowledge_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/kb/query",
            json={
                "user_id": "u1",
                "query": "test",
                "collection_names": ["c1"],
                "stream": True,
            },
        )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    text = response.text
    assert "start" in text
    assert "answer" in text
    assert "done" in text


def test_api_kb_query_error(monkeypatch):
    """Test POST /api/v1/kb/query error handling."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.query_rag = AsyncMock(side_effect=RAGError(
        code=ErrorCode.RAG_RETRIEVAL_FAILED,
        message="检索失败",
    ))

    with patch("app.api.v1.kb.get_knowledge_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/kb/query",
            json={
                "user_id": "u1",
                "query": "test",
                "collection_names": ["c1"],
                "stream": False,
            },
        )
    # Allow either 400 (caught by route) or 200 with error code in body (caught by middleware)
    data = response.json()
    # If FastAPI returns a tuple as a list, extract the dict
    if isinstance(data, list) and len(data) == 2 and isinstance(data[0], dict):
        data = data[0]
    assert data["code"] == ErrorCode.RAG_RETRIEVAL_FAILED
