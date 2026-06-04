from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import AppError, ErrorCode, KnowledgeError, InfraError, make_error
from app.infra.vector_store.base import VectorStoreBase
from app.infra.vector_store.qdrant_store import QdrantVectorStore
from app.infra.vector_store.utils import (
    build_query_filter,
    build_payload_index_params,
    get_distance,
)
from app.schemas.vector_store import (
    CollectionConfig,
    PayloadIndexConfig,
    PointInsert,
    SearchResult,
    RetrievalConfig,
)


class TestSchemas:
    def test_collection_config_defaults(self):
        cfg = CollectionConfig(name="test")
        assert cfg.name == "test"
        assert cfg.vector_dim == 1024
        assert cfg.distance == "Cosine"
        assert cfg.sparse_vector is True
        assert cfg.payload_indexes == []
        assert cfg.default_chunk_size == 500
        assert cfg.default_chunk_overlap == 50

    def test_collection_config_custom(self):
        cfg = CollectionConfig(
            name="safety",
            description="安全隐患",
            vector_dim=768,
            distance="Euclid",
            sparse_vector=False,
            payload_indexes=[
                PayloadIndexConfig(field="doc_type", type="keyword"),
                PayloadIndexConfig(field="source", type="keyword"),
            ],
            default_chunk_size=1000,
            default_chunk_overlap=100,
        )
        assert cfg.name == "safety"
        assert cfg.vector_dim == 768
        assert cfg.distance == "Euclid"
        assert cfg.sparse_vector is False
        assert len(cfg.payload_indexes) == 2

    def test_point_insert(self):
        p = PointInsert(
            id="test-1",
            vector=[0.1, 0.2, 0.3],
            payload={"doc_id": "doc1"},
        )
        assert p.id == "test-1"
        assert p.sparse_vector is None
        assert p.payload == {"doc_id": "doc1"}

    def test_point_insert_with_sparse(self):
        p = PointInsert(
            id="test-2",
            vector=[0.1, 0.2, 0.3],
            sparse_vector={0: 0.5, 3: 0.8},
            payload={"doc_id": "doc2"},
        )
        assert p.sparse_vector == {0: 0.5, 3: 0.8}

    def test_search_result(self):
        r = SearchResult(id="pt-1", score=0.95, payload={"text": "hello"})
        assert r.id == "pt-1"
        assert r.score == 0.95

    def test_retrieval_config_defaults(self):
        rc = RetrievalConfig()
        assert rc.default_top_k == 3
        assert rc.default_score_threshold == 0.5
        assert rc.enable_hybrid is True
        assert rc.hybrid_alpha == 0.7
        assert rc.enable_rerank is False

    def test_point_payload(self):
        pp = __import__("app.schemas.vector_store", fromlist=["PointPayload"]).PointPayload(
            doc_id="doc1",
            collection="general",
            text="sample text",
        )
        assert pp.doc_id == "doc1"
        assert pp.is_parent is False
        assert pp.parent_id is None


class TestUtils:
    def test_build_query_filter_none(self):
        assert build_query_filter(None) is None

    def test_build_query_filter_empty(self):
        assert build_query_filter({}) is None

    def test_build_query_filter_single_value(self):
        filt = build_query_filter({"doc_type": ["report"]})
        assert filt is not None
        assert len(filt.must) == 1
        assert filt.must[0].key == "doc_type"

    def test_build_query_filter_multi_value(self):
        filt = build_query_filter({"doc_type": ["report", "manual"], "source": ["internal"]})
        assert filt is not None
        assert len(filt.must) == 2

    def test_build_query_filter_empty_values_skipped(self):
        filt = build_query_filter({"doc_type": []})
        assert filt is None

    def test_get_distance(self):
        from qdrant_client import models

        assert get_distance("Cosine") == models.Distance.COSINE
        assert get_distance("cosine") == models.Distance.COSINE
        assert get_distance("Euclid") == models.Distance.EUCLID
        assert get_distance("Dot") == models.Distance.DOT
        assert get_distance("unknown") == models.Distance.COSINE

    def test_build_payload_index_params_keyword(self):
        from qdrant_client import models

        indexes = [PayloadIndexConfig(field="doc_type", type="keyword")]
        result = build_payload_index_params(indexes)
        assert len(result) == 1
        assert result[0][0] == "doc_type"
        assert result[0][1] == models.PayloadSchemaType.KEYWORD

    def test_build_payload_index_params_text(self):
        from qdrant_client import models

        indexes = [PayloadIndexConfig(field="text", type="text")]
        result = build_payload_index_params(indexes)
        assert len(result) == 1
        assert result[0][0] == "text"
        assert isinstance(result[0][1], models.TextIndexParams)

    def test_build_payload_index_params_integer(self):
        from qdrant_client import models

        indexes = [PayloadIndexConfig(field="chunk_index", type="integer")]
        result = build_payload_index_params(indexes)
        assert result[0][1] == models.PayloadSchemaType.INTEGER


class TestQdrantVectorStore:
    def _make_store(self):
        store = QdrantVectorStore.__new__(QdrantVectorStore)
        store._url = "http://localhost:6333"
        store._timeout = 30
        store._sparse_vector_name = "bm25"
        store._client = None
        return store

    @pytest.mark.asyncio
    async def test_create_collection_new(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.collection_exists = AsyncMock(return_value=False)
        mock_client.create_collection = AsyncMock()
        mock_client.create_payload_index = AsyncMock()
        mock_client.get_collection = AsyncMock(
            return_value=MagicMock(payload_schema={})
        )
        store._client = mock_client

        from qdrant_client import models

        config = CollectionConfig(
            name="test_coll",
            vector_dim=1024,
            distance="Cosine",
            sparse_vector=True,
            payload_indexes=[
                PayloadIndexConfig(field="doc_type", type="keyword"),
            ],
        )
        await store.create_collection(config)
        mock_client.create_collection.assert_called_once()
        call_kwargs = mock_client.create_collection.call_args[1]
        assert call_kwargs["collection_name"] == "test_coll"

    @pytest.mark.asyncio
    async def test_create_collection_exists(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.collection_exists = AsyncMock(return_value=True)
        mock_client.get_collection = AsyncMock(
            return_value=MagicMock(payload_schema={"doc_type": "keyword"})
        )
        store._client = mock_client

        config = CollectionConfig(name="test_coll")
        await store.create_collection(config)
        mock_client.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_collection(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.delete_collection = AsyncMock()
        store._client = mock_client

        await store.delete_collection("test_coll")
        mock_client.delete_collection.assert_called_once_with("test_coll")

    @pytest.mark.asyncio
    async def test_collection_exists(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.collection_exists = AsyncMock(return_value=True)
        store._client = mock_client

        result = await store.collection_exists("test_coll")
        assert result is True

    @pytest.mark.asyncio
    async def test_list_collections(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_collection = MagicMock()
        mock_collection.name = "general"
        mock_client.get_collections = AsyncMock(
            return_value=MagicMock(collections=[mock_collection])
        )
        store._client = mock_client

        result = await store.list_collections()
        assert "general" in result

    @pytest.mark.asyncio
    async def test_upsert_points(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.upsert = AsyncMock()
        store._client = mock_client

        points = [
            PointInsert(
                id="pt-1",
                vector=[0.1, 0.2, 0.3],
                payload={"doc_id": "doc1", "text": "hello"},
            ),
        ]
        await store.upsert_points("general", points)
        mock_client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_points_with_sparse(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.upsert = AsyncMock()
        store._client = mock_client

        points = [
            PointInsert(
                id="pt-1",
                vector=[0.1, 0.2, 0.3],
                sparse_vector={0: 0.5, 3: 0.8},
                payload={"doc_id": "doc1"},
            ),
        ]
        await store.upsert_points("general", points)
        mock_client.upsert.assert_called_once()
        call_args = mock_client.upsert.call_args
        point_struct = call_args[1]["points"][0]
        assert "bm25" in point_struct.vector

    @pytest.mark.asyncio
    async def test_search(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_point = MagicMock()
        mock_point.id = "pt-1"
        mock_point.score = 0.95
        mock_point.payload = {"doc_id": "doc1", "text": "hello"}
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        mock_client.query_points = AsyncMock(return_value=mock_result)
        store._client = mock_client

        results = await store.search(
            collection="general",
            query_vector=[0.1] * 1024,
            limit=5,
        )
        assert len(results) == 1
        assert results[0].score == 0.95
        assert results[0].payload["doc_id"] == "doc1"

    @pytest.mark.asyncio
    async def test_hybrid_search(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_point = MagicMock()
        mock_point.id = "pt-1"
        mock_point.score = 0.88
        mock_point.payload = {"doc_id": "doc1"}
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        mock_client.query_points = AsyncMock(return_value=mock_result)
        store._client = mock_client

        results = await store.hybrid_search(
            collection="general",
            query_vector=[0.1] * 1024,
            sparse_vector={0: 0.5, 5: 0.8},
            limit=3,
        )
        assert len(results) == 1
        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]
        assert "prefetch" in call_kwargs
        assert len(call_kwargs["prefetch"]) == 2

    @pytest.mark.asyncio
    async def test_search_by_strategy_hybrid(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_point = MagicMock()
        mock_point.id = "pt-1"
        mock_point.score = 0.9
        mock_point.payload = {}
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        mock_client.query_points = AsyncMock(return_value=mock_result)
        store._client = mock_client

        results = await store.search_by_strategy(
            collection="general",
            query_vector=[0.1] * 1024,
            sparse_vector={0: 0.5},
            strategy="hybrid",
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_by_strategy_similarity(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_point = MagicMock()
        mock_point.id = "pt-1"
        mock_point.score = 0.87
        mock_point.payload = {}
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        mock_client.query_points = AsyncMock(return_value=mock_result)
        store._client = mock_client

        results = await store.search_by_strategy(
            collection="general",
            query_vector=[0.1] * 1024,
            strategy="similarity",
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_by_strategy_keyword(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_point = MagicMock()
        mock_point.id = "pt-1"
        mock_point.score = 0.75
        mock_point.payload = {}
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        mock_client.query_points = AsyncMock(return_value=mock_result)
        store._client = mock_client

        results = await store.search_by_strategy(
            collection="general",
            query_vector=[0.1] * 1024,
            sparse_vector={0: 0.5, 3: 0.8},
            strategy="keyword",
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_delete_points(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock()
        store._client = mock_client

        await store.delete_points("general", ["pt-1", "pt-2"])
        mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_filter(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_point1 = MagicMock()
        mock_point1.id = "pt-1"
        mock_point1.payload = {"doc_type": "report"}
        mock_point2 = MagicMock()
        mock_point2.id = "pt-2"
        mock_point2.payload = {"doc_type": "report"}
        mock_client.scroll = AsyncMock(
            return_value=([mock_point1, mock_point2], None)
        )
        mock_client.delete = AsyncMock()
        store._client = mock_client

        count = await store.delete_by_filter("general", {"doc_type": ["report"]})
        assert count == 2
        mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_scroll_points(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_point = MagicMock()
        mock_point.id = "pt-1"
        mock_point.payload = {"doc_id": "doc1", "text": "hello"}
        mock_client.scroll = AsyncMock(
            return_value=([mock_point], None)
        )
        store._client = mock_client

        results = await store.scroll_points("general", limit=10)
        assert len(results) == 1
        assert results[0]["doc_id"] == "doc1"
        assert results[0]["_id"] == "pt-1"

    @pytest.mark.asyncio
    async def test_close(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        store._client = mock_client

        await store.close()
        mock_client.close.assert_called_once()
        assert store._client is None

    @pytest.mark.asyncio
    async def test_close_none_client(self):
        store = self._make_store()
        assert store._client is None
        await store.close()

    @pytest.mark.asyncio
    async def test_error_handling_create_collection(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.collection_exists = AsyncMock(side_effect=Exception("connection failed"))
        store._client = mock_client

        config = CollectionConfig(name="test_coll")
        with pytest.raises(InfraError) as exc_info:
            await store.create_collection(config)
        assert exc_info.value.code == ErrorCode.QDRANT_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_error_handling_upsert(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.upsert = AsyncMock(side_effect=Exception("write failed"))
        store._client = mock_client

        points = [PointInsert(id="pt-1", vector=[0.1], payload={})]
        with pytest.raises(KnowledgeError) as exc_info:
            await store.upsert_points("general", points)
        assert exc_info.value.code == ErrorCode.KB_VECTOR_WRITE_FAILED

    @pytest.mark.asyncio
    async def test_error_handling_search(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.query_points = AsyncMock(side_effect=Exception("search failed"))
        store._client = mock_client

        with pytest.raises(InfraError) as exc_info:
            await store.search("general", [0.1] * 1024)
        assert exc_info.value.code == ErrorCode.QDRANT_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_error_handling_propagates_app_error(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.collection_exists = AsyncMock(
            side_effect=InfraError(ErrorCode.QDRANT_UNAVAILABLE, "test")
        )
        store._client = mock_client

        with pytest.raises(InfraError):
            await store.collection_exists("test_coll")

    @pytest.mark.asyncio
    async def test_get_collection_info_not_exists(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.collection_exists = AsyncMock(return_value=False)
        store._client = mock_client

        result = await store.get_collection_info("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_collection_info_exists(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.collection_exists = AsyncMock(return_value=True)
        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 1024
        mock_info.status = "green"
        mock_info.points_count = 5
        mock_client.get_collection = AsyncMock(return_value=mock_info)
        store._client = mock_client

        result = await store.get_collection_info("general")
        assert result is not None
        assert result["vector_dim"] == 1024
        assert result["points_count"] == 5

    @pytest.mark.asyncio
    async def test_delete_by_filter_empty_result(self):
        store = self._make_store()
        mock_client = AsyncMock()
        mock_client.scroll = AsyncMock(return_value=([], None))
        store._client = mock_client

        count = await store.delete_by_filter("general", {"doc_type": ["nonexistent"]})
        assert count == 0
        mock_client.delete.assert_not_called()


class TestVectorStoreBaseAbstract:
    def test_cannot_instantiate_base(self):
        with pytest.raises(TypeError):
            VectorStoreBase()

    def test_qdrant_store_is_subclass(self):
        assert issubclass(QdrantVectorStore, VectorStoreBase)


class TestConfigKnowledgeSettings:
    def test_knowledge_settings_defaults(self):
        from app.core.config import KnowledgeSettings, RetrievalSettings

        ks = KnowledgeSettings()
        assert ks.collections == []
        assert ks.retrieval.default_top_k == 3
        assert ks.retrieval.enable_hybrid is True

    def test_settings_includes_knowledge(self):
        from app.core.config import Settings, KnowledgeSettings

        s = Settings()
        assert hasattr(s, "knowledge")
        assert isinstance(s.knowledge, KnowledgeSettings)

    def test_knowledge_settings_from_yaml_collections(self):
        from app.core.config import KnowledgeSettings, RetrievalSettings

        ks = KnowledgeSettings(
            collections=[
                {"name": "general", "vector_dim": 1024},
                {"name": "safety", "vector_dim": 768},
            ]
        )
        assert len(ks.collections) == 2
        assert ks.collections[0]["name"] == "general"


class TestBootstrapIntegration:
    @pytest.mark.asyncio
    async def test_init_qdrant_collections_with_config(self):
        from app.bootstrap import _init_qdrant_collections
        from app.infra.vector_store import VectorStoreBase, CollectionConfig
        from app.core.di import container

        mock_store = AsyncMock(spec=VectorStoreBase)
        container.register(VectorStoreBase, lambda v=mock_store: v, singleton=True)

        mock_settings = MagicMock()
        mock_settings.knowledge = MagicMock()
        mock_settings.knowledge.collections = [
            {
                "name": "general",
                "description": "通用知识库",
                "vector_dim": 1024,
                "distance": "Cosine",
                "sparse_vector": True,
                "payload_indexes": [
                    {"field": "doc_type", "type": "keyword"},
                ],
                "default_chunk_size": 500,
                "default_chunk_overlap": 50,
            }
        ]

        await _init_qdrant_collections(mock_settings)
        mock_store.create_collection.assert_called_once()
        call_args = mock_store.create_collection.call_args[0][0]
        assert isinstance(call_args, CollectionConfig)
        assert call_args.name == "general"

        container.reset(VectorStoreBase)

    @pytest.mark.asyncio
    async def test_init_qdrant_collections_empty(self):
        from app.bootstrap import _init_qdrant_collections

        mock_settings = MagicMock()
        mock_settings.knowledge = MagicMock()
        mock_settings.knowledge.collections = []

        await _init_qdrant_collections(mock_settings)


class TestErrorCodes:
    def test_kb_error_codes_exist(self):
        assert ErrorCode.KB_UPLOAD_FAILED == 6001
        assert ErrorCode.KB_FILENAME_EXISTS == 6002
        assert ErrorCode.KB_FILE_NOT_FOUND == 6003
        assert ErrorCode.KB_FORMAT_UNSUPPORTED == 6004
        assert ErrorCode.KB_VECTOR_WRITE_FAILED == 6005
        assert ErrorCode.KB_CHUNK_LIMIT_EXCEEDED == 6006

    def test_qdrant_unavailable_code(self):
        assert ErrorCode.QDRANT_UNAVAILABLE == 1202

    def test_make_error_infra(self):
        err = make_error(ErrorCode.QDRANT_UNAVAILABLE, "test")
        assert isinstance(err, InfraError)
        assert err.code == 1202

    def test_make_error_knowledge(self):
        err = make_error(ErrorCode.KB_VECTOR_WRITE_FAILED, "test")
        assert isinstance(err, KnowledgeError)
        assert err.code == 6005

    def test_error_http_status_mapping(self):
        from app.core.errors import ERROR_HTTP_STATUS

        assert ERROR_HTTP_STATUS[ErrorCode.QDRANT_UNAVAILABLE] == 503
        assert ERROR_HTTP_STATUS[ErrorCode.KB_VECTOR_WRITE_FAILED] == 500
        assert ERROR_HTTP_STATUS[ErrorCode.KB_FILE_NOT_FOUND] == 404