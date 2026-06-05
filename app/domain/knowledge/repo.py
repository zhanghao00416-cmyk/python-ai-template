"""Knowledge base repository: Qdrant-backed document storage."""
from __future__ import annotations

from typing import Any

import structlog

from app.core.errors import AppError, ErrorCode, KnowledgeError, make_error
from app.infra.vector_store.base import VectorStoreBase
from app.schemas.vector_store import CollectionConfig, PointInsert, PointPayload, SearchResult

logger = structlog.get_logger("domain.knowledge.repo")


class KnowledgeRepo:
    """Repository for knowledge base collections and documents.

    Translates domain operations into the underlying vector store without
    exposing infrastructure details to callers.
    """

    def __init__(self, vector_store: VectorStoreBase) -> None:
        self._store = vector_store

    async def create_collection(self, config: CollectionConfig) -> None:
        """Create a collection (idempotent)."""
        try:
            await self._store.create_collection(config)
        except AppError:
            raise
        except Exception as exc:
            logger.error("kb_create_collection_failed", name=config.name, error=str(exc))
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Failed to create collection '{config.name}'",
            ) from exc

    async def delete_collection(self, name: str) -> None:
        """Delete a collection and all its points."""
        try:
            await self._store.delete_collection(name)
        except AppError:
            raise
        except Exception as exc:
            logger.error("kb_delete_collection_failed", name=name, error=str(exc))
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Failed to delete collection '{name}'",
            ) from exc

    async def collection_exists(self, name: str) -> bool:
        return await self._store.collection_exists(name)

    async def list_collections(self) -> list[dict[str, Any]]:
        """Return metadata for all collections."""
        try:
            names = await self._store.list_collections()
        except AppError:
            raise
        except Exception as exc:
            logger.error("kb_list_collections_failed", error=str(exc))
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                "Failed to list collections",
            ) from exc

        results: list[dict[str, Any]] = []
        for name in names:
            info = await self._store.get_collection_info(name)
            if info is None:
                continue
            results.append(info)
        return results

    async def get_collection_info(self, name: str) -> dict[str, Any] | None:
        return await self._store.get_collection_info(name)

    async def insert_document_chunks(
        self,
        collection: str,
        doc_id: str,
        chunks: list[PointInsert],
    ) -> int:
        """Insert or update all chunks belonging to ``doc_id``.

        Returns the number of chunks written.
        """
        if not chunks:
            return 0
        try:
            await self._store.upsert_points(collection, chunks)
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "kb_insert_chunks_failed",
                collection=collection,
                doc_id=doc_id,
                error=str(exc),
            )
            raise make_error(
                ErrorCode.KB_VECTOR_WRITE_FAILED,
                f"Failed to write chunks for document '{doc_id}'",
            ) from exc
        return len(chunks)

    async def list_documents(
        self,
        collection: str,
        doc_type: str | None = None,
        source: str | None = None,
        tag: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return aggregated document metadata for a collection.

        Documents are grouped by ``doc_id`` and counted by chunks.
        """
        query_filter: dict[str, list[str]] = {}
        if doc_type:
            query_filter["doc_type"] = [doc_type]
        if source:
            query_filter["source"] = [source]
        if tag:
            query_filter["tag"] = [tag]

        try:
            payloads = await self._store.scroll_points(
                collection=collection,
                query_filter=query_filter or None,
                limit=limit,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "kb_list_documents_failed",
                collection=collection,
                error=str(exc),
            )
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Failed to list documents in '{collection}'",
            ) from exc

        docs: dict[str, dict[str, Any]] = {}
        for payload in payloads:
            did = payload.get("doc_id")
            if not did:
                continue
            if did not in docs:
                docs[did] = {
                    "doc_id": did,
                    "doc_type": payload.get("doc_type", ""),
                    "source": payload.get("source", ""),
                    "tag": payload.get("tag", ""),
                    "source_file": payload.get("source_file", ""),
                    "chunk_count": 0,
                }
            docs[did]["chunk_count"] += 1  # type: ignore[operator]

        return list(docs.values())

    async def count_documents_by_filter(
        self,
        collection: str,
        doc_id: str | None = None,
        source: str | None = None,
        tag: str | None = None,
        doc_type: str | None = None,
    ) -> int:
        """Count chunks matching the supplied filters."""
        query_filter: dict[str, list[str]] = {}
        if doc_id:
            query_filter["doc_id"] = [doc_id]
        if source:
            query_filter["source"] = [source]
        if tag:
            query_filter["tag"] = [tag]
        if doc_type:
            query_filter["doc_type"] = [doc_type]

        try:
            payloads = await self._store.scroll_points(
                collection=collection,
                query_filter=query_filter or None,
                limit=10_000,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "kb_count_documents_failed",
                collection=collection,
                error=str(exc),
            )
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Failed to count documents in '{collection}'",
            ) from exc

        return len(payloads)

    async def delete_documents(
        self,
        collection: str,
        doc_id: str | None = None,
        source: str | None = None,
        tag: str | None = None,
        doc_type: str | None = None,
    ) -> int:
        """Delete all chunks matching the supplied filters.

        Returns the number of chunks removed.
        """
        query_filter: dict[str, list[str]] = {}
        if doc_id:
            query_filter["doc_id"] = [doc_id]
        if source:
            query_filter["source"] = [source]
        if tag:
            query_filter["tag"] = [tag]
        if doc_type:
            query_filter["doc_type"] = [doc_type]

        if not query_filter:
            raise KnowledgeError(
                code=ErrorCode.KB_FILE_NOT_FOUND,
                message="At least one filter is required to delete documents",
            )

        try:
            deleted = await self._store.delete_by_filter(
                collection=collection,
                query_filter=query_filter,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "kb_delete_documents_failed",
                collection=collection,
                error=str(exc),
            )
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Failed to delete documents from '{collection}'",
            ) from exc

        return deleted

    async def search_chunks(
        self,
        collection: str,
        query_vector: list[float],
        sparse_vector: dict[int, float] | None,
        strategy: str,
        top_k: int,
        score_threshold: float | None,
        query_filter: dict[str, list[str]] | None,
    ) -> list[SearchResult]:
        """Search for relevant chunks in a collection.

        Delegates to the underlying vector store with the chosen strategy.
        """
        try:
            return await self._store.search_by_strategy(
                collection=collection,
                query_vector=query_vector,
                sparse_vector=sparse_vector,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=query_filter,
                strategy=strategy,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "kb_search_chunks_failed",
                collection=collection,
                strategy=strategy,
                error=str(exc),
            )
            raise make_error(
                ErrorCode.RAG_RETRIEVAL_FAILED,
                f"Search failed for collection '{collection}'",
            ) from exc

    async def get_parent_chunks(
        self,
        collection: str,
        parent_ids: list[str],
    ) -> list[SearchResult]:
        """Fetch parent chunks by their IDs."""
        if not parent_ids:
            return []
        query_filter = {"parent_id": parent_ids}
        try:
            payloads = await self._store.scroll_points(
                collection=collection,
                query_filter=query_filter,
                limit=len(parent_ids) * 2,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "kb_get_parent_chunks_failed",
                collection=collection,
                error=str(exc),
            )
            return []

        results: list[SearchResult] = []
        seen: set[str] = set()
        for payload in payloads:
            cid = payload.get("_id") or payload.get("chunk_id")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            results.append(
                SearchResult(
                    id=str(cid),
                    score=0.0,
                    payload=payload,
                )
            )
        return results

    def build_point_insert(
        self,
        point_id: str,
        vector: list[float],
        sparse_vector: dict[int, float] | None,
        payload: PointPayload,
    ) -> PointInsert:
        """Factory helper to build a PointInsert from domain payload."""
        return PointInsert(
            id=point_id,
            vector=vector,
            sparse_vector=sparse_vector,
            payload=payload.model_dump(mode="json"),
        )
