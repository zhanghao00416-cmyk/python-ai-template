# API Contract

## Overview

This document defines the API contract for the Python AI Template platform. All endpoints follow REST conventions with structured JSON responses and SSE for streaming.

## Base URL

```
/api/v1
```

## Common Response Envelope

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "uuid",
  "trace_id": "uuid",
  "data": { }
}
```

Error response:

```json
{
  "code": 1001,
  "message": "Unauthorized: invalid API key",
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

## Endpoint Registry

### Health — [filled by F01, enhanced]

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/health | Health check with dependency details |

#### GET /api/v1/health

**Response**:

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "uuid",
  "trace_id": "uuid",
  "data": {
    "status": "ok | degraded | error",
    "version": "0.1.0",
    "uptime": 0.0,
    "dependencies": {
      "database": {
        "status": "ok | degraded | error",
        "latency_ms": 3
      },
      "redis": {
        "status": "ok | degraded | error",
        "latency_ms": 1
      },
      "qdrant": {
        "status": "ok | degraded | error",
        "latency_ms": 5
      },
      "llm": {
        "status": "ok | degraded | error",
        "channels": {
          "qwen_cloud": {
            "status": "ok | open | half_open",
            "latency_ms": 200
          },
          "vllm": {
            "status": "ok | open | half_open",
            "latency_ms": null
          }
        }
      }
    }
  }
}
```

| Field | Description |
|-------|-------------|
| status | Overall: `ok` (all healthy), `degraded` (partial), `error` (critical failure) |
| dependencies.*.status | `ok` = normal, `degraded` = slow but usable, `error` = unavailable |
| dependencies.llm.channels.*.status | `ok` = normal, `open` = circuit breaker tripped, `half_open` = probing recovery |
| dependencies.*.latency_ms | Response latency in milliseconds; `null` = not checked or unavailable |

---

### Orchestrated — [TBD: filled by F14+]

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/run | Unified orchestrated entry point (SSE) |

#### POST /api/v1/run — Unified Entry Point (SSE)

The primary entry point for conversational AI. The server orchestrates: intent classification → workflow selection → multi-agent execution → tool calls → SSE streaming response.

**Request body**:

```json
{
  "user_id": "string (required)",
  "session_id": "string (required, auto-created if not exists)",
  "query": "string (required, non-empty)",
  "stream": true,
  "intent": "string?",
  "model_override": "string?",
  "temperature": 0.7?,
  "max_tokens": 4096?,
  "metadata": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | yes | User identifier |
| session_id | string | yes | Session identifier; auto-created if not exists |
| query | string | yes | User input |
| stream | boolean | no | Default true; false returns sync JSON response |
| intent | string | no | Skip intent classification if caller already knows; e.g. "qa", "chat" |
| model_override | string | no | Override default model for this request |
| temperature | float | no | Generation randomness (0.0–1.0) |
| max_tokens | int | no | Max generation length |
| metadata | object | no | Extensible business metadata (channel, version, etc.) |

**Response (SSE)**:

```
start → [intent]? → [route]? → [agent]* → [tool]* → [citation]* → [heartbeat]* → chunk* → [usage]? → done
                                                                                    ↘ error (anytime)
```

**Response (sync, stream=false)**:

```json
{
  "code": 0,
  "data": {
    "intent": "qa",
    "content": "full response text",
    "citations": [],
    "usage": {
      "input_tokens": 150,
      "output_tokens": 300,
      "model": "qwen-plus"
    }
  }
}
```

Orchestration-specific SSE events (in addition to standard events):

| Event | Data Fields | Description |
|-------|-------------|-------------|
| `intent` | `intent`, `confidence`, `layer_used` | Intent classification result |
| `route` | `workflow_id`, `intent` | Selected workflow |
| `agent` | `agent_name`, `step_id` | Agent step begins |
| `tool` | `tool_name`, `step_id` | Tool call (start/result) |

**Intent classification for `/run`**: Uses a simplified 4-type model (extensible by business):

| Intent | Description |
|--------|-------------|
| `qa` | Knowledge Q&A (default RAG workflow) |
| `task` | Multi-step task requiring tools |
| `chat` | Free conversation, no retrieval |
| `retrieve_only` | Pure retrieval, no generation |

**Integration model**:

| Mode | Usage |
|------|-------|
| Conversational | Only `POST /run` |
| Self-orchestrated | `POST /intent` → call individual capability APIs |
| Mixed | Upload knowledge via `/kb/collections`; chat via `/run` |

#### API 选型决策表（禁止混用职责）

| 场景 | 推荐入口 | 不要用 | 原因 |
|------|----------|--------|------|
| 产品级对话：自动意图 + 选工作流 + Agent/工具 + 一条 SSE 流 | `POST /api/v1/run` | 在 `/chat` 里复制编排逻辑 | `/run` 是唯一编排入口 |
| 已知「只要聊天」：会话管理 + 上下文截取 + 流式回复 | `POST /api/v1/chat` | `/run` | 跳过意图漏斗，域边界清晰 |
| 已知「只要 RAG」：指定集合/策略/rerank，可不要会话编排 | `POST /api/v1/kb/query` | `/run` 或 `/chat` | 检索参数多，独立契约 |
| 上传/管理知识库文档与集合 | `POST/GET/DELETE /api/v1/kb/*` | `/run` | 长任务异步（`task_id`），与对话解耦 |
| 调用方自建流水线：先分类再调能力 API | `POST /api/v1/intent` → `/chat` / `/kb/query` / Agent API | 仅 `/run` | 中台自编排 |
| 查会话历史、删会话 | `GET/DELETE /api/v1/chat/sessions/*` | `/run` | CRUD 资源模型 |
| 健康检查、依赖与熔断状态 | `GET /api/v1/health` | 业务 API | 运维探针 |

**反模式（实现阶段 3 必查）**：

- 在 `domain/chat` 内调用完整 Orchestrator（应只在 `/run` 域编排）。
- 在 `domain/knowledge` 的 query 路径里默认跑四层 intent（应仅在 `/run` 或显式 `/intent`）。
- 同一请求既走 `/run` 又内部再调 `/chat` HTTP（应复用 service 层，禁止 api 互调）。

---

### Chat — [TBD: filled by F14]

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/chat | Chat completion (auto-create session, SSE or sync) |
| GET | /api/v1/chat/sessions/{session_id} | Get session details |
| GET | /api/v1/chat/sessions/{session_id}/messages | List session messages |
| DELETE | /api/v1/chat/sessions/{session_id} | Delete session (soft delete, cascade messages) |

#### POST /api/v1/chat

Session auto-creation: if `session_id` does not exist, a new session is created automatically. First-time fields (`title`, `model_config`) only take effect on creation.

**Request body**:

```json
{
  "user_id": "string (required)",
  "session_id": "string (required, auto-created if not exists)",
  "query": "string (required, non-empty)",
  "stream": true?,
  "model_override": "string?",
  "temperature": 0.7?,
  "max_tokens": 4096?,
  "title": "string? (first-time creation only)",
  "model_config": "object? (first-time creation only)",
  "metadata": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | yes | User identifier |
| session_id | string | yes | Caller-generated UUID; auto-created if not exists |
| query | string | yes | User message |
| stream | boolean | no | Default true; false returns sync JSON |
| model_override | string | no | Override default chat model |
| temperature | float | no | Generation randomness (0.0–1.0) |
| max_tokens | int | no | Max generation length |
| title | string | no | Session title; only used when session is first created |
| model_config | object | no | Model config override; only used when session is first created |
| metadata | object | no | Extensible business metadata |

**Response (SSE)**:

```
start → [heartbeat]* → chunk* → [citation]? → [usage]? → done
                                              ↘ error (anytime)
```

**Response (sync, stream=false)**:

```json
{
  "code": 0,
  "data": {
    "content": "full response text",
    "citations": [],
    "usage": {
      "input_tokens": 150,
      "output_tokens": 300,
      "model": "qwen-plus"
    }
  }
}
```

#### GET /api/v1/chat/sessions/{session_id}

**Response**:

```json
{
  "code": 0,
  "data": {
    "id": "uuid",
    "user_id": "string",
    "title": "string",
    "intent_type": "string?",
    "model_config": {},
    "created_at": "ISO8601",
    "updated_at": "ISO8601",
    "metadata": {}
  }
}
```

#### GET /api/v1/chat/sessions/{session_id}/messages

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| limit | int | 20 | Messages per page |
| offset | int | 0 | Pagination offset |
| role | string | null | Filter by role: user / assistant / system / tool |
| before | ISO8601 | null | Messages before this timestamp (cursor-style) |

**Response**:

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "uuid",
        "session_id": "uuid",
        "role": "user | assistant | system | tool",
        "content": "string",
        "token_count": 42,
        "model_name": "qwen-plus",
        "citations": [],
        "tool_calls": null,
        "tool_results": null,
        "created_at": "ISO8601",
        "metadata": {}
      }
    ],
    "total": 100,
    "offset": 0,
    "limit": 20
  }
}
```

#### DELETE /api/v1/chat/sessions/{session_id}

Soft delete: marks session as deleted, cascades to all messages (also soft-deleted).

**Response**:

```json
{
  "code": 0,
  "data": {
    "deleted_session_id": "uuid",
    "deleted_messages_count": 15
  }
}
```

---

### Knowledge Base — [TBD: filled by F15a/F15b]

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/kb/collections | Create a collection |
| GET | /api/v1/kb/collections | List collections |
| DELETE | /api/v1/kb/collections/{collection_name} | Delete a collection |
| POST | /api/v1/kb/collections/{collection_name}/documents | Upload document (async) |
| GET | /api/v1/kb/collections/{collection_name}/documents | List/search documents |
| DELETE | /api/v1/kb/collections/{collection_name}/documents | Delete documents (batch/clear) |
| POST | /api/v1/kb/query | RAG query with configurable retrieval |

#### POST /api/v1/kb/collections

**Request body**:

```json
{
  "name": "string (required)",
  "description": "string?",
  "vector_size": 1024?,
  "metadata": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Collection name (unique) |
| description | string | no | Collection description |
| vector_size | int | no | Vector dimension; default from config |
| metadata | object | no | Extensible collection metadata |

**Response**:

```json
{
  "code": 0,
  "data": {
    "name": "ai_knowledge",
    "vector_size": 1024,
    "status": "created",
    "document_count": 0
  }
}
```

#### GET /api/v1/kb/collections

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| limit | int | 20 | Collections per page |
| offset | int | 0 | Pagination offset |
| name | string | null | Fuzzy search by name |

**Response**:

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "name": "ai_knowledge",
        "description": "...",
        "vector_size": 1024,
        "document_count": 42,
        "status": "active",
        "created_at": "ISO8601"
      }
    ],
    "total": 5,
    "offset": 0,
    "limit": 20
  }
}
```

#### DELETE /api/v1/kb/collections/{collection_name}

**Response** (includes impact scope):

```json
{
  "code": 0,
  "data": {
    "deleted_collection": "ai_knowledge",
    "deleted_documents_count": 42,
    "deleted_vectors_count": 256
  }
}
```

#### POST /api/v1/kb/collections/{collection_name}/documents

Upload a markdown document with chunking strategy and metadata. Processing is async — returns a task_id.

**Request** (multipart/form-data):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | File | yes | Markdown file (.md) |
| doc_type | string | no | Metadata: document type (e.g. 技术文档/手册/FAQ) |
| source | string | no | Metadata: origin (e.g. 内部/外部/爬取) |
| tag | string | no | Metadata: tag (e.g. 重要/已审核/草稿) |
| uploader | string | yes | Uploader identifier |
| chunking_strategy | string | no | Chunking strategy, default from config |
| chunking_params | object | no | Strategy-specific parameters |
| enable_parent_child | boolean | no | Enable parent-child chunking mode; default false |
| parent_chunk_params | object | no | Parent chunk config (only when enable_parent_child=true) |

**Chunking strategies**:

| Strategy | Key | Parameters |
|----------|-----|------------|
| Fixed + overlap | `fixed_overlap` | `chunk_size` (default 500), `overlap` (default 50) |
| Delimiter + max length | `delimiter_max` | `delimiters` (default ["\n\n", "\n"]), `max_chunk_size` (default 1000) |
| Semantic | `semantic` | `similarity_threshold` (default 0.85) |
| Paragraph | `paragraph` | `min_paragraph_chars` (default 50) |

**Parent-child chunking mode**:

When `enable_parent_child=true`, the document is chunked at two granularities:

1. **Parent chunks**: Large-granularity chunks for context (always uses `fixed_overlap` strategy with `parent_chunk_params`)
2. **Child chunks**: Fine-granularity chunks for precise matching (uses the selected `chunking_strategy`)

Each child chunk stores a `parent_id` linking to its parent. During retrieval, matching a child chunk automatically returns the parent chunk for full context.

```json
{
  "enable_parent_child": true,
  "chunking_strategy": "fixed_overlap",
  "chunking_params": { "chunk_size": 500, "overlap": 50 },
  "parent_chunk_params": { "chunk_size": 2000, "overlap": 200 }
}
```

| Parameter | Description |
|-----------|-------------|
| `parent_chunk_params.chunk_size` | Parent chunk size (default 2000) |
| `parent_chunk_params.overlap` | Parent chunk overlap (default 200) |

**Response**:

```json
{
  "code": 0,
  "data": {
    "task_id": "uuid",
    "status": "pending",
    "document_id": "uuid",
    "message": "Document uploaded, processing started"
  }
}
```

Deduplication: if a file with the same name + uploader + collection already exists, return HTTP 409 with existing document_id.

#### GET /api/v1/kb/collections/{collection_name}/documents

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| limit | int | 20 | Documents per page |
| offset | int | 0 | Pagination offset |
| filename | string | null | Fuzzy search by filename |
| doc_type | string | null | Filter by doc_type metadata |
| source | string | null | Filter by source metadata |
| tag | string | null | Filter by tag metadata |
| uploader | string | null | Filter by uploader |

**Response**:

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "uuid",
        "filename": "guide.md",
        "doc_type": "技术文档",
        "source": "内部",
        "tag": "已审核",
        "uploader": "user1",
        "chunk_count": 12,
        "parent_child_enabled": true,
        "status": "indexed | pending | error",
        "created_at": "ISO8601"
      }
    ],
    "total": 42,
    "offset": 0,
    "limit": 20
  }
}
```

#### DELETE /api/v1/kb/collections/{collection_name}/documents

Supports targeted deletion and one-click clear-all with two-step confirmation.

**Query parameters**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| doc_id | string | no | Delete specific document by ID |
| doc_type | string | no | Filter: delete all matching doc_type |
| source | string | no | Filter: delete all matching source |
| tag | string | no | Filter: delete all matching tag |
| uploader | string | no | Filter: delete all matching uploader |
| filename | string | no | Filter: delete matching filename (fuzzy) |
| clear_all | boolean | no | Clear all documents in the collection |
| confirm_token | string | no | Confirmation token from pre-check response |

**Two-step confirmation flow**:

1. **Without `confirm_token`**: Returns impact scope + a `confirm_token` (valid 60s). No deletion performed.

```json
{
  "code": 0,
  "data": {
    "affected_documents_count": 42,
    "affected_chunks_count": 256,
    "confirm_token": "uuid",
    "message": "Confirm deletion by resending with confirm_token"
  }
}
```

2. **With `confirm_token`**: Executes deletion.

```json
{
  "code": 0,
  "data": {
    "deleted_documents_count": 42,
    "deleted_chunks_count": 256
  }
}
```

#### POST /api/v1/kb/query

RAG retrieval and generation with configurable strategies.

**Request body**:

```json
{
  "user_id": "string (required)",
  "session_id": "string?",
  "query": "string (required)",
  "collection_names": ["string"]?,
  "doc_type": "string?",
  "source": "string?",
  "tag": "string?",
  "uploader": "string?",
  "retrieval_strategy": "hybrid"?,
  "top_k": 5?,
  "score_threshold": 0.5?,
  "enable_rerank": false?,
  "stream": true?,
  "model_override": "string?",
  "temperature": 0.7?,
  "max_tokens": 4096?
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | yes | User identifier |
| session_id | string | no | Session for context |
| query | string | yes | Search query |
| collection_names | string[] | no | Target collections; default all |
| doc_type | string | no | Filter by doc_type metadata |
| source | string | no | Filter by source metadata |
| tag | string | no | Filter by tag metadata |
| uploader | string | no | Filter by uploader |
| retrieval_strategy | string | no | See below; default `hybrid` |
| top_k | int | no | Number of results; default 5 |
| score_threshold | float | no | Minimum similarity score; default 0.5 |
| enable_rerank | boolean | no | Enable reranking; default false |
| stream | boolean | no | SSE or sync; default true |
| model_override | string | no | Override generation model |
| temperature | float | no | Generation randomness |
| max_tokens | int | no | Max generation length |

**Retrieval strategies**:

| Strategy | Key | Description |
|----------|-----|-------------|
| Keyword | `keyword` | Sparse vector / full-text search |
| Similarity | `similarity` | Dense vector search |
| Hybrid | `hybrid` | Combine keyword + similarity (default) |
| RRF | `rrf` | Reciprocal Rank Fusion |

**Response (SSE)**:

```
start → [heartbeat]* → [citation]? → chunk* → [usage]? → done
                                              ↘ error (anytime)
```

**Response (sync, stream=false)**:

```json
{
  "code": 0,
  "data": {
    "content": "generated answer",
    "citations": [
      {
        "filename": "guide.md",
        "chunk_text": "...",
        "score": 0.92
      }
    ],
    "retrieval_results": [
      {
        "chunk_text": "...",
        "score": 0.92,
        "chunk_index": 3,
        "parent_chunk_text": "...",
        "parent_chunk_index": 1,
        "metadata": { "doc_type": "技术文档", "source": "内部" }
      }
    ],
    "usage": {
      "input_tokens": 150,
      "output_tokens": 300,
      "model": "qwen-plus"
    }
  }
}
```

---

### Intent — [TBD: filled by F16]

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/intent | Classify user intent (three-layer + multi-intent) |

#### POST /api/v1/intent

Three-layer classification pipeline: keyword → similarity → LLM. Each earlier layer can short-circuit. Supports multi-intent detection with query reconstruction.

**Request body**:

```json
{
  "user_id": "string (required)",
  "session_id": "string (required)",
  "query": "string (required, non-empty)",
  "candidates": ["qa", "task", "chat", "retrieve_only"]?,
  "options": {
    "keyword_enabled": true?,
    "similarity_enabled": true?,
    "multi_intent_enabled": true?
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | yes | User identifier |
| session_id | string | yes | Session identifier |
| query | string | yes | User input |
| candidates | string[] | no | Limit classification scope; default all configured intents |
| options.keyword_enabled | boolean | no | Enable L1 keyword matching; default true |
| options.similarity_enabled | boolean | no | Enable L2 similarity matching; default true |
| options.multi_intent_enabled | boolean | no | Enable multi-intent detection; default true |

**Three-layer pipeline**:

```
L1: Keyword matching (fastest, zero LLM cost)
    ↓ not matched or low confidence
L2: Similarity matching (embedding-based, low cost)
    ↓ not matched or low confidence
L3: LLM classification (most accurate, highest cost)
```

**Intent configuration** (in `configs/default.yaml`):

```yaml
intent:
  layers:
    keyword:
      enabled: true
      rules:
        - intent: qa
          keywords: ["什么是", "怎么用", "如何", "解释"]
        - intent: task
          keywords: ["帮我", "执行", "创建", "删除"]
        - intent: chat
          keywords: ["你好", "闲聊", "聊聊"]
        - intent: retrieve_only
          keywords: ["搜索", "查找", "检索"]
      confidence_threshold: 0.9
    similarity:
      enabled: true
      top_k: 3
      score_threshold: 0.85
    llm:
      enabled: true
      model_routing: intent
  multi_intent:
    enabled: true
    max_intents: 3
```

**Default intent types** (extensible by business via prompt):

| Intent | Description |
|--------|-------------|
| `qa` | Knowledge Q&A |
| `task` | Multi-step task requiring tools |
| `chat` | Free conversation |
| `retrieve_only` | Pure retrieval, no generation |

**Response**:

```json
{
  "code": 0,
  "data": {
    "intent": "task",
    "confidence": 0.95,
    "query": "帮我创建一个知识库",
    "layer_used": "keyword",
    "routing": {
      "workflow_id": "task_workflow",
      "model": "qwen-plus"
    },
    "sub_intents": [
      {
        "intent": "qa",
        "confidence": 0.88,
        "query": "解释下 RAG 是什么",
        "original_query": "顺便解释下 RAG 是什么"
      }
    ]
  }
}
```

| Field | Description |
|-------|-------------|
| intent | Primary intent (highest confidence); this is the one to execute |
| confidence | Primary intent confidence (0.0–1.0) |
| query | Reconstructed full query for primary intent (resolves subject omission) |
| layer_used | Which layer resolved: `keyword` / `similarity` / `llm` |
| routing | Recommended routing for primary intent |
| sub_intents | Additional intents (not executed, returned for caller orchestration) |
| sub_intents[].query | Reconstructed full query (resolves subject omission) |
| sub_intents[].original_query | Original text fragment |

---

### Prompt Admin — [TBD: filled by F17]

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/prompts` | Query prompt templates (list + detail with filters) |
| PUT | `/api/v1/prompts/{name}` | Modify prompt (auto version increment + rollback) |
| GET | `/api/v1/prompts/{name}/versions` | Prompt version history |
| POST | `/api/v1/prompts/{name}/reset` | Reset to baseline version |

#### GET /api/v1/prompts

Query templates with pagination and filters. When `name` filter matches a single result, returns full detail (including content).

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| limit | int | 20 | Templates per page |
| offset | int | 0 | Pagination offset |
| directory | string | null | Filter by directory (e.g. "agents", "skills") |
| name | string | null | Fuzzy search by template name; exact match returns detail |

**Response (list)**:

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "name": "rag_answer",
        "directory": "skills",
        "description": "RAG answer generation prompt",
        "variables": ["query", "context", "language"],
        "version": 3,
        "updated_at": "ISO8601"
      }
    ],
    "total": 12,
    "offset": 0,
    "limit": 20
  }
}
```

**Response (single, exact name match)**:

```json
{
  "code": 0,
  "data": {
    "name": "rag_answer",
    "directory": "skills",
    "description": "RAG answer generation prompt",
    "content": "You are a helpful assistant...\n\nContext: {context}\n\nQuery: {query}",
    "variables": ["query", "context", "language"],
    "version": 3,
    "baseline_content": "original content from prompts/ directory",
    "created_at": "ISO8601",
    "updated_at": "ISO8601"
  }
}
```

#### PUT /api/v1/prompts/{name}

Modify prompt content or rollback to a specific version. `content` and `rollback_version` are mutually exclusive.

**Request body**:

```json
{
  "content": "string?",
  "description": "string?",
  "rollback_version": 3?
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| content | string | no* | New prompt content; auto-extract variables |
| description | string | no | Updated description |
| rollback_version | int | no* | Rollback to specific version; mutually exclusive with content |

*At least one of `content` or `rollback_version` must be provided.

Version history: each update or rollback increments `version`. All previous versions are retained in `prompt_templates` table.

**Response**:

```json
{
  "code": 0,
  "data": {
    "name": "rag_answer",
    "version": 4,
    "previous_version": 3,
    "updated_at": "ISO8601"
  }
}
```

#### GET /api/v1/prompts/{name}/versions

List all historical versions of a prompt template.

**Response**:

```json
{
  "code": 0,
  "data": {
    "name": "rag_answer",
    "current_version": 5,
    "baseline_version": 1,
    "versions": [
      { "version": 5, "content_preview": "first 100 chars...", "updated_by": "system", "updated_at": "ISO8601" },
      { "version": 4, "content_preview": "first 100 chars...", "updated_by": "user1", "updated_at": "ISO8601" },
      { "version": 3, "content_preview": "first 100 chars...", "updated_by": "user1", "updated_at": "ISO8601" }
    ]
  }
}
```

#### POST /api/v1/prompts/{name}/reset

Reset prompt to baseline content from `prompts/` directory. Baseline files are the source of truth loaded at startup.

**Response**:

```json
{
  "code": 0,
  "data": {
    "name": "rag_answer",
    "version": 6,
    "reset_from_version": 5,
    "baseline_source": "prompts/skills/rag_answer.md",
    "updated_at": "ISO8601"
  }
}
```

---

### Agent — [TBD: filled by F11, F12]

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/agent/run` | Execute agent task (SSE) |
| GET | `/api/v1/agent/trajectories` | List trajectories by session |
| GET | `/api/v1/agent/trajectories/{task_id}` | Get trajectory detail |

#### POST /api/v1/agent/run

Execute an agent task with specified engine type, tools and skills. Supports react (dynamic), workflow (pre-defined DAG), and orchestrator (multi-agent) modes.

**Request body**:

```json
{
  "user_id": "string (required)",
  "session_id": "string (required)",
  "query": "string (required, non-empty)",
  "agent_type": "react?",
  "agent_name": "string?",
  "tools": ["string"]?,
  "skills": ["string"]?,
  "max_steps": 10?,
  "stream": true?,
  "model_override": "string?",
  "metadata": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | yes | User identifier |
| session_id | string | yes | Session identifier |
| query | string | yes | Task description / user input |
| agent_type | string | no | Engine type: `react` (default) / `workflow` / `orchestrator` |
| agent_name | string | no | Role name from `configs/agents.yaml`; loads prompt, default tools/skills, model |
| tools | string[] | no | Override allowed tools; default from agent config or all available |
| skills | string[] | no | Override allowed skills; skill-used tools are masked from direct tool access |
| max_steps | int | no | Max execution steps; default 10, prevents infinite loops |
| stream | boolean | no | Default true; false returns sync JSON |
| model_override | string | no | Override model for this run |
| metadata | object | no | Extensible business metadata |

**Tool / Skill / MCP hierarchy**:

| Type | Description | Source |
|------|-------------|--------|
| Tool | Atomic operation | Built-in + MCP registered (MCP is transparent to caller) |
| Skill | Multi-step orchestration (prompt + steps + tools) | `skills/` directory definitions |

Priority: `request override` > `agent config` > `all available`

Mutual exclusion: if a skill uses a tool (e.g. `rag_answer` uses `kb_search`), that tool is masked from the agent's direct tool list to prevent conflict.

**Agent configuration** (`configs/agents.yaml`):

```yaml
agents:
  researcher:
    system_prompt: "prompts/agents/researcher.md"
    tools: ["kb_search", "code_execute"]
    skills: ["rag_answer"]
    model_routing: "chat"
    max_steps: 8
```

**Tool registration** (`configs/default.yaml`):

```yaml
tools:
  builtin:
    - kb_search
    - code_execute
    - http_request
  mcp:
    - name: web_search
      url: "http://localhost:8080/mcp"
      timeout: 30
```

**Response (SSE)**:

```
start → [agent]* → [tool]* → [heartbeat]* → chunk* → [citation]? → [usage]? → done
                                                                        ↘ error (anytime)
```

SSE events specific to Agent:

| Event | Data Fields | Description |
|-------|-------------|-------------|
| `agent` | `agent_name`, `step_id`, `state` | Agent state change (IDLE/THINKING/ACTING/OBSERVING/DONE) |
| `tool` | `tool_name`, `step_id`, `status` | Tool call start/result |

**Response (sync, stream=false)**:

```json
{
  "code": 0,
  "data": {
    "task_id": "uuid",
    "content": "full response text",
    "citations": [],
    "trajectory": [
      { "step": 1, "state": "THINKING", "thought": "..." },
      { "step": 2, "state": "ACTING", "tool": "kb_search", "input": {} },
      { "step": 3, "state": "OBSERVING", "observation": "..." }
    ],
    "usage": {
      "input_tokens": 150,
      "output_tokens": 300,
      "model": "qwen-plus"
    }
  }
}
```

#### GET /api/v1/agent/trajectories

List agent execution trajectories, filtered by session.

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| session_id | string | null | Filter by session ID |
| agent_name | string | null | Filter by agent name |
| limit | int | 20 | Results per page |
| offset | int | 0 | Pagination offset |

**Response**:

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "task_id": "uuid",
        "session_id": "uuid",
        "agent_name": "researcher",
        "agent_type": "react",
        "step_count": 5,
        "status": "completed",
        "created_at": "ISO8601"
      }
    ],
    "total": 10,
    "offset": 0,
    "limit": 20
  }
}
```

#### GET /api/v1/agent/trajectories/{task_id}

Get detailed trajectory for a single agent execution.

**Response**:

```json
{
  "code": 0,
  "data": {
    "task_id": "uuid",
    "session_id": "uuid",
    "agent_name": "researcher",
    "agent_type": "react",
    "status": "completed",
    "steps": [
      {
        "step_index": 1,
        "state": "THINKING",
        "thought": "I need to search the knowledge base for deployment info",
        "action": null,
        "observation": null,
        "token_usage": { "input_tokens": 50, "output_tokens": 20 },
        "created_at": "ISO8601"
      },
      {
        "step_index": 2,
        "state": "ACTING",
        "thought": null,
        "action": { "tool": "kb_search", "input": { "query": "deployment" } },
        "observation": null,
        "token_usage": null,
        "created_at": "ISO8601"
      },
      {
        "step_index": 3,
        "state": "OBSERVING",
        "thought": null,
        "action": null,
        "observation": { "result": "found 3 relevant chunks" },
        "token_usage": null,
        "created_at": "ISO8601"
      }
    ],
    "total_token_usage": { "input_tokens": 200, "output_tokens": 150 },
    "created_at": "ISO8601",
    "completed_at": "ISO8601"
  }
}
```

---

### Workflow — [TBD: filled by F13]

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/workflow/run` | Execute workflow (SSE) |
| GET | `/api/v1/workflow/runs/{task_id}` | Get workflow execution result |

#### POST /api/v1/workflow/run

Execute a pre-defined workflow DAG. Workflows are defined in `workflows/` directory and composed in Python code (not a visual canvas).

**Request body**:

```json
{
  "user_id": "string (required)",
  "session_id": "string (required)",
  "workflow_id": "string (required)",
  "inputs": {},
  "stream": true?,
  "metadata": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | yes | User identifier |
| session_id | string | yes | Session identifier |
| workflow_id | string | yes | Workflow name from `workflows/` directory |
| inputs | object | no | Key-value input parameters for the workflow |
| stream | boolean | no | Default true; false returns sync JSON |
| metadata | object | no | Extensible business metadata |

**Response (SSE)**:

```
start → [progress]* → [agent]* → [tool]* → [heartbeat]* → chunk* → [usage]? → done
                                                                        ↘ error (anytime)
```

SSE events specific to Workflow:

| Event | Data Fields | Description |
|-------|-------------|-------------|
| `progress` | `current`, `total`, `node` | Node execution progress |

**Response (sync, stream=false)**:

```json
{
  "code": 0,
  "data": {
    "task_id": "uuid",
    "workflow_id": "rag_qa",
    "content": "full response text",
    "nodes": [
      { "name": "intent_classify", "status": "completed", "duration_ms": 120 },
      { "name": "rag_search", "status": "completed", "duration_ms": 350 },
      { "name": "generate", "status": "completed", "duration_ms": 800 }
    ],
    "usage": {
      "input_tokens": 150,
      "output_tokens": 300,
      "model": "qwen-plus"
    }
  }
}
```

#### GET /api/v1/workflow/runs/{task_id}

Get execution result and per-node status for a workflow run.

**Response**:

```json
{
  "code": 0,
  "data": {
    "task_id": "uuid",
    "workflow_id": "rag_qa",
    "status": "completed",
    "nodes": [
      { "name": "intent_classify", "status": "completed", "duration_ms": 120, "output": { "intent": "qa" } },
      { "name": "rag_search", "status": "completed", "duration_ms": 350, "output": { "chunks_count": 5 } },
      { "name": "generate", "status": "completed", "duration_ms": 800, "output": { "content": "..." } }
    ],
    "total_duration_ms": 1270,
    "created_at": "ISO8601",
    "completed_at": "ISO8601"
  }
}
```

---

### Task Queue — [TBD: filled by F07]

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/tasks` | Submit async task |
| GET | `/api/v1/tasks/{task_id}` | Query task status (unified for all async sources) |

#### POST /api/v1/tasks

Submit a custom async task. For AI-driven tasks, use `/agent/run` or `/workflow/run` instead. This endpoint is for pure computation / IO tasks that don't require LLM (batch import, batch evaluation, embedding generation, etc.).

**Request body**:

```json
{
  "task_type": "string (required)",
  "input_data": {},
  "callback_url": "string?",
  "metadata": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| task_type | string | yes | Task type: `batch_import` / `batch_eval` / `batch_embed` / custom |
| input_data | object | no | Task input payload (free-form key-value) |
| callback_url | string | no | URL to POST notification when task completes |
| metadata | object | no | Extensible business metadata |

**Response**:

```json
{
  "code": 0,
  "data": {
    "task_id": "uuid",
    "task_type": "batch_import",
    "status": "pending",
    "created_at": "ISO8601"
  }
}
```

#### GET /api/v1/tasks/{task_id}

Unified task status query for all async sources: Agent, Workflow, KB upload, and custom tasks. Use `task_type` to distinguish source.

**Response**:

```json
{
  "code": 0,
  "data": {
    "task_id": "uuid",
    "task_type": "kb_upload | agent_run | workflow_run | batch_import | batch_eval | batch_embed | custom",
    "status": "pending | running | completed | failed",
    "progress": 0.35,
    "input_data": {},
    "output_data": {},
    "error_message": null,
    "created_at": "ISO8601",
    "started_at": "ISO8601",
    "completed_at": null
  }
}
```

---

### Observability — [TBD: filled by F18]

| Method | Path | Description |
|--------|------|-------------|
| GET | `/metrics` | Prometheus metrics endpoint |

#### GET /metrics

Prometheus-format metrics. Not under `/api/v1` prefix (follows Prometheus convention).

**Metrics registry**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `llm_request_total` | Counter | provider, model, task_type | LLM call count |
| `llm_request_duration_seconds` | Histogram | provider, model | LLM call latency |
| `llm_tokens_total` | Counter | provider, model, direction (input/output) | Token usage |
| `llm_circuit_breaker_state` | Gauge | provider, channel | Circuit breaker state (0=closed, 1=open, 2=half_open) |
| `http_request_total` | Counter | method, path, status | HTTP request count |
| `http_request_duration_seconds` | Histogram | method, path | HTTP request latency |
| `kb_document_count` | Gauge | collection | Document count per collection |
| `kb_query_duration_seconds` | Histogram | collection, strategy | RAG query latency |
| `agent_step_total` | Counter | agent_name, agent_type | Agent execution step count |
| `agent_step_duration_seconds` | Histogram | agent_name | Agent single step latency |

---

## SSE Event Protocol

All SSE streaming endpoints follow the same event protocol. Events are sent in order:

```
start → [intent]? → [route]? → [heartbeat]* → chunk* → [structured]? → [citation]? → [usage]? → done
              → [agent]* → [tool]* → [progress]*
                                                                    ↘ error (anytime)
```

### Event Types

| Event | Direction | Data Fields | Description |
|-------|-----------|-------------|-------------|
| `start` | Server → Client | `intent`, `user_id`, `session_id` | Stream begins; intent indicates which domain (qa/chat/task/retrieve_only/agent/workflow) |
| `intent` | Server → Client | `intent`, `confidence`, `layer_used` | Intent classification result |
| `chunk` | Server → Client | `content` | Streaming text content token |
| `structured` | Server → Client | `data`, `user_id?`, `session_id?` | Structured data payload |
| `citation` | Server → Client | `sources` | Reference sources from knowledge base retrieval |
| `heartbeat` | Server → Client | `ts` | Keep-alive during long operations; interval defined by `SSE_HEARTBEAT_INTERVAL` config |
| `progress` | Server → Client | `current`, `total` | Progress indicator for multi-step operations |
| `usage` | Server → Client | `input_tokens`, `output_tokens`, `model` | Token usage statistics; must be sent before `done` |
| `done` | Server → Client | `reason` | Stream completed successfully; reason typically "complete" |
| `error` | Server → Client | `code`, `message` | Error occurred; code is AI_xxxx error code from ERROR_CODE.md |

### SSE Endpoint Behavior

- **Heartbeat**: Sent every `SSE_HEARTBEAT_INTERVAL` seconds (default 15) during LLM calls to prevent connection timeout
- **Disconnect detection**: Server checks `request.is_disconnected` before each event; stops stream on disconnect
- **Error handling**: If an error occurs mid-stream, an `error` event is sent followed by stream termination (no `done` event)
- **Event ordering**: `start` is always first; `done` or `error` is always last; other events may appear in domain-specific order
- **Usage**: `usage` event is sent before `done` on all streaming endpoints that involve LLM calls

## Authentication — [TBD: filled by F20]

- API Key header: `X-API-Key`
- Rate limiting via Redis (configurable thresholds)

## Request Context Propagation

Every request must carry:
- `trace_id` — auto-generated or from header `X-Trace-Id`
- `request_id` — auto-generated UUID
- `user_id` — from auth or header `X-User-Id`
- `session_id` — from request body or header

[TBD: filled by work orders F01, F06, F07, F14–F17, F20]
