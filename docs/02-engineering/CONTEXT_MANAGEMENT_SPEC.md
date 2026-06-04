# 上下文管理规范

## 概述

上下文管理器由两层组成：`app/domain/session/`（会话/消息 CRUD）和 `app/services/context_manager.py`（上下文窗口截断 + Redis 缓存）。它确保 LLM 调用在 token 限制内接收到正确大小的上下文，同时保持对话连续性。

## 会话管理 — [filled by F09]

### 会话生命周期

```
Create → Active → (Idle timeout) → Expired
               ↓
            Delete
```

实现层：`app/domain/session/service.py` 中的 `SessionService`。

```python
class SessionService:
    async def create_session(self, request: SessionCreateRequest) -> SessionDetail:
    async def get_session(self, session_id: UUID) -> SessionDetail:
    async def list_sessions(self, user_id: str | None, ...) -> SessionListResponse:
    async def delete_session(self, session_id: UUID) -> bool:
    async def expire_session(self, session_id: UUID) -> SessionDetail:
```

会话过期通过 `metadata_.status = "expired"` 标记实现，不修改 SessionModel 结构。

### 会话模型

| 字段 | 类型 | 描述 | ORM 映射 |
|-------|------|------|----------|
| id | UUID | 会话标识符 | `SessionModel.id` |
| user_id | str | 所有者 | `SessionModel.user_id` |
| title | str | 自动生成或用户设置 | `SessionModel.title` |
| intent_type | str | 分类意图 | `SessionModel.intent_type` |
| model_config | dict | 此会话的模型设置 | `SessionModel.model_config` (Schema 用 `model_settings` 避免 Pydantic 冲突) |
| created_at | datetime | 创建时间 | `SessionModel.created_at` |
| updated_at | datetime | 最后活动时间 | `SessionModel.updated_at` |
| metadata | dict | 可扩展元数据 | `SessionModel.metadata_` (列名 `metadata`) |

## 消息管理 — [filled by F09]

### 消息生命周期

实现层：`app/domain/session/service.py` 中的 `SessionService`。

```python
class SessionService:
    async def add_message(self, request: MessageCreateRequest) -> MessageDetail:
    async def get_messages(self, session_id: UUID, ...) -> MessageListResponse:
    async def update_message(self, message_id: UUID, request: MessageUpdateRequest) -> MessageDetail:
```

### 消息模型

| 字段 | 类型 | 描述 | ORM 映射 |
|-------|------|------|----------|
| id | UUID | 消息标识符 | `MessageModel.id` |
| session_id | UUID | 所属会话 | `MessageModel.session_id` |
| role | str | user / assistant / system / tool | `MessageModel.role` |
| content | str | 消息文本 | `MessageModel.content` |
| token_count | int | Token 计数（用于窗口管理） | `MessageModel.token_count` |
| model_name | str | 使用的 LLM 模型 | `MessageModel.model_name` |
| citations | list | RAG 引用参考 | `MessageModel.citations` |
| tool_calls | list | Agent 工具调用 | `MessageModel.tool_calls` |
| tool_results | list | Agent 工具结果 | `MessageModel.tool_results` |
| created_at | datetime | 消息时间戳 | `MessageModel.created_at` |
| metadata | dict | 可扩展元数据 | `MessageModel.metadata_` (列名 `metadata`) |

## 上下文窗口截断 — [filled by F09]

### 策略

当对话历史超过模型的上下文窗口时，上下文管理器必须进行截断，同时保留：

1. **系统提示词** — 始终包含
2. **最近的消息** — 优先保留
3. **较早上下文的摘要** — 通过 LLM 生成（可选，F09 提供文本摘要框架）

### 截断算法 — [filled by F09]

实现层：`app/services/context_manager.py` 中的 `ContextManager.get_context_window()`。

```python
class ContextManager:
    async def get_context_window(
        self,
        session_id: UUID,
        messages: list[MessageDetail],
        max_tokens: int | None = None,
        strategy: str | None = None,
        system_prompt: str | None = None,
    ) -> ContextWindowResult:
```

三种策略：
- `"recent_priority"`：保留最近的消息，丢弃最早的，直到 fit token budget
- `"summary"`：30% budget 保留摘要文本 + 70% 保留最近消息原文；F09 使用文本摘要（无 LLM 调用），LLM 摘要由后续集成
- `"sliding_window"`：保留最近的 N 条消息直到 fit budget（与 recent_priority 行为等价）

### Token 计数 — [filled by F09]

实现：`app/services/context_manager.py` 中 `count_tokens()` 函数。

```python
def count_tokens(text: str, model: str = "cl100k_base") -> int:
    # tiktoken 可用时用 tiktoken，否则近似值 len(text) // 4
```

默认编码 `cl100k_base` 覆盖 GPT-4/4o 家族。

### 上下文窗口结构 — [filled by F09]

```python
class ContextWindowResult(BaseModel):
    session_id: UUID
    system_prompt: str | None
    messages: list[MessageDetail]   # 截断后的消息列表
    total_tokens: int               # 窗口内总 token 数
    truncated: bool                 # 是否发生了截断
    summary: str | None             # 被丢弃消息的摘要（仅 strategy=summary）
```

## Redis 缓存 — [filled by F09]

- 活跃会话上下文缓存在 Redis 中以实现快速检索
- 缓存键：`session_ctx:{session_id}`（HASH 类型）
- TTL：由 `ContextSettings.redis_cache_ttl` 配置（默认：3600 秒 / 1 小时）
- 消息追加时调用 `ContextManager.invalidate_cache()` 使缓存失效
- 缓存未命中时，从 PostgreSQL 重建
- Redis 不可用时静默降级为仅数据库模式（不抛异常，仅 warning 日志）

## 并发 — [filled by F09]

- 消息追加为仅追加操作（无并发写入冲突）
- 上下文窗口读取为只读操作（安全的并发读取）
- Token 计数为 CPU 密集型，`count_tokens` 为同步方法（调用方按需 `asyncio.to_thread`）

## 错误处理 — [filled by F09]

| 场景 | 错误码 | 行为 |
|----------|-----------|----------|
| 会话未找到 | `0005 VALIDATION_ERROR` | 服务层抛 `SystemError(0005)`；HTTP 404 由 F14 API 层处理 |
| 消息未找到 | `0005 VALIDATION_ERROR` | 同上 |
| 截断后仍超出 token 限制 | `0004 TIMEOUT_ERROR` | ContextWindowResult.truncated=True 标记 |
| Redis 不可用 | 降级模式 | 静默降级为仅数据库模式（warning 日志） |

## 配置 — [filled by F09]

```yaml
context:
  redis_cache_ttl: 3600        # Redis 缓存 TTL（秒）
  default_max_tokens: 4096     # 默认上下文窗口最大 token 数
  default_strategy: recent_priority  # 默认截断策略
```

环境变量前缀：`CONTEXT_`（如 `CONTEXT_REDIS_CACHE_TTL=7200`）。