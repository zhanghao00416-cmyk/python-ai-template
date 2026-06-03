# Persistence Layer Specification

## Overview

The persistence layer (`app/infra/database.py`) provides a unified repository pattern over PostgreSQL (AsyncEngine + SQLAlchemy), with Redis for caching and Qdrant for vector storage. All database access goes through `BaseRepo` subclasses in domain packages.

## BaseRepo Pattern — [TBD: filled by F02]

### Base Repository

```python
class BaseRepo(Generic[T]):
    """Generic async repository providing CRUD operations."""

    def __init__(self, model: type[T], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id: UUID) -> T | None:
        """Retrieve a single entity by primary key."""

    async def create(self, data: dict) -> T:
        """Create a new entity."""

    async def update(self, id: UUID, data: dict) -> T:
        """Update an existing entity."""

    async def delete(self, id: UUID) -> None:
        """Soft or hard delete an entity."""

    async def list(self, filters: dict | None = None, pagination: Pagination | None = None) -> list[T]:
        """List entities with optional filters and pagination."""

    async def count(self, filters: dict | None = None) -> int:
        """Count entities matching filters."""
```

### Domain-Specific Repositories — [TBD: filled by subsequent work orders]

```python
# In app/domain/chat/repo.py
class SessionRepo(BaseRepo[Session]):
    async def get_by_user(self, user_id: str) -> list[Session]: ...

# In app/domain/chat/repo.py
class MessageRepo(BaseRepo[Message]):
    async def get_recent(self, session_id: UUID, limit: int) -> list[Message]: ...
```

## AsyncEngine Setup — [TBD: filled by F02]

```python
# app/infra/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

engine = create_async_engine(
    config.DATABASE_URL,       # postgresql+asyncpg://...
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession)
```

### Session Management — [TBD: filled by F02]

```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Connection Lifecycle — [TBD: filled by F02]

| Phase | Action |
|-------|--------|
| App startup | Create engine, register with DI container |
| Request | Open session via `Depends(get_session)` |
| Request end | Commit or rollback |
| App shutdown | Dispose engine |

## Alembic Migrations — [TBD: filled by F02]

- Migration directory: `migrations/`
- Auto-generate from SQLAlchemy models: `alembic revision --autogenerate -m "description"`
- Apply: `alembic upgrade head`
- Each work order that modifies the data model must include a migration

### Migration Workflow

1. Modify model in `app/infra/database.py` or domain models
2. Run `alembic revision --autogenerate -m "FXX: description"`
3. Review the generated migration
4. Run `alembic upgrade head` to apply
5. Verify with `pytest tests/test_02_database.py`

## Redis Client — [TBD: filled by F02]

```python
# app/infra/redis_client.py
class RedisClient:
    def __init__(self, url: str, db: int = 0):
        self.client = redis.asyncio.from_url(url, db=db)

    async def ping(self) -> bool:
        """Health check."""

    async def get(self, key: str) -> str | None:
        """Get value by key."""

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """Set value with optional TTL."""

    async def delete(self, key: str) -> None:
        """Delete key."""

    async def incr(self, key: str) -> int:
        """Increment counter (for rate limiting)."""
```

## Vector Store — [TBD: filled by F05]

See `docs/04-kb/QDRANT_COLLECTION_CONFIG.md` for Qdrant persistence details.

## Error Handling — [TBD: filled by F02]

| Scenario | Error Code | Behavior |
|----------|-----------|----------|
| Connection failed | `0003 SERVICE_UNAVAILABLE` | Retry with backoff |
| Unique constraint violation | `0005 VALIDATION_ERROR` | Return conflict error |
| Row not found | `0005 VALIDATION_ERROR` | Return 404 |
| Transaction deadlock | `0007 DEPENDENCY_ERROR` | Retry with backoff |
| Redis unavailable | `0003 SERVICE_UNAVAILABLE` | Fall back to DB |

## Pagination — [TBD: filled by F02]

```python
class Pagination:
    offset: int = 0
    limit: int = 20
    sort_by: str = "created_at"
    sort_order: str = "desc"    # "asc" | "desc"

class PaginatedResult(Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int
```

[TBD: filled by work orders F02, F05, F07]