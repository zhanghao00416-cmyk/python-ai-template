from __future__ import annotations

import asyncio
from typing import Any

import structlog
from qdrant_client import models
from qdrant_client.async_qdrant_client import AsyncQdrantClient

import time

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode, InfraError, make_error
from app.core.metrics import record_kb_query, record_kb_document_count
from app.infra.vector_store.base import VectorStoreBase
from app.infra.vector_store.utils import (
    build_payload_index_params,
    build_query_filter,
    get_distance,
)
from app.schemas.vector_store import (
    CollectionConfig,
    PointInsert,
    SearchResult,
)

logger = structlog.get_logger("infra.vector_store.qdrant")


class QdrantVectorStore(VectorStoreBase):

    def __init__(
        self,
        url: str | None = None,
        timeout: int | None = None,
        sparse_vector_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self._url = url or settings.qdrant.url
        self._timeout = timeout or settings.qdrant.timeout
        self._sparse_vector_name = (
            sparse_vector_name or settings.qdrant.sparse_vector_name
        )
        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                url=self._url,
                timeout=float(self._timeout),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
            logger.info("qdrant_vector_store.closed")

    async def create_collection(self, config: CollectionConfig) -> None:
        client = await self._get_client()
        try:
            exists = await asyncio.wait_for(
                client.collection_exists(config.name),
                timeout=float(self._timeout),
            )
        except Exception as exc:
            logger.error("qdrant_collection_check_failed", name=config.name, error=str(exc))
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Qdrant collection check failed for '{config.name}'",
            ) from exc

        if exists:
            logger.info("qdrant_collection_already_exists", name=config.name)
            await self._ensure_payload_indexes(client, config)
            return

        distance = get_distance(config.distance)
        vectors_config = models.VectorParams(
            size=config.vector_dim,
            distance=distance,
        )
        sparse_vectors_config: dict[str, models.SparseVectorParams] = {}
        if config.sparse_vector:
            sparse_vectors_config[self._sparse_vector_name] = models.SparseVectorParams(
                index=models.SparseIndexParams(on_disk=False),
            )

        try:
            await asyncio.wait_for(
                client.create_collection(
                    collection_name=config.name,
                    vectors_config=vectors_config,
                    sparse_vectors_config=sparse_vectors_config or None,
                ),
                timeout=float(self._timeout),
            )
            logger.info(
                "qdrant_collection_created",
                name=config.name,
                vector_dim=config.vector_dim,
                distance=config.distance,
                sparse_vector=config.sparse_vector,
            )
        except Exception as exc:
            logger.error("qdrant_collection_create_failed", name=config.name, error=str(exc))
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Failed to create collection '{config.name}'",
            ) from exc

        await self._ensure_payload_indexes(client, config)

    async def _ensure_payload_indexes(
        self, client: AsyncQdrantClient, config: CollectionConfig
    ) -> None:
        existing_fields = await self._get_existing_index_fields(client, config.name)
        index_params = build_payload_index_params(config.payload_indexes)

        for field_name, field_schema in index_params:
            if field_name in existing_fields:
                logger.debug("qdrant_payload_index_exists", field=field_name)
                continue
            try:
                await asyncio.wait_for(
                    client.create_payload_index(
                        collection_name=config.name,
                        field_name=field_name,
                        field_schema=field_schema,
                    ),
                    timeout=float(self._timeout),
                )
                logger.info("qdrant_payload_index_created", field=field_name)
            except Exception as exc:
                err_msg = str(exc)
                if "already" in err_msg.lower():
                    logger.info("qdrant_payload_index_exists", field=field_name)
                else:
                    logger.error(
                        "qdrant_payload_index_create_failed",
                        field=field_name,
                        error=str(exc),
                    )

    async def _get_existing_index_fields(
        self, client: AsyncQdrantClient, collection_name: str
    ) -> set[str]:
        try:
            info = await asyncio.wait_for(
                client.get_collection(collection_name),
                timeout=float(self._timeout),
            )
            schema = info.payload_schema or {}
            return set(schema.keys())
        except Exception:
            return set()

    async def delete_collection(self, name: str) -> None:
        client = await self._get_client()
        try:
            await asyncio.wait_for(
                client.delete_collection(name),
                timeout=float(self._timeout),
            )
            logger.info("qdrant_collection_deleted", name=name)
        except Exception as exc:
            logger.error("qdrant_collection_delete_failed", name=name, error=str(exc))
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Failed to delete collection '{name}'",
            ) from exc

    async def collection_exists(self, name: str) -> bool:
        client = await self._get_client()
        try:
            return await asyncio.wait_for(
                client.collection_exists(name),
                timeout=float(self._timeout),
            )
        except Exception as exc:
            logger.error("qdrant_collection_exists_check_failed", name=name, error=str(exc))
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Failed to check collection existence for '{name}'",
            ) from exc

    async def list_collections(self) -> list[str]:
        client = await self._get_client()
        try:
            result = await asyncio.wait_for(
                client.get_collections(),
                timeout=float(self._timeout),
            )
            return [c.name for c in result.collections]
        except Exception as exc:
            logger.error("qdrant_list_collections_failed", error=str(exc))
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                "Failed to list collections",
            ) from exc

    async def get_collection_info(self, name: str) -> dict[str, Any] | None:
        client = await self._get_client()
        try:
            exists = await asyncio.wait_for(
                client.collection_exists(name),
                timeout=float(self._timeout),
            )
            if not exists:
                return None
            info = await asyncio.wait_for(
                client.get_collection(name),
                timeout=float(self._timeout),
            )
            points_count = info.points_count
            record_kb_document_count(collection=name, count=points_count)
            return {
                "name": name,
                "vector_dim": info.config.params.vectors.size,
                "status": str(info.status),
                "points_count": points_count,
            }
        except Exception as exc:
            logger.error("qdrant_get_collection_info_failed", name=name, error=str(exc))
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Failed to get collection info for '{name}'",
            ) from exc

    async def upsert_points(
        self, collection: str, points: list[PointInsert]
    ) -> None:
        client = await self._get_client()
        sdk_points: list[models.PointStruct] = []
        for item in points:
            point_vector: dict[str, models.VectorStruct] = {
                "": item.vector,
            }
            if item.sparse_vector is not None:
                point_vector[self._sparse_vector_name] = models.SparseVector(
                    indices=list(item.sparse_vector.keys()),
                    values=list(item.sparse_vector.values()),
                )
            sdk_points.append(
                models.PointStruct(
                    id=item.id,
                    vector=point_vector,
                    payload=item.payload,
                )
            )
        try:
            await asyncio.wait_for(
                client.upsert(
                    collection_name=collection,
                    points=sdk_points,
                ),
                timeout=float(self._timeout),
            )
            logger.info(
                "qdrant_upsert_completed",
                collection=collection,
                point_count=len(sdk_points),
            )
        except AppError:
            raise
        except Exception as exc:
            logger.error("qdrant_upsert_failed", collection=collection, error=str(exc))
            raise make_error(
                ErrorCode.KB_VECTOR_WRITE_FAILED,
                f"Vector write failed for collection '{collection}'",
            ) from exc

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 5,
        score_threshold: float | None = None,
        query_filter: dict[str, list[str]] | None = None,
    ) -> list[SearchResult]:
        client = await self._get_client()
        filter_obj = build_query_filter(query_filter)
        start = time.perf_counter()
        try:
            results = await asyncio.wait_for(
                client.query_points(
                    collection_name=collection,
                    query=query_vector,
                    limit=limit,
                    score_threshold=score_threshold,
                    query_filter=filter_obj,
                ),
                timeout=float(self._timeout),
            )
            points = results.points if hasattr(results, "points") else results
            return [
                SearchResult(
                    id=str(p.id),
                    score=p.score if hasattr(p, "score") else 0.0,
                    payload=p.payload or {},
                )
                for p in points
            ]
        except AppError:
            raise
        except Exception as exc:
            logger.error("qdrant_search_failed", collection=collection, error=str(exc))
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Search failed for collection '{collection}'",
            ) from exc
        finally:
            record_kb_query(collection=collection, strategy="similarity", duration=time.perf_counter() - start)

    async def hybrid_search(
        self,
        collection: str,
        query_vector: list[float],
        sparse_vector: dict[int, float],
        limit: int = 5,
        score_threshold: float | None = None,
        query_filter: dict[str, list[str]] | None = None,
        alpha: float = 0.7,
    ) -> list[SearchResult]:
        client = await self._get_client()
        filter_obj = build_query_filter(query_filter)
        prefetch_dense = models.Prefetch(
            query=query_vector,
            using="",
            limit=limit * 3,
            filter=filter_obj,
        )
        prefetch_sparse = models.Prefetch(
            query=models.SparseVector(
                indices=list(sparse_vector.keys()),
                values=list(sparse_vector.values()),
            ),
            using=self._sparse_vector_name,
            limit=limit * 3,
            filter=filter_obj,
        )
        start = time.perf_counter()
        try:
            results = await asyncio.wait_for(
                client.query_points(
                    collection_name=collection,
                    prefetch=[prefetch_dense, prefetch_sparse],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    limit=limit,
                    score_threshold=score_threshold,
                ),
                timeout=float(self._timeout),
            )
            points = results.points if hasattr(results, "points") else results
            return [
                SearchResult(
                    id=str(p.id),
                    score=p.score if hasattr(p, "score") else 0.0,
                    payload=p.payload or {},
                )
                for p in points
            ]
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "qdrant_hybrid_search_failed",
                collection=collection,
                error=str(exc),
            )
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Hybrid search failed for collection '{collection}'",
            ) from exc
        finally:
            record_kb_query(collection=collection, strategy="hybrid", duration=time.perf_counter() - start)

    async def search_by_strategy(
        self,
        collection: str,
        query_vector: list[float],
        sparse_vector: dict[int, float] | None = None,
        limit: int = 5,
        score_threshold: float | None = None,
        query_filter: dict[str, list[str]] | None = None,
        strategy: str = "hybrid",
        alpha: float = 0.7,
    ) -> list[SearchResult]:
        if strategy in ("hybrid", "rrf") and sparse_vector is not None:
            return await self.hybrid_search(
                collection=collection,
                query_vector=query_vector,
                sparse_vector=sparse_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
                alpha=alpha,
            )
        if strategy == "keyword" and sparse_vector is not None:
            return await self._sparse_search(
                collection=collection,
                sparse_vector=sparse_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
            )
        return await self.search(
            collection=collection,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=query_filter,
        )

    async def _sparse_search(
        self,
        collection: str,
        sparse_vector: dict[int, float],
        limit: int = 5,
        score_threshold: float | None = None,
        query_filter: dict[str, list[str]] | None = None,
    ) -> list[SearchResult]:
        client = await self._get_client()
        filter_obj = build_query_filter(query_filter)
        sparse_vec = models.SparseVector(
            indices=list(sparse_vector.keys()),
            values=list(sparse_vector.values()),
        )
        start = time.perf_counter()
        try:
            results = await asyncio.wait_for(
                client.query_points(
                    collection_name=collection,
                    query=sparse_vec,
                    using=self._sparse_vector_name,
                    limit=limit,
                    score_threshold=score_threshold,
                    query_filter=filter_obj,
                ),
                timeout=float(self._timeout),
            )
            points = results.points if hasattr(results, "points") else results
            return [
                SearchResult(
                    id=str(p.id),
                    score=p.score if hasattr(p, "score") else 0.0,
                    payload=p.payload or {},
                )
                for p in points
            ]
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "qdrant_sparse_search_failed",
                collection=collection,
                error=str(exc),
            )
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Sparse search failed for collection '{collection}'",
            ) from exc
        finally:
            record_kb_query(collection=collection, strategy="keyword", duration=time.perf_counter() - start)

    async def delete_points(self, collection: str, point_ids: list[str]) -> None:
        client = await self._get_client()
        try:
            await asyncio.wait_for(
                client.delete(
                    collection_name=collection,
                    points_selector=models.PointIdsList(
                        points=point_ids,
                    ),
                ),
                timeout=float(self._timeout),
            )
            logger.info(
                "qdrant_points_deleted",
                collection=collection,
                count=len(point_ids),
            )
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "qdrant_points_delete_failed",
                collection=collection,
                error=str(exc),
            )
            raise make_error(
                ErrorCode.QDRANT_UNAVAILABLE,
                f"Failed to delete points from '{collection}'",
            ) from exc

    async def delete_by_filter(
        self, collection: str, query_filter: dict[str, list[str]]
    ) -> int:
        client = await self._get_client()
        filter_obj = build_query_filter(query_filter)
        count = 0
        offset: str | int | None = None
        batch_limit = 100
        all_ids: list[str] = []
        while True:
            try:
                scroll_result = await asyncio.wait_for(
                    client.scroll(
                        collection_name=collection,
                        scroll_filter=filter_obj,
                        limit=batch_limit,
                        offset=offset,
                        with_payload=False,
                        with_vectors=False,
                    ),
                    timeout=float(self._timeout),
                )
            except AppError:
                raise
            except Exception as exc:
                logger.error(
                    "qdrant_delete_by_filter_scroll_failed",
                    collection=collection,
                    error=str(exc),
                )
                raise make_error(
                    ErrorCode.QDRANT_UNAVAILABLE,
                    f"Failed to scroll points in '{collection}'",
                ) from exc

            points, next_offset = scroll_result
            for p in points:
                all_ids.append(str(p.id))
                count += 1

            if next_offset is None or len(points) < batch_limit:
                break
            offset = next_offset

        if all_ids:
            try:
                await asyncio.wait_for(
                    client.delete(
                        collection_name=collection,
                        points_selector=models.PointIdsList(points=all_ids),
                    ),
                    timeout=float(self._timeout),
                )
                logger.info(
                    "qdrant_delete_by_filter_completed",
                    collection=collection,
                    deleted_count=count,
                )
            except AppError:
                raise
            except Exception as exc:
                logger.error(
                    "qdrant_delete_by_filter_failed",
                    collection=collection,
                    error=str(exc),
                )
                raise make_error(
                    ErrorCode.QDRANT_UNAVAILABLE,
                    f"Failed to delete points by filter in '{collection}'",
                ) from exc

        return count

    async def scroll_points(
        self,
        collection: str,
        query_filter: dict[str, list[str]] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        client = await self._get_client()
        filter_obj = build_query_filter(query_filter)
        all_payloads: list[dict[str, Any]] = []
        offset: str | int | None = None

        while True:
            try:
                scroll_result = await asyncio.wait_for(
                    client.scroll(
                        collection_name=collection,
                        scroll_filter=filter_obj,
                        limit=limit,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                    ),
                    timeout=float(self._timeout),
                )
            except AppError:
                raise
            except Exception as exc:
                logger.error(
                    "qdrant_scroll_failed",
                    collection=collection,
                    error=str(exc),
                )
                raise make_error(
                    ErrorCode.QDRANT_UNAVAILABLE,
                    f"Failed to scroll points in '{collection}'",
                ) from exc

            points, next_offset = scroll_result
            for p in points:
                if p.payload:
                    payload = dict(p.payload)
                    payload["_id"] = str(p.id)
                    all_payloads.append(payload)

            if next_offset is None or len(points) < limit:
                break
            offset = next_offset

        return all_payloads