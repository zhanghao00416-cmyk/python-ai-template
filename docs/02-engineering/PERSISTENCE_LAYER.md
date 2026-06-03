# 持久化层规范

## 概述

持久化层（`app/infra/database.py`）在 PostgreSQL（AsyncEngine + SQLAlchemy）之上提供统一的仓库模式，并使用 Redis 进行缓存、Qdrant 进行向量存储。所有数据库访问均通过域包中的 `BaseRepo` 子类进行。

## BaseRepo 模式 — [TBD: filled by F02]

### 基础仓库

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

### 领域专用仓库 — [TBD: filled by subsequent work orders]

```python
# In app/domain/chat/repo.py
class SessionRepo(BaseRepo[Session]):
    async def get_by_user(self, user_id: str) -> list[Session]: ...

# In app/domain/chat/repo.py
class MessageRepo(BaseRepo[Message]):
    async def get_recent(self, session_id: UUID, limit: int) -> list[Message]: ...
```

## AsyncEngine 设置 — [TBD: filled by F02]

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

### 会话管理 — [TBD: filled by F02]

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

### 连接生命周期 — [TBD: filled by F02]

| 阶段 | 操作 |
|------|------|
| 应用启动 | 创建引擎，注册至 DI 容器 |
| 请求 | 通过 `Depends(get_session)` 打开会话 |
| 请求结束 | 提交或回滚 |
| 应用关闭 | 释放引擎 |

## Alembic 数据库迁移 — [TBD: filled by F02]

- 迁移目录：`migrations/`
- 从 SQLAlchemy 模型自动生成：`alembic revision --autogenerate -m "description"`
- 应用迁移：`alembic upgrade head`
- 修改数据模型的每个工单必须包含迁移

### 迁移工作流

1. 在 `app/infra/database.py` 或域模型中修改模型
2. 运行 `alembic revision --autogenerate -m "FXX: description"`
3. 审查生成的迁移
4. 运行 `alembic upgrade head` 应用迁移
5. 使用 `pytest tests/test_02_database.py` 验证

## Redis 客户端 — [TBD: filled by F02]

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

## 向量存储 — [TBD: filled by F05]

Qdrant 持久化详情请参见 `docs/04-kb/QDRANT_COLLECTION_CONFIG.md`。

## 错误处理 — [TBD: filled by F02]

| 场景 | 错误码 | 行为 |
|------|--------|------|
| 连接失败 | `0003 SERVICE_UNAVAILABLE` | 带退避策略重试 |
| 唯一约束冲突 | `0005 VALIDATION_ERROR` | 返回冲突错误 |
| 数据行未找到 | `0005 VALIDATION_ERROR` | 返回 404 |
| 事务死锁 | `0007 DEPENDENCY_ERROR` | 带退避策略重试 |
| Redis 不可用 | `0003 SERVICE_UNAVAILABLE` | 降级至数据库 |

## 分页 — [TBD: filled by F02]

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