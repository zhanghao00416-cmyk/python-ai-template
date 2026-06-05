"""Tests for F15c: Knowledge base end-to-end integration flow.

This module verifies the complete lifecycle:
    create collection → upload document → ingest → query (sync + stream)
    → list documents → preview delete → delete documents → delete collection
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.kb import router as kb_router
from app.core.di import container
from app.core.errors import ErrorCode
from app.domain.knowledge.service import KnowledgeService
from app.schemas.knowledge import (
    CollectionCreateRequest,
    CollectionCreateResponse,
    CollectionDeleteResponse,
    CollectionListResponse,
    DocumentDeletePreview,
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    RAGQueryResponse,
    RAGRetrievalResult,
    RAGCitation,
    RAGUsage,
)
from app.schemas.vector_store import SearchResult
from app.services.llm.gateway import LLMGateway
from app.services.prompt_manager import PromptManager
from app.services.sse_stream import SSEStreamService
from sqlalchemy.ext.asyncio import async_sessionmaker


# ------------------------------------------------------------------
# Helpers / Fixtures
# ------------------------------------------------------------------

class FakeLLMGateway:
    def __init__(self, content: str = "E2E answer"):
        self._content = content

    async def generate(self, request):
        from app.schemas.llm import LLMResponse
        return LLMResponse(
            content=self._content,
            model="qwen-plus",
            input_tokens=12,
            output_tokens=6,
        )

    async def generate_stream(self, request):
        from app.schemas.llm import LLMChunk
        yield LLMChunk(content=self._content, input_tokens=12, output_tokens=6)


class FakePromptManager:
    def render(self, name: str, variables: dict | None = None) -> str:
        if "system" in name:
            return f"system: {variables.get('context', '')}"
        return variables.get("question", "") if variables else ""


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


def _make_vector_store_mock() -> MagicMock:
    store = MagicMock()
    store.create_collection = AsyncMock()
    store.delete_collection = AsyncMock()
    store.collection_exists = AsyncMock(return_value=True)
    store.list_collections = AsyncMock(
        return_value=[{"name": "e2e_test", "vector_dim": 1024, "points_count": 0, "description": ""}]
    )
    store.get_collection_info = AsyncMock(
        return_value={"name": "e2e_test", "vector_dim": 1024, "distance": "Cosine", "points_count": 0, "description": ""}
    )
    store.upsert_points = AsyncMock()
    store.scroll_points = AsyncMock(return_value=[])
    store.delete_by_filter = AsyncMock(return_value=0)
    store.search_by_strategy = AsyncMock(return_value=[])
    return store


def _make_task_service_mock() -> MagicMock:
    svc = MagicMock()
    model = MagicMock()
    model.task_id = uuid4()
    model.status = "pending"
    svc.submit_task = AsyncMock(return_value=model)
    return svc


# ------------------------------------------------------------------
# End-to-end flow tests (service layer)
# ------------------------------------------------------------------

@pytest.fixture
def e2e_service():
    """Build a KnowledgeService with mocked infra for E2E flow testing."""
    from app.domain.knowledge.repo import KnowledgeRepo
    store = _make_vector_store_mock()
    repo = KnowledgeRepo(vector_store=store)
    task_svc = _make_task_service_mock()
    svc = KnowledgeService(
        repo=repo,
        task_service=task_svc,
        llm_gateway=FakeLLMGateway(),
        prompt_manager=FakePromptManager(),
    )
    return svc, store


@pytest.mark.asyncio
async def test_e2e_full_lifecycle_happy_path(e2e_service):
    """Complete flow: create → ingest → query → delete."""
    svc, store = e2e_service

    # 1. Create collection
    create_resp = await svc.create_collection(CollectionCreateRequest(name="e2e_test"))
    assert create_resp.name == "e2e_test"
    assert create_resp.status == "created"
    store.create_collection.assert_awaited_once()

    # 2. Ingest document directly (bypass async upload/task queue)
    ingest_result = await svc.ingest_document(
        collection="e2e_test",
        filename="e2e_doc.md",
        text="# E2E Test\n\nThis is integration test content.\n",
        doc_type="article",
        source="e2e",
        tag="test",
        uploader="e2e_user",
        strategy="fixed_overlap",
        chunking_params={"chunk_size": 50, "chunk_overlap": 10},
        enable_parent_child=False,
        parent_chunk_params={},
    )
    assert ingest_result["collection"] == "e2e_test"
    assert ingest_result["chunk_count"] > 0
    doc_id = ingest_result["doc_id"]
    store.upsert_points.assert_awaited()

    # 3. Setup search mock for query
    store.search_by_strategy = AsyncMock(return_value=[
        SearchResult(
            id="c1",
            score=0.92,
            payload={
                "text": "integration test content",
                "chunk_index": 0,
                "doc_id": doc_id,
                "source_file": "e2e_doc.md",
                "doc_type": "article",
                "source": "e2e",
                "tag": "test",
                "_collection": "e2e_test",
            },
        ),
    ])

    # 4. Sync RAG query
    from app.schemas.knowledge import RAGQueryRequest
    query_req = RAGQueryRequest(
        user_id="e2e_user",
        query="integration test",
        collection_names=["e2e_test"],
    )
    query_resp = await svc.query_rag(query_req)
    assert query_resp.content == "E2E answer"
    assert len(query_resp.citations) == 1
    assert query_resp.citations[0].filename == "e2e_doc.md"
    assert len(query_resp.retrieval_results) == 1
    assert query_resp.retrieval_results[0].chunk_text == "integration test content"

    # 5. Stream RAG query
    sse = SSEStreamService(intent="qa", user_id="e2e_user", session_id="s1")
    events = []
    async for event in svc.query_rag_stream(query_req, sse):
        events.append(event)
    assert any("start" in e for e in events)
    assert any("E2E answer" in e for e in events)
    assert any("done" in e for e in events)

    # 6. List documents
    store.scroll_points = AsyncMock(return_value=[
        {"doc_id": doc_id, "doc_type": "article", "source": "e2e", "tag": "test", "source_file": "e2e_doc.md"},
    ])
    list_resp = await svc.list_documents("e2e_test")
    assert list_resp.collection == "e2e_test"
    assert len(list_resp.documents) == 1
    assert list_resp.documents[0].doc_id == doc_id

    # 7. Preview delete
    from app.schemas.knowledge import DocumentDeleteRequest
    preview = await svc.preview_delete_documents(
        "e2e_test",
        DocumentDeleteRequest(doc_id=doc_id),
    )
    assert preview.matched_count == 1
    assert preview.confirm_token

    # 8. Delete documents
    store.delete_by_filter = AsyncMock(return_value=1)
    del_resp = await svc.delete_documents(
        "e2e_test",
        DocumentDeleteRequest(doc_id=doc_id, confirm_token=preview.confirm_token),
    )
    assert del_resp.deleted_count == 1

    # 9. Delete collection
    del_coll_resp = await svc.delete_collection("e2e_test")
    assert del_coll_resp.deleted is True
    store.delete_collection.assert_awaited_once_with("e2e_test")


@pytest.mark.asyncio
async def test_e2e_query_empty_collection(e2e_service):
    """Query on a collection with no documents should return graceful no-result."""
    svc, store = e2e_service

    # Create but don't ingest
    await svc.create_collection(CollectionCreateRequest(name="empty_coll"))

    store.search_by_strategy = AsyncMock(return_value=[])
    from app.schemas.knowledge import RAGQueryRequest
    query_req = RAGQueryRequest(
        user_id="u1",
        query="anything",
        collection_names=["empty_coll"],
    )
    resp = await svc.query_rag(query_req)
    assert "未找到相关文档" in resp.content
    assert resp.citations == []


# ------------------------------------------------------------------
# End-to-end flow tests (API layer)
# ------------------------------------------------------------------

def test_api_e2e_full_lifecycle(monkeypatch):
    """Chain API calls to verify the full HTTP flow."""
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock(spec=KnowledgeService)

    # Stateful mock to simulate the backend across calls
    _state = {"doc_id": None, "confirm_token": None}

    async def _create_collection(request):
        return CollectionCreateResponse(name=request.name, status="created")

    async def _upload_document(collection, filename, content_bytes, request):
        _state["doc_id"] = "doc:e2e1234567890ab"
        return DocumentUploadResponse(
            task_id=str(uuid4()),
            status="pending",
        )

    async def _query_rag(request):
        return RAGQueryResponse(
            content="API E2E answer",
            citations=[RAGCitation(filename="api.md", chunk_text="api text", score=0.9)],
            retrieval_results=[
                RAGRetrievalResult(chunk_text="api text", score=0.9, chunk_index=0, doc_id=_state["doc_id"])
            ],
            usage=RAGUsage(input_tokens=10, output_tokens=5, model="qwen-plus"),
        )

    async def _query_rag_stream(request, sse):
        async for ev in sse.start():
            yield ev
        async for ev in sse.chunk("API E2E answer"):
            yield ev
        async for ev in sse.done():
            yield ev

    async def _list_documents(collection, doc_type=None, source=None, tag=None):
        from app.schemas.knowledge import DocumentListItem
        return DocumentListResponse(
            collection=collection,
            documents=[
                DocumentListItem(
                    doc_id=_state["doc_id"],
                    doc_type="article",
                    source="api",
                    tag="test",
                    source_file="api.md",
                    chunk_count=1,
                )
            ],
        )

    async def _preview_delete_documents(collection, request):
        _state["confirm_token"] = "token1234567890abcdef"
        return DocumentDeletePreview(
            collection=collection,
            matched_count=1,
            confirm_token=_state["confirm_token"],
            filters={"doc_id": _state["doc_id"]},
        )

    async def _delete_documents(collection, request):
        return DocumentDeleteResponse(
            collection=collection,
            deleted_count=1,
            confirm_token=request.confirm_token,
        )

    async def _delete_collection(name):
        return CollectionDeleteResponse(name=name, deleted=True)

    mock_service.create_collection = _create_collection
    mock_service.upload_document = _upload_document
    mock_service.query_rag = _query_rag
    mock_service.query_rag_stream = _query_rag_stream
    mock_service.list_documents = _list_documents
    mock_service.preview_delete_documents = _preview_delete_documents
    mock_service.delete_documents = _delete_documents
    mock_service.delete_collection = _delete_collection

    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.api.v1.kb.get_knowledge_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)

        # 1. POST /kb/collections
        r = client.post("/api/v1/kb/collections", json={"name": "api_e2e"})
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "api_e2e"
        assert data["data"]["status"] == "created"

        # 2. POST /kb/collections/{name}/documents
        r = client.post(
            "/api/v1/kb/collections/api_e2e/documents",
            data={"doc_type": "article", "source": "api", "tag": "test"},
            files={"file": ("api.md", b"# API\n\nAPI test content.\n", "text/markdown")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "pending"

        # 3. POST /kb/query (sync)
        r = client.post(
            "/api/v1/kb/query",
            json={
                "user_id": "u1",
                "query": "api test",
                "collection_names": ["api_e2e"],
                "stream": False,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["content"] == "API E2E answer"
        assert len(data["data"]["citations"]) == 1

        # 4. POST /kb/query (stream)
        r = client.post(
            "/api/v1/kb/query",
            json={
                "user_id": "u1",
                "query": "api test",
                "collection_names": ["api_e2e"],
                "stream": True,
            },
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "text/event-stream; charset=utf-8"
        text = r.text
        assert "start" in text
        assert "API E2E answer" in text
        assert "done" in text

        # 5. GET /kb/collections/{name}/documents
        r = client.get("/api/v1/kb/collections/api_e2e/documents")
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert len(data["data"]["documents"]) == 1

        # 6. DELETE /kb/collections/{name}/documents (preview)
        r = client.delete(
            "/api/v1/kb/collections/api_e2e/documents",
            params={"doc_id": _state["doc_id"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["matched_count"] == 1
        assert data["data"]["confirm_token"]

        # 7. DELETE /kb/collections/{name}/documents (confirm)
        r = client.delete(
            "/api/v1/kb/collections/api_e2e/documents",
            params={"doc_id": _state["doc_id"], "confirm_token": _state["confirm_token"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["deleted_count"] == 1

        # 8. DELETE /kb/collections/{name}
        r = client.delete("/api/v1/kb/collections/api_e2e")
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["deleted"] is True


def test_api_e2e_query_error(monkeypatch):
    """E2E flow should handle errors gracefully."""
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock(spec=KnowledgeService)
    from app.core.errors import KnowledgeError

    async def _failing_query(request):
        raise KnowledgeError(code=ErrorCode.RAG_RETRIEVAL_FAILED, message="检索失败")

    mock_service.query_rag = _failing_query

    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.api.v1.kb.get_knowledge_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/api/v1/kb/query",
            json={"user_id": "u1", "query": "test", "collection_names": ["c1"], "stream": False},
        )
        data = r.json()
        if isinstance(data, list) and len(data) == 2 and isinstance(data[0], dict):
            data = data[0]
        assert data["code"] == ErrorCode.RAG_RETRIEVAL_FAILED
