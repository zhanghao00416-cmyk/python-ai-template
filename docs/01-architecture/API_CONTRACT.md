# API 契约

## 概述

本文档定义 Python AI Template 平台的 API 契约。所有端点遵循 REST 约定，使用结构化 JSON 响应和 SSE 进行流式传输。

## 基础 URL

```
/api/v1
```

## 通用响应信封

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "uuid",
  "trace_id": "uuid",
  "data": { }
}
```

错误响应：

```json
{
  "code": 1001,
  "message": "Unauthorized: invalid API key",
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

## 端点注册表

### Health — [filled by F01, enhanced]

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/health | 健康检查，含依赖详情 |

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
| status | 总体状态：`ok`（全部健康）、`degraded`（部分降级）、`error`（关键故障） |
| dependencies.*.status | `ok` = 正常, `degraded` = 慢但可用, `error` = 不可用 |
| dependencies.llm.channels.*.status | `ok` = 正常, `open` = 熔断器跳开, `half_open` = 探测恢复中 |
| dependencies.*.latency_ms | 响应延迟（毫秒）；`null` = 未检查或不可用 |

---

### Orchestrated — [TBD: filled by F14+]

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/run | 统一编排入口（SSE） |

#### POST /api/v1/run — 统一入口（SSE）

对话 AI 的主入口。服务端编排：意图分类 → 工作流选择 → 多 Agent 执行 → 工具调用 → SSE 流式响应。

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
| user_id | string | yes | 用户标识 |
| session_id | string | yes | 会话标识；不存在时自动创建 |
| query | string | yes | 用户输入 |
| stream | boolean | no | 默认 true；false 返回同步 JSON 响应 |
| intent | string | no | 跳过意图分类（调用方已知）；如 "qa"、"chat" |
| model_override | string | no | 本次请求覆盖默认模型 |
| temperature | float | no | 生成随机性（0.0–1.0） |
| max_tokens | int | no | 最大生成长度 |
| metadata | object | no | 可扩展业务元数据（渠道、版本等） |

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

编排专用 SSE 事件（除标准事件外）：

| Event | Data Fields | Description |
|-------|-------------|-------------|
| `intent` | `intent`, `confidence`, `layer_used` | 意图分类结果 |
| `route` | `workflow_id`, `intent` | 选中的工作流 |
| `agent` | `agent_name`, `step_id` | Agent 步骤开始 |
| `tool` | `tool_name`, `step_id` | 工具调用（开始/结果） |

**`/run` 的意图分类**：使用简化四类模型（可由业务扩展）：

| Intent | Description |
|--------|-------------|
| `qa` | 知识问答（默认 RAG 工作流） |
| `task` | 需要工具的多步任务 |
| `chat` | 自由对话，无检索 |
| `retrieve_only` | 纯检索，无生成 |

**集成模式**：

| 模式 | 用法 |
|------|------|
| 对话模式 | 仅 `POST /run` |
| 自编排模式 | `POST /intent` → 调用各能力 API |
| 混合模式 | 通过 `/kb/collections` 上传知识；通过 `/run` 对话 |

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
| POST | /api/v1/chat | 聊天补全（自动创建会话，SSE 或同步） |
| GET | /api/v1/chat/sessions/{session_id} | 获取会话详情 |
| GET | /api/v1/chat/sessions/{session_id}/messages | 列出会话消息 |
| DELETE | /api/v1/chat/sessions/{session_id} | 删除会话（软删除，级联消息） |

#### POST /api/v1/chat

会话自动创建：如果 `session_id` 不存在，自动创建新会话。首次字段（`title`、`model_config`）仅在创建时生效。

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
| user_id | string | yes | 用户标识 |
| session_id | string | yes | 调用方生成的 UUID；不存在时自动创建 |
| query | string | yes | 用户消息 |
| stream | boolean | no | 默认 true；false 返回同步 JSON |
| model_override | string | no | 覆盖默认聊天模型 |
| temperature | float | no | 生成随机性（0.0–1.0） |
| max_tokens | int | no | 最大生成长度 |
| title | string | no | 会话标题；仅在首次创建会话时使用 |
| model_config | object | no | 模型配置覆盖；仅在首次创建会话时使用 |
| metadata | object | no | 可扩展业务元数据 |

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
| limit | int | 20 | 每页消息数 |
| offset | int | 0 | 分页偏移 |
| role | string | null | 按角色过滤：user / assistant / system / tool |
| before | ISO8601 | null | 此时间戳之前的消息（游标式） |

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

软删除：标记会话为已删除，级联删除所有消息（同样软删除）。

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
| POST | /api/v1/kb/collections | 创建集合 |
| GET | /api/v1/kb/collections | 列出集合 |
| DELETE | /api/v1/kb/collections/{collection_name} | 删除集合 |
| POST | /api/v1/kb/collections/{collection_name}/documents | 上传文档（异步） |
| GET | /api/v1/kb/collections/{collection_name}/documents | 列出/搜索文档 |
| DELETE | /api/v1/kb/collections/{collection_name}/documents | 删除文档（批量/清空） |
| POST | /api/v1/kb/query | RAG 查询（可配置检索策略） |

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
| name | string | yes | 集合名称（唯一） |
| description | string | no | 集合描述 |
| vector_size | int | no | 向量维度；默认从配置读取 |
| metadata | object | no | 可扩展集合元数据 |

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
| limit | int | 20 | 每页集合数 |
| offset | int | 0 | 分页偏移 |
| name | string | null | 按名称模糊搜索 |

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

**Response**（含影响范围）：

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

上传 Markdown 文档，支持分块策略和元数据。处理为异步——返回 task_id。

**Request** (multipart/form-data):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | File | yes | Markdown 文件（.md） |
| doc_type | string | no | 元数据：文档类型（如 技术文档/手册/FAQ） |
| source | string | no | 元数据：来源（如 内部/外部/爬取） |
| tag | string | no | 元数据：标签（如 重要/已审核/草稿） |
| uploader | string | yes | 上传者标识 |
| chunking_strategy | string | no | 分块策略，默认从配置读取 |
| chunking_params | object | no | 策略参数 |
| enable_parent_child | boolean | no | 启用父子分块模式；默认 false |
| parent_chunk_params | object | no | 父分块配置（仅在 enable_parent_child=true 时有效） |

**分块策略**：

| Strategy | Key | Parameters |
|----------|-----|------------|
| 固定大小 + 重叠 | `fixed_overlap` | `chunk_size`（默认 500）、`overlap`（默认 50） |
| 分隔符 + 最大长度 | `delimiter_max` | `delimiters`（默认 ["\n\n", "\n"]）、`max_chunk_size`（默认 1000） |
| 语义分块 | `semantic` | `similarity_threshold`（默认 0.85） |
| 段落分块 | `paragraph` | `min_paragraph_chars`（默认 50） |

**父子分块模式**：

当 `enable_parent_child=true` 时，文档以两种粒度分块：

1. **父块**：大粒度分块，用于上下文（始终使用 `fixed_overlap` 策略配合 `parent_chunk_params`）
2. **子块**：细粒度分块，用于精确匹配（使用选定的 `chunking_strategy`）

每个子块存储 `parent_id` 链接到其父块。检索时，匹配子块会自动返回父块以提供完整上下文。

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
| `parent_chunk_params.chunk_size` | 父块大小（默认 2000） |
| `parent_chunk_params.overlap` | 父块重叠（默认 200） |

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

去重：如果同名称 + 同上传者 + 同集合的文件已存在，返回 HTTP 409 含已有 document_id。

#### GET /api/v1/kb/collections/{collection_name}/documents

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| limit | int | 20 | 每页文档数 |
| offset | int | 0 | 分页偏移 |
| filename | string | null | 按文件名模糊搜索 |
| doc_type | string | null | 按 doc_type 元数据过滤 |
| source | string | null | 按 source 元数据过滤 |
| tag | string | null | 按 tag 元数据过滤 |
| uploader | string | null | 按上传者过滤 |

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

支持定向删除和一键清空（需两步确认）。

**Query parameters**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| doc_id | string | no | 按 ID 删除指定文档 |
| doc_type | string | no | 过滤：删除所有匹配 doc_type 的文档 |
| source | string | no | 过滤：删除所有匹配 source 的文档 |
| tag | string | no | 过滤：删除所有匹配 tag 的文档 |
| uploader | string | no | 过滤：删除所有匹配 uploader 的文档 |
| filename | string | no | 过滤：按文件名匹配删除（模糊） |
| clear_all | boolean | no | 清空集合内所有文档 |
| confirm_token | string | no | 预检响应返回的确认令牌 |

**两步确认流程**：

1. **不带 `confirm_token`**：返回影响范围 + `confirm_token`（60 秒有效）。不执行删除。

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

2. **带 `confirm_token`**：执行删除。

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

RAG 检索与生成，支持可配置策略。

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
| user_id | string | yes | 用户标识 |
| session_id | string | no | 会话（用于上下文） |
| query | string | yes | 搜索查询 |
| collection_names | string[] | no | 目标集合；默认全部 |
| doc_type | string | no | 按 doc_type 元数据过滤 |
| source | string | no | 按 source 元数据过滤 |
| tag | string | no | 按 tag 元数据过滤 |
| uploader | string | no | 按上传者过滤 |
| retrieval_strategy | string | no | 见下表；默认 `hybrid` |
| top_k | int | no | 返回结果数；默认 5 |
| score_threshold | float | no | 最低相似度分数；默认 0.5 |
| enable_rerank | boolean | no | 启用重排序；默认 false |
| stream | boolean | no | SSE 或同步；默认 true |
| model_override | string | no | 覆盖生成模型 |
| temperature | float | no | 生成随机性 |
| max_tokens | int | no | 最大生成长度 |

**检索策略**：

| Strategy | Key | Description |
|----------|-----|-------------|
| 关键词 | `keyword` | 稀疏向量 / 全文搜索 |
| 语义相似 | `similarity` | 稠密向量搜索 |
| 混合 | `hybrid` | 关键词 + 相似度组合（默认） |
| RRF | `rrf` | 倒数排名融合 |

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
| POST | /api/v1/intent | 意图分类（三层 + 多意图） |

#### POST /api/v1/intent

三层分类流水线：关键词 → 相似度 → LLM。较早层可短路返回。支持多意图检测与查询重构。

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
| user_id | string | yes | 用户标识 |
| session_id | string | yes | 会话标识 |
| query | string | yes | 用户输入 |
| candidates | string[] | no | 限定分类范围；默认全部已配置意图 |
| options.keyword_enabled | boolean | no | 启用 L1 关键词匹配；默认 true |
| options.similarity_enabled | boolean | no | 启用 L2 相似度匹配；默认 true |
| options.multi_intent_enabled | boolean | no | 启用多意图检测；默认 true |

**三层流水线**：

```
L1: 关键词匹配（最快，零 LLM 开销）
    ↓ 未匹配或低置信度
L2: 相似度匹配（基于嵌入向量，低开销）
    ↓ 未匹配或低置信度
L3: LLM 分类（最准确，最高开销）
```

**意图配置**（在 `configs/default.yaml` 中）：

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

**默认意图类型**（可由业务通过 prompt 扩展）：

| Intent | Description |
|--------|-------------|
| `qa` | 知识问答 |
| `task` | 需要工具的多步任务 |
| `chat` | 自由对话 |
| `retrieve_only` | 纯检索，无生成 |

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
| intent | 主意图（最高置信度）；此为应执行的意图 |
| confidence | 主意图置信度（0.0–1.0） |
| query | 主意图重构后的完整查询（解析主语省略） |
| layer_used | 解析层：`keyword` / `similarity` / `llm` |
| routing | 主意图推荐路由 |
| sub_intents | 附带意图（不执行，返回供调用方编排） |
| sub_intents[].query | 重构后的完整查询（解析主语省略） |
| sub_intents[].original_query | 原始文本片段 |

---

### Prompt 管理 — [TBD: filled by F17]

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/prompts` | 查询 Prompt 模板（列表 + 带过滤的详情） |
| PUT | `/api/v1/prompts/{name}` | 修改 Prompt（自动版本递增 + 回滚） |
| GET | `/api/v1/prompts/{name}/versions` | Prompt 版本历史 |
| POST | `/api/v1/prompts/{name}/reset` | 重置为基线版本 |

#### GET /api/v1/prompts

查询模板，支持分页和过滤。当 `name` 过滤条件精确匹配单条结果时，返回完整详情（含内容）。

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| limit | int | 20 | 每页模板数 |
| offset | int | 0 | 分页偏移 |
| directory | string | null | 按目录过滤（如 "agents"、"skills"） |
| name | string | null | 按模板名模糊搜索；精确匹配返回详情 |

**Response (列表)**:

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

**Response (单条，精确名称匹配)**:

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

修改 Prompt 内容或回滚到指定版本。`content` 和 `rollback_version` 互斥。

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
| content | string | no* | 新 Prompt 内容；自动提取变量 |
| description | string | no | 更新描述 |
| rollback_version | int | no* | 回滚到指定版本；与 content 互斥 |

*`content` 和 `rollback_version` 至少提供一个。

版本历史：每次更新或回滚递增 `version`。所有历史版本保留在 `prompt_templates` 表中。

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

列出 Prompt 模板的所有历史版本。

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

将 Prompt 重置为 `prompts/` 目录中的基线内容。基线文件是启动时加载的事实来源。

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
| POST | `/api/v1/agent/run` | 执行 Agent 任务（SSE） |
| GET | `/api/v1/agent/trajectories` | 按会话列出轨迹 |
| GET | `/api/v1/agent/trajectories/{task_id}` | 获取轨迹详情 |

#### POST /api/v1/agent/run

使用指定引擎类型、工具和技能执行 Agent 任务。支持 react（动态）、workflow（预定义 DAG）和 orchestrator（多 Agent）模式。

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
| user_id | string | yes | 用户标识 |
| session_id | string | yes | 会话标识 |
| query | string | yes | 任务描述 / 用户输入 |
| agent_type | string | no | 引擎类型：`react`（默认）/ `workflow` / `orchestrator` |
| agent_name | string | no | `configs/agents.yaml` 中的角色名；加载 prompt、默认工具/技能、模型 |
| tools | string[] | no | 覆盖允许的工具；默认从 Agent 配置或全部可用工具获取 |
| skills | string[] | no | 覆盖允许的技能；技能使用的工具从直接工具列表中屏蔽 |
| max_steps | int | no | 最大执行步数；默认 10，防止无限循环 |
| stream | boolean | no | 默认 true；false 返回同步 JSON |
| model_override | string | no | 本次运行覆盖模型 |
| metadata | object | no | 可扩展业务元数据 |

**工具 / 技能 / MCP 层级**：

| Type | Description | Source |
|------|-------------|--------|
| Tool | 原子操作 | 内置 + MCP 注册（MCP 对调用方透明） |
| Skill | 多步编排（prompt + 步骤 + 工具） | `skills/` 目录定义 |

优先级：`请求覆盖` > `Agent 配置` > `全部可用`

互斥：如果技能使用了某工具（如 `rag_answer` 使用 `kb_search`），该工具从 Agent 直接工具列表中屏蔽以防止冲突。

**Agent 配置**（`configs/agents.yaml`）：

```yaml
agents:
  researcher:
    system_prompt: "prompts/agents/researcher.md"
    tools: ["kb_search", "code_execute"]
    skills: ["rag_answer"]
    model_routing: "chat"
    max_steps: 8
```

**工具注册**（`configs/default.yaml`）：

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

Agent 专用 SSE 事件：

| Event | Data Fields | Description |
|-------|-------------|-------------|
| `agent` | `agent_name`, `step_id`, `state` | Agent 状态变更（IDLE/THINKING/ACTING/OBSERVING/DONE） |
| `tool` | `tool_name`, `step_id`, `status` | 工具调用开始/结果 |

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

列出 Agent 执行轨迹，按会话过滤。

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| session_id | string | null | 按会话 ID 过滤 |
| agent_name | string | null | 按 Agent 名称过滤 |
| limit | int | 20 | 每页结果数 |
| offset | int | 0 | 分页偏移 |

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

获取单次 Agent 执行的详细轨迹。

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
| POST | `/api/v1/workflow/run` | 执行工作流（SSE） |
| GET | `/api/v1/workflow/runs/{task_id}` | 获取工作流执行结果 |

#### POST /api/v1/workflow/run

执行预定义的工作流 DAG。工作流定义在 `workflows/` 目录，使用 Python 代码编排（非可视化画布）。

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
| user_id | string | yes | 用户标识 |
| session_id | string | yes | 会话标识 |
| workflow_id | string | yes | `workflows/` 目录中的工作流名称 |
| inputs | object | no | 工作流的键值输入参数 |
| stream | boolean | no | 默认 true；false 返回同步 JSON |
| metadata | object | no | 可扩展业务元数据 |

**Response (SSE)**:

```
start → [progress]* → [agent]* → [tool]* → [heartbeat]* → chunk* → [usage]? → done
                                                                        ↘ error (anytime)
```

Workflow 专用 SSE 事件：

| Event | Data Fields | Description |
|-------|-------------|-------------|
| `progress` | `current`, `total`, `node` | 节点执行进度 |

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

获取工作流运行的执行结果和各节点状态。

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
| POST | `/api/v1/tasks` | 提交异步任务 |
| GET | `/api/v1/tasks/{task_id}` | 查询任务状态（统一所有异步来源） |

#### POST /api/v1/tasks

提交自定义异步任务。AI 驱动的任务请使用 `/agent/run` 或 `/workflow/run`。此端点适用于不需要 LLM 的纯计算/IO 任务（批量导入、批量评估、嵌入生成等）。

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
| task_type | string | yes | 任务类型：`batch_import` / `batch_eval` / `batch_embed` / 自定义 |
| input_data | object | no | 任务输入载荷（自由键值） |
| callback_url | string | no | 任务完成时 POST 通知的 URL |
| metadata | object | no | 可扩展业务元数据 |

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

统一任务状态查询，适用于所有异步来源：Agent、Workflow、KB 上传和自定义任务。使用 `task_type` 区分来源。

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

### 可观测性 — [TBD: filled by F18]

| Method | Path | Description |
|--------|------|-------------|
| GET | `/metrics` | Prometheus 指标端点 |

#### GET /metrics

Prometheus 格式指标。不在 `/api/v1` 前缀下（遵循 Prometheus 约定）。

**指标注册表**：

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `llm_request_total` | Counter | provider, model, task_type | LLM 调用次数 |
| `llm_request_duration_seconds` | Histogram | provider, model | LLM 调用延迟 |
| `llm_tokens_total` | Counter | provider, model, direction (input/output) | Token 使用量 |
| `llm_circuit_breaker_state` | Gauge | provider, channel | 熔断器状态（0=关闭, 1=打开, 2=半开） |
| `http_request_total` | Counter | method, path, status | HTTP 请求次数 |
| `http_request_duration_seconds` | Histogram | method, path | HTTP 请求延迟 |
| `kb_document_count` | Gauge | collection | 每集合文档数 |
| `kb_query_duration_seconds` | Histogram | collection, strategy | RAG 查询延迟 |
| `agent_step_total` | Counter | agent_name, agent_type | Agent 执行步数 |
| `agent_step_duration_seconds` | Histogram | agent_name | Agent 单步延迟 |

---

## SSE 事件协议

所有 SSE 流式端点遵循相同的事件协议。事件按顺序发送：

```
start → [intent]? → [route]? → [heartbeat]* → chunk* → [structured]? → [citation]? → [usage]? → done
               → [agent]* → [tool]* → [progress]*
                                                                     ↘ error (anytime)
```

### 事件类型

| Event | Direction | Data Fields | Description |
|-------|-----------|-------------|-------------|
| `start` | 服务端 → 客户端 | `intent`, `user_id`, `session_id` | 流开始；intent 指示所属域（qa/chat/task/retrieve_only/agent/workflow） |
| `intent` | 服务端 → 客户端 | `intent`, `confidence`, `layer_used` | 意图分类结果 |
| `chunk` | 服务端 → 客户端 | `content` | 流式文本内容 token |
| `structured` | 服务端 → 客户端 | `data`, `user_id?`, `session_id?` | 结构化数据载荷 |
| `citation` | 服务端 → 客户端 | `sources` | 知识库检索的引用来源 |
| `heartbeat` | 服务端 → 客户端 | `ts` | 长操作期间保持连接；间隔由 `SSE_HEARTBEAT_INTERVAL` 配置定义 |
| `progress` | 服务端 → 客户端 | `current`, `total` | 多步操作进度指示 |
| `usage` | 服务端 → 客户端 | `input_tokens`, `output_tokens`, `model` | Token 使用统计；必须在 `done` 之前发送 |
| `done` | 服务端 → 客户端 | `reason` | 流成功完成；reason 通常为 "complete" |
| `error` | 服务端 → 客户端 | `code`, `message` | 发生错误；code 为 ERROR_CODE.md 中的 AI_xxxx 错误码 |

### SSE 端点行为

- **心跳**：LLM 调用期间每隔 `SSE_HEARTBEAT_INTERVAL` 秒（默认 15）发送，防止连接超时
- **断连检测**：服务端在每个事件前检查 `request.is_disconnected`；断连时停止流
- **错误处理**：如果流中途发生错误，发送 `error` 事件后终止流（不发送 `done` 事件）
- **事件顺序**：`start` 始终为首；`done` 或 `error` 始终为尾；其他事件按域特定顺序出现
- **使用量**：所有涉及 LLM 调用的流式端点，在 `done` 之前发送 `usage` 事件

## 认证 — [TBD: filled by F20]

- API Key 头：`X-API-Key`
- 通过 Redis 限流（可配置阈值）

## 请求上下文传播

每个请求必须携带：
- `trace_id` — 自动生成或来自请求头 `X-Trace-Id`
- `request_id` — 自动生成 UUID
- `user_id` — 来自认证或请求头 `X-User-Id`
- `session_id` — 来自请求体或请求头

[TBD: filled by work orders F01, F06, F07, F14–F17, F20]