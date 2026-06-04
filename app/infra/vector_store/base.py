from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.vector_store import CollectionConfig, PointInsert, SearchResult


class VectorStoreBase(ABC):

    @abstractmethod
    async def create_collection(self, config: CollectionConfig) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_collection(self, name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def collection_exists(self, name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def list_collections(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def upsert_points(
        self, collection: str, points: list[PointInsert]
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 5,
        score_threshold: float | None = None,
        query_filter: dict[str, list[str]] | None = None,
    ) -> list[SearchResult]:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    async def delete_points(
        self, collection: str, point_ids: list[str]
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_filter(
        self, collection: str, query_filter: dict[str, list[str]]
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    async def scroll_points(
        self,
        collection: str,
        query_filter: dict[str, list[str]] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_collection_info(
        self, name: str
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError