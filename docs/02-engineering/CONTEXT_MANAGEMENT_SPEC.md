# Context Management Specification

## Overview

The Context Manager (`app/services/context/`) handles session lifecycle, message persistence, and context window truncation. It ensures that LLM calls receive correctly sized context within token limits while preserving conversation continuity.

## Session Management — [TBD: filled by F09]

### Session Lifecycle

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

### Session Model

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Session identifier |
| user_id | str | Owner |
| title | str | Auto-generated or user-set |
| intent_type | str | Classified intent |
| model_config | dict | Model settings for this session |
| created_at | datetime | Creation time |
| updated_at | datetime | Last activity time |
| metadata | dict | Extensible metadata |

## Message Management — [TBD: filled by F09]

### Message Lifecycle

```python
class ContextManager:
    async def add_message(self, session_id: UUID, role: str, content: str, **kwargs) -> Message:
        """Append a message to a session."""

    async def get_messages(self, session_id: UUID, limit: int = 100, offset: int = 0) -> list[Message]:
        """Retrieve messages for a session with pagination."""

    async def update_message(self, message_id: UUID, content: str) -> Message:
        """Update message content (for streaming finalization)."""
```

### Message Model

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Message identifier |
| session_id | UUID | Parent session |
| role | str | user / assistant / system / tool |
| content | str | Message text |
| token_count | int | Token count (for window management) |
| model_name | str | LLM model used |
| citations | list | RAG citation references |
| tool_calls | list | Agent tool calls |
| tool_results | list | Agent tool results |
| created_at | datetime | Message timestamp |

## Context Window Truncation — [TBD: filled by F09]

### Strategy

When conversation history exceeds the model's context window, the Context Manager must truncate while preserving:

1. **System prompt** — always included
2. **Most recent messages** — prioritized
3. **Summary of earlier context** — generated via LLM (optional)

### Truncation Algorithm — [TBD: filled by F09]

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

### Token Counting — [TBD: filled by F09]

```python
def count_tokens(text: str, model: str) -> int:
    """Count tokens using model-appropriate tokenizer."""
```

Default: use `tiktoken` for OpenAI-compatible models, approximation for others.

### Context Window Structure — [TBD: filled by F09]

```python
class ContextWindow:
    session_id: UUID
    system_prompt: str
    messages: list[Message]       # Truncated message list
    total_tokens: int              # Total tokens in window
    truncated: bool                # Whether truncation occurred
    summary: str | None            # Summary of dropped messages (if strategy=summary)
```

## Redis Caching — [TBD: filled by F09]

- Active session context cached in Redis for fast retrieval
- Cache key: `session_ctx:{session_id}`
- TTL: configurable per session (default: 1 hour)
- Cache invalidated on message append
- On cache miss, rebuild from PostgreSQL

## Concurrency — [TBD: filled by F09]

- Message append is append-only (no concurrent write conflicts)
- Context window reads are read-only (safe concurrent reads)
- Token counting is CPU-bound and runs in thread pool

## Error Handling — [TBD: filled by F09]

| Scenario | Error Code | Behavior |
|----------|-----------|----------|
| Session not found | `0005 VALIDATION_ERROR` | Return 404 |
| Token limit exceeded despite truncation | `0004 TIMEOUT_ERROR` | Retry with smaller window |
| Redis unavailable | `0003 SERVICE_UNAVAILABLE` | Fall back to DB-only |

[TBD: filled by work order F09]