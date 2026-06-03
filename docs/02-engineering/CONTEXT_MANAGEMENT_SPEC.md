# 上下文管理规范

## 概述

上下文管理器（`app/services/context/`）负责会话生命周期、消息持久化和上下文窗口截断。它确保 LLM 调用在 token 限制内接收到正确大小的上下文，同时保持对话连续性。

## 会话管理 — [TBD: filled by F09]

### 会话生命周期

```
Create → Active → (Idle timeout) → Expired
               ↓
            Delete
```

```python
class ContextManager:
    async def create_session(self, user_id: str, metadata: dict = {}) -> Session:
        """Create a new conversation session."""

    async def get_session(self, session_id: UUID) -> Session:
        """Retrieve a session by ID."""

    async def list_sessions(self, user_id: str, pagination: Pagination) -> list[Session]:
        """List sessions for a user."""

    async def delete_session(self, session_id: UUID) -> None:
        """Delete a session and all its messages."""

    async def expire_session(self, session_id: UUID) -> None:
        """Mark session as expired (idle timeout)."""
```

### 会话模型

| 字段 | 类型 | 描述 |
|-------|------|------|
| id | UUID | 会话标识符 |
| user_id | str | 所有者 |
| title | str | 自动生成或用户设置 |
| intent_type | str | 分类意图 |
| model_config | dict | 此会话的模型设置 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 最后活动时间 |
| metadata | dict | 可扩展元数据 |

## 消息管理 — [TBD: filled by F09]

### 消息生命周期

```python
class ContextManager:
    async def add_message(self, session_id: UUID, role: str, content: str, **kwargs) -> Message:
        """Append a message to a session."""

    async def get_messages(self, session_id: UUID, limit: int = 100, offset: int = 0) -> list[Message]:
        """Retrieve messages for a session with pagination."""

    async def update_message(self, message_id: UUID, content: str) -> Message:
        """Update message content (for streaming finalization)."""
```

### 消息模型

| 字段 | 类型 | 描述 |
|-------|------|------|
| id | UUID | 消息标识符 |
| session_id | UUID | 所属会话 |
| role | str | user / assistant / system / tool |
| content | str | 消息文本 |
| token_count | int | Token 计数（用于窗口管理） |
| model_name | str | 使用的 LLM 模型 |
| citations | list | RAG 引用参考 |
| tool_calls | list | Agent 工具调用 |
| tool_results | list | Agent 工具结果 |
| created_at | datetime | 消息时间戳 |

## 上下文窗口截断 — [TBD: filled by F09]

### 策略

当对话历史超过模型的上下文窗口时，上下文管理器必须进行截断，同时保留：

1. **系统提示词** — 始终包含
2. **最近的消息** — 优先保留
3. **较早上下文的摘要** — 通过 LLM 生成（可选）

### 截断算法 — [TBD: filled by F09]

```python
async def get_context_window(
    self,
    session_id: UUID,
    max_tokens: int,
    strategy: str = "recent_priority"
) -> ContextWindow:
    """
    Build a context window within token budget.

    Strategies:
    - "recent_priority": Keep most recent messages, drop oldest
    - "summary": Summarize old messages, keep recent verbatim
    - "sliding_window": Fixed-size window of last N messages
    """
```

### Token 计数 — [TBD: filled by F09]

```python
def count_tokens(text: str, model: str) -> int:
    """Count tokens using model-appropriate tokenizer."""
```

默认：OpenAI 兼容模型使用 `tiktoken`，其他模型使用近似值。

### 上下文窗口结构 — [TBD: filled by F09]

```python
class ContextWindow:
    session_id: UUID
    system_prompt: str
    messages: list[Message]       # Truncated message list
    total_tokens: int              # Total tokens in window
    truncated: bool                # Whether truncation occurred
    summary: str | None            # Summary of dropped messages (if strategy=summary)
```

## Redis 缓存 — [TBD: filled by F09]

- 活跃会话上下文缓存在 Redis 中以实现快速检索
- 缓存键：`session_ctx:{session_id}`
- TTL：按会话可配置（默认：1 小时）
- 消息追加时使缓存失效
- 缓存未命中时，从 PostgreSQL 重建

## 并发 — [TBD: filled by F09]

- 消息追加为仅追加操作（无并发写入冲突）
- 上下文窗口读取为只读操作（安全的并发读取）
- Token 计数为 CPU 密集型，在线程池中运行

## 错误处理 — [TBD: filled by F09]

| 场景 | 错误码 | 行为 |
|----------|-----------|----------|
| 会话未找到 | `0005 VALIDATION_ERROR` | 返回 404 |
| 截断后仍超出 token 限制 | `0004 TIMEOUT_ERROR` | 以更小窗口重试 |
| Redis 不可用 | `0003 SERVICE_UNAVAILABLE` | 降级为仅数据库模式 |

[TBD: filled by work order F09]