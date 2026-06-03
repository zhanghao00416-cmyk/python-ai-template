# Error Code System

## Overview

All platform errors use a **4-digit domain code** (e.g. `2003`). Codes are categorized by domain. No raw stack traces are ever returned to clients.

## Canonical Format (F03+ 必须遵守)

| 场景 | `code` 字段类型 | 示例 | 说明 |
|------|----------------|------|------|
| **REST JSON 响应** | `integer` | `2003` | 成功为 `0`；业务错误为表内 4 位整数，**不带** `AI_` 前缀 |
| **SSE `error` 事件** | `string` | `"AI_2003"` | 格式 `AI_%04d`，与 REST 数值一一对应 |
| **日志 / 轨迹** | `string`（推荐） | `AI_2003` | 便于检索；可由 `format_error_code(2003)` 生成 |
| **Python `AppError.code`** | `int` | `2003` | 与 REST 整数一致；枚举见 `app/core/errors.py` |

转换规则（实现放在 `app/core/errors.py`，F03 注册）：

```python
def format_error_code(code: int) -> str:
    """2003 -> 'AI_2003'"""
    return f"AI_{code:04d}"

def parse_error_code(value: str | int) -> int:
    """'AI_2003' or 2003 -> 2003"""
    if isinstance(value, int):
        return value
    s = value.strip().upper()
    if s.startswith("AI_"):
        s = s[3:]
    return int(s)
```

**禁止**：REST 返回 `"AI_2003"` 字符串；SSE 返回裸整数 `2003`（除非变更单明确统一）。

## Error Response Format (REST)

```json
{
  "code": 2003,
  "message": "Intent classification failed: LLM timeout",
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

## Domain Code Ranges

| Range | Domain | Description |
|-------|--------|-------------|
| 1xxx | Auth | Authentication & authorization errors |
| 2xxx | Intent | Intent classification & routing errors |
| 3xxx | RAG | Retrieval-augmented generation errors |
| 4xxx | Multimodal | Multimodal processing errors |
| 5xxx | Reserved | Reserved for business-specific use |
| 6xxx | Knowledge | Knowledge base management errors |
| 7xxx | Agent | Agent engine errors |
| 8xxx | Workflow | Workflow engine errors |
| 0xxx | System | General / infrastructure errors |

## Error Code Definitions

### 0xxx — System / Infrastructure — [TBD: filled by F01, F03]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 0001 | INTERNAL_ERROR | 500 | Unhandled internal error |
| 0002 | CONFIG_ERROR | 500 | Configuration loading or validation error |
| 0003 | SERVICE_UNAVAILABLE | 503 | Required service unavailable |
| 0004 | TIMEOUT_ERROR | 504 | Operation timed out (includes semaphore acquire timeout) |
| 0005 | VALIDATION_ERROR | 400 | Request validation failed |
| 0006 | RATE_LIMITED | 429 | Request rate limit exceeded |
| 0007 | DEPENDENCY_ERROR | 502 | External dependency call failed |

### 1xxx — Auth — [TBD: filled by F20]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 1001 | AUTH_INVALID_KEY | 401 | Invalid or missing API key |
| 1002 | AUTH_EXPIRED_KEY | 401 | API key has expired |
| 1003 | AUTH_FORBIDDEN | 403 | Insufficient permissions |
| 1004 | AUTH_RATE_LIMITED | 429 | Rate limit exceeded for this key |
| 1005 | AUTH_BODY_TOO_LARGE | 413 | Request body exceeds max size |

### 2xxx — Intent — [TBD: filled by F16]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 2001 | INTENT_CLASSIFY_FAILED | 500 | Intent classification LLM call failed |
| 2002 | INTENT_UNKNOWN | 400 | Could not determine intent or missing required field |
| 2003 | INTENT_TIMEOUT | 504 | Intent classification timed out |
| 2004 | INTENT_INVALID_INPUT | 400 | Input too short or malformed for classification |

### 3xxx — RAG — [TBD: filled by F15b]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 3001 | RAG_COLLECTION_NOT_FOUND | 404 | Requested collection does not exist |
| 3002 | RAG_RETRIEVAL_FAILED | 400 | Invalid collection name or retrieval query failed |
| 3003 | RAG_NO_RESULTS | 200 | Retrieval returned no relevant documents |
| 3004 | RAG_GENERATION_FAILED | 500 | Answer generation LLM call failed |
| 3005 | RAG_INDEXING_FAILED | 500 | Document indexing failed |
| 3006 | RAG_DOCUMENT_NOT_FOUND | 404 | Requested document does not exist |
| 3007 | RAG_RERANK_NOT_ENABLED | 400 | Rerank requested but not implemented |

### 4xxx — Multimodal — [TBD: reserved]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 4001 | MULTIMODAL_INVALID_INPUT | 400 | Invalid or unreachable multimodal input |
| 4002 | MULTIMODAL_PROCESSING_FAILED | 500 | Multimodal processing failed |

### 5xxx — Reserved — [TBD: reserved]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 5001 | RESERVED_5001 | - | Reserved for business-specific use |
| 5002 | RESERVED_5002 | - | Reserved for business-specific use |
| 5003 | RESERVED_5003 | - | Reserved for business-specific use |

### 6xxx — Knowledge — [TBD: filled by F05, F15a/F15b/F15c]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 6001 | KB_UPLOAD_FAILED | 500 | File upload failed |
| 6002 | KB_FILENAME_EXISTS | 409 | Filename already exists |
| 6003 | KB_FILE_NOT_FOUND | 404 | File not found |
| 6004 | KB_FORMAT_UNSUPPORTED | 415 | File format unsupported (only markdown) |
| 6005 | KB_VECTOR_WRITE_FAILED | 500 | Vector write failed |
| 6006 | KB_CHUNK_LIMIT_EXCEEDED | 413 | Chunk count exceeds max_chunks limit |

### 7xxx — Agent — [TBD: filled by F11, F12]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 7001 | AGENT_STATE_INVALID | 400 | Invalid state transition |
| 7002 | AGENT_TOOL_NOT_FOUND | 404 | Referenced tool not registered |
| 7003 | AGENT_EXECUTION_FAILED | 500 | Agent execution loop failed |
| 7004 | AGENT_MAX_ITERATIONS | 500 | Agent exceeded max iterations |
| 7005 | AGENT_ORCHESTRATION_FAILED | 500 | Multi-agent orchestration failed |

### 8xxx — Workflow — [TBD: filled by F13]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 8001 | WORKFLOW_NODE_NOT_FOUND | 404 | Referenced node does not exist |
| 8002 | WORKFLOW_EDGE_INVALID | 400 | Invalid conditional edge configuration |
| 8003 | WORKFLOW_EXECUTION_FAILED | 500 | Workflow execution failed |
| 8004 | WORKFLOW_CYCLE_DETECTED | 400 | Workflow DAG contains a cycle |
| 8005 | WORKFLOW_STATE_ERROR | 400 | Invalid workflow state transition |

### 9xxx — Task Queue / Prompt / SSE — [TBD: filled by F07, F08, F17]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 9001 | TASK_NOT_FOUND | 404 | Referenced task does not exist |
| 9002 | TASK_ALREADY_RUNNING | 409 | Task is already in running state |
| 9003 | TASK_SUBMIT_FAILED | 500 | Failed to submit task to queue |
| 9004 | PROMPT_NOT_FOUND | 404 | Prompt template file not found |
| 9005 | PROMPT_PATH_INVALID | 400 | Prompt path contains invalid characters or traversal |
| 9006 | PROMPT_WRITE_FAILED | 500 | Failed to write prompt template |
| 9007 | SSE_CONNECTION_LOST | 200 | Client disconnected during SSE streaming |

### Model Gateway — uses 11xx per convention — [TBD: filled by F04]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 1101 | MODEL_TIMEOUT | 504 | Model call timed out |
| 1102 | LOCAL_MODEL_UNAVAILABLE | 503 | Local vLLM service unavailable (circuit open) |
| 1103 | MODEL_FORMAT_ERROR | 502 | Model returned malformed response |
| 1104 | CLOUD_MODEL_ERROR | 503 | Cloud API call failed (circuit open) |

### Infrastructure — uses 12xx — [TBD: filled by F02, F05]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 1201 | DATABASE_ERROR | 500 | Database connection or query failed |
| 1202 | QDRANT_UNAVAILABLE | 503 | Qdrant connection failed |
| 1203 | REDIS_ERROR | 503 | Redis connection or operation failed |

## Error Hierarchy in Code

```
AppError (base)
├── SystemError (0xxx)
├── AuthError (1xxx)
├── IntentError (2xxx)
├── RAGError (3xxx)
├── MultimodalError (4xxx)
├── ReservedError (5xxx)
├── KnowledgeError (6xxx)
├── AgentError (7xxx)
├── WorkflowError (8xxx)
└── TaskError (9xxx)
```

## Registration & Lookup — [TBD: filled by F03]

All error codes are registered in `app/core/errors.py` as a centralized registry. Domain modules raise typed exceptions; the middleware layer catches and maps to structured API responses.

[TBD: filled by work orders F01, F03, F05, F11–F16, F20]