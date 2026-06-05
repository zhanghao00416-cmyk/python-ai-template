"""Tests for F15a: knowledge base document management (chunking, upload, collections)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.errors import ErrorCode, KnowledgeError, make_error
from app.domain.knowledge.repo import KnowledgeRepo
from app.domain.knowledge.service import (
    KnowledgeService,
    _active_filters,
    _default_payload_indexes,
    _doc_id,
    _make_confirm_token,
)
from app.schemas.knowledge import (
    ChunkingParams,
    ChunkingStrategy,
    CollectionCreateRequest,
    CollectionListItem,
    DocumentDeletePreview,
    DocumentDeleteRequest,
    DocumentListItem,
    DocumentUploadRequest,
    ParentChunkParams,
)
from app.schemas.vector_store import CollectionConfig, PayloadIndexConfig, PointPayload
from app.services.chunking import ChunkingService, TextChunk
from app.services.embedding import EmbeddingService, _hash_vector, _tokenize


# ===========================================================================
# Helpers
# ===========================================================================

def _make_vector_store_mock() -> MagicMock:
    """Return a MagicMock spec'd like VectorStoreBase with async methods."""
    store = MagicMock()
    store.create_collection = AsyncMock()
    store.delete_collection = AsyncMock()
    store.collection_exists = AsyncMock(return_value=True)
    store.list_collections = AsyncMock(return_value=["kb_test"])
    store.get_collection_info = AsyncMock(return_value={
        "name": "kb_test",
        "vector_dim": 1024,
        "distance": "Cosine",
        "points_count": 0,
        "description": "",
    })
    store.upsert_points = AsyncMock()
    store.scroll_points = AsyncMock(return_value=[])
    store.delete_by_filter = AsyncMock(return_value=0)
    return store


def _make_task_service_mock() -> MagicMock:
    svc = MagicMock()
    model = MagicMock()
    model.task_id = uuid4()
    model.status = "pending"
    svc.submit_task = AsyncMock(return_value=model)
    return svc


# ===========================================================================
# TestChunkingStrategies
# ===========================================================================

class TestChunkingStrategies:
    def test_fixed_overlap_basic(self):
        svc = ChunkingService()
        text = "a " * 200
        chunks = svc.chunk(
            text=text,
            doc_id="doc1",
            strategy=ChunkingStrategy.FIXED_OVERLAP,
            params=ChunkingParams(chunk_size=50, chunk_overlap=10),
        )
        assert len(chunks) > 0
        assert all(len(c.text) <= 50 for c in chunks)
        assert chunks[0].chunk_index == 0
        assert chunks[0].is_parent is False

    def test_delimiter_max_basic(self):
        svc = ChunkingService()
        text = "line1\nline2\nline3"
        chunks = svc.chunk(
            text=text,
            doc_id="doc1",
            strategy=ChunkingStrategy.DELIMITER_MAX,
            params=ChunkingParams(chunk_size=50, delimiter="\n"),
        )
        assert len(chunks) > 0
        assert all(len(c.text) <= 50 for c in chunks)

    def test_semantic_basic(self):
        svc = ChunkingService()
        text = "First paragraph.\n\nSecond paragraph with more words here.\n\nThird paragraph also here."
        chunks = svc.chunk(
            text=text,
            doc_id="doc1",
            strategy=ChunkingStrategy.SEMANTIC,
            params=ChunkingParams(chunk_size=50),
        )
        assert len(chunks) >= 1

    def test_paragraph_basic(self):
        svc = ChunkingService()
        text = "# Heading\n\nBody text here.\n\n## Subheading\n\nMore text."
        chunks = svc.chunk(
            text=text,
            doc_id="doc1",
            strategy=ChunkingStrategy.PARAGRAPH,
            params=ChunkingParams(),
        )
        assert len(chunks) >= 2
        # Headings should be captured
        assert any(c.heading for c in chunks)

    def test_parent_child_mode(self):
        svc = ChunkingService()
        text = "word " * 500
        chunks = svc.chunk(
            text=text,
            doc_id="doc1",
            strategy=ChunkingStrategy.FIXED_OVERLAP,
            params=ChunkingParams(chunk_size=50, chunk_overlap=10),
            enable_parent_child=True,
            parent_params=ParentChunkParams(chunk_size=200, chunk_overlap=20),
        )
        parents = [c for c in chunks if c.is_parent]
        children = [c for c in chunks if not c.is_parent]
        assert len(parents) > 0
        assert len(children) > 0
        # Every child should reference a parent
        for child in children:
            assert child.parent_id is not None
            assert any(p.chunk_id == child.parent_id for p in parents)

    def test_empty_text(self):
        svc = ChunkingService()
        chunks = svc.chunk(
            text="",
            doc_id="doc1",
            strategy=ChunkingStrategy.FIXED_OVERLAP,
            params=ChunkingParams(),
        )
        assert chunks == []


# ===========================================================================
# TestEmbeddingService
# ===========================================================================

class TestEmbeddingService:
    @pytest.mark.asyncio
    async def test_embed_batch_empty(self):
        svc = EmbeddingService()
        result = await svc.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_batch_fallback(self):
        svc = EmbeddingService()
        # Ensure no external URL is configured for the test
        svc._base_url = ""
        result = await svc.embed_batch(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == svc._dim
        # Vectors should be unit-normalized
        import math
        for vec in result:
            norm = math.sqrt(sum(v * v for v in vec))
            assert abs(norm - 1.0) < 1e-6

    def test_compute_sparse_vectors(self):
        svc = EmbeddingService()
        result = svc.compute_sparse_vectors(["hello world", "hello"])
        assert len(result) == 2
        # Shared vocabulary means overlapping keys
        assert any(k in result[1] for k in result[0])

    def test_tokenize(self):
        tokens = _tokenize("Hello, 世界! 123")
        assert "hello" in tokens
        assert "世界" in tokens
        assert "123" in tokens

    def test_hash_vector_determinism(self):
        v1 = _hash_vector("test", 128)
        v2 = _hash_vector("test", 128)
        assert v1 == v2
        assert len(v1) == 128


# ===========================================================================
# TestKnowledgeRepo
# ===========================================================================

class TestKnowledgeRepo:
    @pytest.mark.asyncio
    async def test_create_collection(self):
        store = _make_vector_store_mock()
        repo = KnowledgeRepo(vector_store=store)
        cfg = CollectionConfig(name="kb_test")
        await repo.create_collection(cfg)
        store.create_collection.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_collections(self):
        store = _make_vector_store_mock()
        repo = KnowledgeRepo(vector_store=store)
        result = await repo.list_collections()
        assert len(result) == 1
        assert result[0]["name"] == "kb_test"

    @pytest.mark.asyncio
    async def test_insert_document_chunks(self):
        store = _make_vector_store_mock()
        repo = KnowledgeRepo(vector_store=store)
        points = [repo.build_point_insert(
            point_id="p1",
            vector=[0.1] * 1024,
            sparse_vector={0: 0.5},
            payload=PointPayload(doc_id="d1", collection="kb_test", text="hello"),
        )]
        written = await repo.insert_document_chunks("kb_test", "d1", points)
        assert written == 1
        store.upsert_points.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_documents_aggregates(self):
        store = _make_vector_store_mock()
        store.scroll_points = AsyncMock(return_value=[
            {"doc_id": "d1", "doc_type": "article", "source": "web", "tag": "ai", "source_file": "a.md"},
            {"doc_id": "d1", "doc_type": "article", "source": "web", "tag": "ai", "source_file": "a.md"},
            {"doc_id": "d2", "doc_type": "faq", "source": "internal", "tag": "", "source_file": "b.md"},
        ])
        repo = KnowledgeRepo(vector_store=store)
        rows = await repo.list_documents("kb_test")
        assert len(rows) == 2
        d1 = next(r for r in rows if r["doc_id"] == "d1")
        assert d1["chunk_count"] == 2

    @pytest.mark.asyncio
    async def test_count_documents_by_filter(self):
        store = _make_vector_store_mock()
        store.scroll_points = AsyncMock(return_value=[{"doc_id": "d1"}] * 5)
        repo = KnowledgeRepo(vector_store=store)
        count = await repo.count_documents_by_filter("kb_test", doc_type="article")
        assert count == 5

    @pytest.mark.asyncio
    async def test_delete_documents(self):
        store = _make_vector_store_mock()
        store.delete_by_filter = AsyncMock(return_value=3)
        repo = KnowledgeRepo(vector_store=store)
        deleted = await repo.delete_documents("kb_test", doc_id="d1")
        assert deleted == 3


# ===========================================================================
# TestKnowledgeService
# ===========================================================================

class TestKnowledgeService:
    def _make_service(self, store=None, task_svc=None):
        if store is None:
            store = _make_vector_store_mock()
        repo = KnowledgeRepo(vector_store=store)
        if task_svc is None:
            task_svc = _make_task_service_mock()
        return KnowledgeService(repo=repo, task_service=task_svc)

    @pytest.mark.asyncio
    async def test_create_collection(self):
        svc = self._make_service()
        req = CollectionCreateRequest(name="kb_new")
        resp = await svc.create_collection(req)
        assert resp.name == "kb_new"
        assert resp.status == "created"

    @pytest.mark.asyncio
    async def test_list_collections(self):
        svc = self._make_service()
        resp = await svc.list_collections()
        assert len(resp.collections) == 1
        assert isinstance(resp.collections[0], CollectionListItem)

    @pytest.mark.asyncio
    async def test_delete_collection(self):
        store = _make_vector_store_mock()
        svc = self._make_service(store=store)
        resp = await svc.delete_collection("kb_test")
        assert resp.deleted is True
        store.delete_collection.assert_awaited_once_with("kb_test")

    @pytest.mark.asyncio
    async def test_upload_document_rejects_non_md(self):
        svc = self._make_service()
        with pytest.raises(KnowledgeError) as exc_info:
            await svc.upload_document(
                collection="kb_test",
                filename="report.pdf",
                content_bytes=b"data",
                request=DocumentUploadRequest(),
            )
        assert exc_info.value.code == ErrorCode.KB_FORMAT_UNSUPPORTED

    @pytest.mark.asyncio
    async def test_upload_document_accepts_md(self):
        svc = self._make_service()
        text = "# Hello\n\nThis is a test document.\n"
        resp = await svc.upload_document(
            collection="kb_test",
            filename="test.md",
            content_bytes=text.encode("utf-8"),
            request=DocumentUploadRequest(strategy=ChunkingStrategy.FIXED_OVERLAP),
        )
        assert resp.status == "pending"
        assert resp.task_id

    @pytest.mark.asyncio
    async def test_upload_document_chunk_limit(self):
        svc = self._make_service()
        # Create a very long text that will exceed default max_chunks
        text = "word " * 10000
        with patch.object(svc, "_chunking", ChunkingService()):
            with pytest.raises(KnowledgeError) as exc_info:
                await svc.upload_document(
                    collection="kb_test",
                    filename="long.md",
                    content_bytes=text.encode("utf-8"),
                    request=DocumentUploadRequest(
                        strategy=ChunkingStrategy.FIXED_OVERLAP,
                        chunking_params=ChunkingParams(chunk_size=50, chunk_overlap=0),
                    ),
                )
        assert exc_info.value.code == ErrorCode.KB_CHUNK_LIMIT_EXCEEDED

    @pytest.mark.asyncio
    async def test_list_documents(self):
        store = _make_vector_store_mock()
        store.scroll_points = AsyncMock(return_value=[
            {"doc_id": "d1", "doc_type": "article", "source": "web", "tag": "ai", "source_file": "a.md"},
        ])
        svc = self._make_service(store=store)
        resp = await svc.list_documents("kb_test")
        assert resp.collection == "kb_test"
        assert len(resp.documents) == 1
        assert isinstance(resp.documents[0], DocumentListItem)

    @pytest.mark.asyncio
    async def test_list_documents_collection_not_found(self):
        store = _make_vector_store_mock()
        store.collection_exists = AsyncMock(return_value=False)
        svc = self._make_service(store=store)
        with pytest.raises(KnowledgeError) as exc_info:
            await svc.list_documents("missing")
        assert exc_info.value.code == ErrorCode.KB_FILE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_preview_delete_documents(self):
        store = _make_vector_store_mock()
        store.scroll_points = AsyncMock(return_value=[{"doc_id": "d1"}] * 3)
        svc = self._make_service(store=store)
        req = DocumentDeleteRequest(doc_type="article")
        preview = await svc.preview_delete_documents("kb_test", req)
        assert preview.matched_count == 3
        assert preview.confirm_token
        assert preview.filters == {"doc_type": "article"}

    @pytest.mark.asyncio
    async def test_delete_documents_requires_token(self):
        store = _make_vector_store_mock()
        store.scroll_points = AsyncMock(return_value=[{"doc_id": "d1"}] * 2)
        store.delete_by_filter = AsyncMock(return_value=2)
        svc = self._make_service(store=store)
        req = DocumentDeleteRequest(doc_type="article")
        with pytest.raises(KnowledgeError) as exc_info:
            await svc.delete_documents("kb_test", req)
        assert exc_info.value.code == ErrorCode.KB_UPLOAD_FAILED

    @pytest.mark.asyncio
    async def test_delete_documents_with_valid_token(self):
        store = _make_vector_store_mock()
        store.scroll_points = AsyncMock(return_value=[{"doc_id": "d1"}] * 2)
        store.delete_by_filter = AsyncMock(return_value=2)
        svc = self._make_service(store=store)
        preview = await svc.preview_delete_documents("kb_test", DocumentDeleteRequest(doc_type="article"))
        req = DocumentDeleteRequest(doc_type="article", confirm_token=preview.confirm_token)
        resp = await svc.delete_documents("kb_test", req)
        assert resp.deleted_count == 2
        assert resp.confirm_token == preview.confirm_token

    @pytest.mark.asyncio
    async def test_ingest_document(self):
        store = _make_vector_store_mock()
        store.upsert_points = AsyncMock()
        svc = self._make_service(store=store)
        result = await svc.ingest_document(
            collection="kb_test",
            filename="test.md",
            text="# Title\n\nSome content here.\n",
            doc_type="article",
            source="web",
            tag="ai",
            uploader="user1",
            strategy="fixed_overlap",
            chunking_params={"chunk_size": 50, "chunk_overlap": 10},
            enable_parent_child=False,
            parent_chunk_params={"chunk_size": 1000, "chunk_overlap": 100},
        )
        assert result["doc_id"]
        assert result["chunk_count"] > 0
        assert result["collection"] == "kb_test"
        store.upsert_points.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ingest_document_empty_text(self):
        store = _make_vector_store_mock()
        svc = self._make_service(store=store)
        result = await svc.ingest_document(
            collection="kb_test",
            filename="empty.md",
            text="",
            doc_type="article",
            source="web",
            tag="",
            uploader="user1",
            strategy="fixed_overlap",
            chunking_params={},
            enable_parent_child=False,
            parent_chunk_params={},
        )
        assert result["chunk_count"] == 0


# ===========================================================================
# TestKnowledgeServiceHelpers
# ===========================================================================

class TestKnowledgeServiceHelpers:
    def test_default_payload_indexes(self):
        indexes = _default_payload_indexes()
        fields = {i.field for i in indexes}
        assert fields == {"doc_type", "source", "tag", "uploader", "doc_id"}
        assert all(i.type == "keyword" for i in indexes)

    def test_doc_id_format(self):
        doc_id = _doc_id("file.md")
        assert doc_id.startswith("doc:")
        assert len(doc_id) == 20  # "doc:" + 16 hex chars

    def test_active_filters(self):
        req = DocumentDeleteRequest(doc_id="d1", source="web", tag="", doc_type="")
        filters = _active_filters(req)
        assert filters == {"doc_id": "d1", "source": "web"}

    def test_make_confirm_token_determinism(self):
        token1 = _make_confirm_token("kb", {"doc_id": "d1"})
        token2 = _make_confirm_token("kb", {"doc_id": "d1"})
        assert token1 == token2
        assert len(token1) == 32

    def test_make_confirm_token_different_inputs(self):
        t1 = _make_confirm_token("kb1", {"doc_id": "d1"})
        t2 = _make_confirm_token("kb2", {"doc_id": "d1"})
        assert t1 != t2


# ===========================================================================
# TestSchemas
# ===========================================================================

class TestSchemas:
    def test_chunking_params_validation(self):
        params = ChunkingParams(chunk_size=100, chunk_overlap=20)
        assert params.chunk_size == 100
        assert params.chunk_overlap == 20

    def test_chunking_params_overlap_must_lt_size(self):
        with pytest.raises(ValueError):
            ChunkingParams(chunk_size=50, chunk_overlap=50)

    def test_collection_create_request_defaults(self):
        req = CollectionCreateRequest(name="test")
        assert req.vector_dim == 1024
        assert req.distance == "Cosine"

    def test_document_upload_request_defaults(self):
        req = DocumentUploadRequest()
        assert req.doc_type == "article"
        assert req.strategy == ChunkingStrategy.FIXED_OVERLAP
        assert req.enable_parent_child is False

    def test_document_delete_request(self):
        req = DocumentDeleteRequest(doc_id="d1", confirm_token="abc")
        assert req.doc_id == "d1"
        assert req.confirm_token == "abc"
