# 持久化层规范

## 概述

持久化层（`app/infra/database.py`）在 PostgreSQL（AsyncEngine + SQLAlchemy）之上提供统一的仓库模式，并使用 Redis 进行缓存、Qdrant 进行向量存储。所有数据库访问均通过域包中的 `BaseRepo` 子类进行。

## BaseRepo 模式 — [filled by F02]

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

### 领域专用仓库 — [filled by F02, F07]

```python
# In app/domain/chat/repo.py
class SessionRepo(BaseRepo[Session]):
    async def get_by_user(self, user_id: str) -> list[Session]: ...

# In app/domain/chat/repo.py
class MessageRepo(BaseRepo[Message]):
    async def get_recent(self, session_id: UUID, limit: int) -> list[Message]: ...

# In app/domain/task/repo.py
class TaskRepo(BaseRepo[TaskModel]):
    async def get_by_task_id(self, task_id: UUID) -> TaskModel | None: ...
    async def create_task(self, data: dict) -> TaskModel: ...
    async def update_task(self, task_id: UUID, data: dict) -> TaskModel | None: ...
    async def list_tasks(self, task_type=None, status=None, user_id=None, pagination=None) -> tuple[list, int]: ...
```

## AsyncEngine 设置 — [filled by F02]

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

### 会话管理 — [filled by F02]

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

### 连接生命周期 — [filled by F02]

| 阶段 | 操作 |
|------|------|
| 应用启动 | 创建引擎，注册至 DI 容器 |
| 请求 | 通过 `Depends(get_session)` 打开会话 |
| 请求结束 | 提交或回滚 |
| 应用关闭 | 释放引擎 |

## Alembic 数据库迁移 — [filled by F02]

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

## Redis 客户端 — [filled by F02]

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

## 向量存储 — [filled by F05]

向量存储层位于 `app/infra/vector_store/`，提供 `VectorStoreBase` 抽象基类和 `QdrantVectorStore` 实现。

### 架构

```
app/infra/vector_store/
├── __init__.py          # 包导出
├── base.py              # VectorStoreBase ABC
├── qdrant_store.py      # QdrantVectorStore 实现
└── utils.py             # build_query_filter, build_payload_index_params, get_distance
```

### VectorStoreBase 接口

| 方法 | 说明 |
|------|------|
| `create_collection(config)` | 创建集合（含 payload 索引 + 稀疏向量） |
| `delete_collection(name)` | 删除集合 |
| `collection_exists(name)` | 检查集合是否存在 |
| `list_collections()` | 列出所有集合 |
| `upsert_points(collection, points)` | 插入/更新向量点 |
| `search(collection, query_vector, ...)` | 稠密向量检索 |
| `hybrid_search(collection, query_vector, sparse_vector, ...)` | 混合检索（RRF） |
| `search_by_strategy(collection, ..., strategy)` | 按策略检索：similarity/keyword/hybrid/rrf |
| `delete_points(collection, point_ids)` | 按 ID 删除 |
| `delete_by_filter(collection, query_filter)` | 按条件删除 |
| `scroll_points(collection, query_filter, ...)` | 分页遍历 |
| `get_collection_info(name)` | 获取集合信息 |
| `close()` | 关闭连接 |

### 启动时自动创建集合

`bootstrap.py` 中的 `_init_qdrant_collections()` 读取 `configs/default.yaml` 的 `knowledge.collections` 列表，自动创建配置中声明但尚不存在的集合。

### 配置

- `QdrantSettings`：`qdrant.url`、`qdrant.timeout`、`qdrant.sparse_vector_name`
- `KnowledgeSettings`：`knowledge.collections[]`、`knowledge.retrieval.*`
- `CollectionConfig` schema：name / vector_dim / distance / sparse_vector / payload_indexes / default_chunk_size / default_chunk_overlap

### 依赖方向

```
domain → services → infra/vector_store (仅经 VectorStoreBase 接口)
```

域代码永不直接使用 `qdrant_client` SDK，必须通过 `VectorStoreBase` 接口。

## 错误处理 — [filled by F02]

| 场景 | 错误码 | 行为 |
|------|--------|------|
| 连接失败 | `0003 SERVICE_UNAVAILABLE` | 带退避策略重试 |
| 唯一约束冲突 | `0005 VALIDATION_ERROR` | 返回冲突错误 |
| 数据行未找到 | `0005 VALIDATION_ERROR` | 返回 404 |
| 事务死锁 | `0007 DEPENDENCY_ERROR` | 带退避策略重试 |
| Redis 不可用 | `0003 SERVICE_UNAVAILABLE` | 降级至数据库 |

## 分页 — [filled by F02]

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

[filled by F02, F05, F07]