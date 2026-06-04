from __future__ import annotations

import structlog
from typing import Any, AsyncGenerator, Generic, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import Select, select, func, update as sa_update, delete as sa_delete
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = structlog.get_logger("infra.database")

T = TypeVar("T")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base:
    """Declarative base for all ORM models. Metadata shared project-wide."""
    pass


def init_db_engine() -> AsyncEngine:
    """Create and register the async engine. Called from bootstrap."""
    global _engine, _session_factory
    settings = get_settings()
    _engine = create_async_engine(
        settings.database.url,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        pool_timeout=30,
        pool_recycle=3600,
        echo=False,
    )
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db_engine() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Session factory not initialized. Call init_db_engine() first.")
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session with auto commit/rollback."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine (called during shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


class Pagination:
    """Pagination parameters for list queries."""

    def __init__(
        self,
        offset: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> None:
        self.offset = max(0, offset)
        self.limit = max(1, min(limit, 100))
        self.sort_by = sort_by
        self.sort_order = sort_order.lower()
        if self.sort_order not in ("asc", "desc"):
            self.sort_order = "desc"


class PaginatedResult(Generic[T]):
    """Paginated result container."""

    def __init__(self, items: Sequence[T], total: int, offset: int, limit: int) -> None:
        self.items = items
        self.total = total
        self.offset = offset
        self.limit = limit

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
        }


class BaseRepo(Generic[T]):
    """Generic async repository providing CRUD operations.

    Domain repos inherit from this class, specializing T to their model.
    """

    def __init__(self, model: type[T], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, id: UUID | str) -> T | None:
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> T:
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: UUID | str, data: dict[str, Any]) -> T | None:
        instance = await self.get_by_id(id)
        if instance is None:
            return None
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, id: UUID | str) -> bool:
        instance = await self.get_by_id(id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        pagination: Pagination | None = None,
    ) -> PaginatedResult[T]:
        stmt = select(self.model)
        count_stmt = select(func.count()).select_from(self.model)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    stmt = stmt.where(getattr(self.model, key) == value)
                    count_stmt = count_stmt.where(getattr(self.model, key) == value)

        if pagination:
            sort_col = getattr(self.model, pagination.sort_by, None)
            if sort_col is not None:
                if pagination.sort_order == "asc":
                    stmt = stmt.order_by(sort_col.asc())
                else:
                    stmt = stmt.order_by(sort_col.desc())
            stmt = stmt.offset(pagination.offset).limit(pagination.limit)

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        pg = pagination or Pagination()
        return PaginatedResult(
            items=items,
            total=total,
            offset=pg.offset,
            limit=pg.limit,
        )

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        count_stmt = select(func.count()).select_from(self.model)
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    count_stmt = count_stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(count_stmt)
        return result.scalar() or 0