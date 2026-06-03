# Chat Workflow Specification

## Overview

The Chat workflow (`app/domain/chat/`) manages conversation sessions, message persistence, context window assembly, LLM interaction, and SSE streaming responses. It is the core user-facing interaction pattern.

## Chat Request Flow — [TBD: filled by F14]

```
POST /api/v1/chat (SSE)
    ↓
API Layer (api/chat.py)
    ↓
ChatService (domain/chat/service.py)
    ↓
┌──────────────────────────────────┐
│ 1. Resolve or create session      │
│ 2. Persist user message           │
│ 3. Build context window           │
│ 4. Call LLM Gateway (stream)     │
│ 5. Stream SSE events             │
│ 6. Persist assistant message      │
│ 7. Update session metadata        │
└──────────────────────────────────┘
    ↓
SSE Event Stream to Client
```

## SSE Event Protocol — [TBD: filled by F06, F14]

The chat endpoint returns an SSE stream with the following events:

```
event: start
data: {"session_id": "uuid", "message_id": "uuid"}

event: chunk
data: {"content": "partial text", "message_id": "uuid"}

event: citation
data: {"sources": [{"doc_id": "...", "heading": "...", "score": 0.95}], "message_id": "uuid"}

event: heartbeat
data: {"ts": "2024-01-01T00:00:00Z"}

event: done
data: {"message_id": "uuid", "reason": "complete", "input_tokens": 50, "output_tokens": 120}

event: error
data: {"code": 1001, "message": "Unauthorized"}
```

### Event Lifecycle

1. `start` — Sent immediately, includes session and message IDs
2. `chunk` — Sent for each LLM streaming token group
3. `citation` — Sent if RAG sources are available (optional)
4. `heartbeat` — Sent every N seconds to prevent timeout (configurable, default 15s)
5. `done` — Sent when LLM generation is complete, includes token stats
6. `error` — Sent if any error occurs, then stream closes

## Session Lifecycle — [TBD: filled by F09, F14]

Sessions are auto-created on first chat request. Caller generates `session_id` (UUID); if it doesn't exist, a new session is created automatically.

### Auto-Create Session

When a chat request arrives with a `session_id` that doesn't exist:

1. Create new session with `user_id`, `session_id`, `title` (optional), `model_config` (optional)
2. First-time fields only take effect on creation
3. Subsequent requests with the same `session_id` reuse the session

### Get Session

```python
GET /api/v1/chat/sessions/{session_id}
→ { "session_id": "uuid", "title": "...", "message_count": 5, "created_at": "...", "updated_at": "..." }
```

### Delete Session

```python
DELETE /api/v1/chat/sessions/{session_id}
→ { "code": 0, "message": "ok" }
```

## Message Persistence — [TBD: filled by F09, F14]

### Add User Message

When a chat request arrives:

1. If `session_id` provided: validate session exists
2. If no `session_id`: create new session
3. Persist user message via `ContextManager.add_message()`
4. Count tokens and store in `token_count` field

### Add Assistant Message

After LLM generation completes:

1. Persist full assistant response via `ContextManager.add_message()`
2. Store `input_tokens` and `output_tokens`
3. Store `citations` if RAG was used
4. Update `session.updated_at`

## Context Window Assembly — [TBD: filled by F09, F14]

Before calling the LLM, the chat service assembles the context:

1. Load system prompt from `prompts/chat/system.md`
2. Retrieve conversation history via `ContextManager.get_context_window()`
3. Apply truncation strategy (default: `recent_priority`)
4. Merge: system prompt + truncated history + user message
5. Ensure total tokens ≤ model context limit

### Context Window Parameters — [TBD: filled by F14]

```python
class ChatContextConfig:
    max_context_tokens: int = 4096    # Total context window
    system_prompt_tokens: int = 500   # Budget for system prompt
    truncation_strategy: str = "recent_priority"
    include_citations: bool = True
```

## LLM Call — [TBD: filled by F04, F14]

- Uses `LLMGateway.generate_stream()` for SSE responses
- Task type: `"chat"`
- Model: from session config or default
- Concurrency: governed by LLM semaphore
- Timeout: configurable per chat request

## Streaming Service — [TBD: filled by F06, F14]

The SSE stream is managed by `services/sse_stream/`:

```python
class SSEStreamService:
    async def create_stream(
        self,
        session_id: UUID,
        llm_stream: AsyncIterator[LLMChunk]
    ) -> EventSourceResponse:
        """
        1. Send 'start' event
        2. Iterate LLM stream, send 'chunk' events
        3. Send 'citation' events if available
        4. Send 'heartbeat' events periodically
        5. Send 'done' event with token stats
        6. Handle disconnect detection
        7. On error: send 'error' event and close
        """
```

### Disconnect Detection — [TBD: filled by F06]

- Client disconnect is detected via asyncio event
- On disconnect: cancel LLM stream, send log event
- No orphan LLM calls allowed

## API Endpoints — [TBD: filled by F14]

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| POST | /api/v1/chat | Chat completion (auto-create session, SSE or sync) | EventSourceResponse / JSON |
| GET | /api/v1/chat/sessions/{id} | Get session | JSON |
| GET | /api/v1/chat/sessions/{id}/messages | List messages | JSON |
| DELETE | /api/v1/chat/sessions/{id} | Delete session (soft delete, cascade) | JSON |

## Error Codes — [TBD: filled by F14]

Uses system error codes from `docs/01-architecture/ERROR_CODE.md`:

- `0004 TIMEOUT_ERROR` — LLM timeout
- `0003 SERVICE_UNAVAILABLE` — LLM unavailable
- `0005 VALIDATION_ERROR` — Invalid request
- `1001 AUTH_INVALID_KEY` — Missing/invalid API key

[TBD: filled by work orders F04, F06, F09, F14]