# 错误码体系

## 概述

所有平台错误使用 **4 位域编码**（如 `2003`）。错误码按域分类。绝不会向客户端返回原始堆栈跟踪。

## 规范格式（F03+ 必须遵守）

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

## 错误响应格式（REST）

```json
{
  "code": 2003,
  "message": "Intent classification failed: LLM timeout",
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

## 域编码范围

| Range | Domain | Description |
|-------|--------|-------------|
| 1xxx | Auth | 认证与授权错误 |
| 2xxx | Intent | 意图分类与路由错误 |
| 3xxx | RAG | 检索增强生成错误 |
| 4xxx | Multimodal | 多模态处理错误 |
| 5xxx | Reserved | 保留用于业务特定用途 |
| 6xxx | Knowledge | 知识库管理错误 |
| 7xxx | Agent | 智能体引擎错误 |
| 8xxx | Workflow | 工作流引擎错误 |
| 0xxx | System | 通用 / 基础设施错误 |

## 错误码定义

### 0xxx — 系统 / 基础设施 — [filled by F01, F03]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 0001 | INTERNAL_ERROR | 500 | 未处理的内部错误 |
| 0002 | CONFIG_ERROR | 500 | 配置加载或校验错误 |
| 0003 | SERVICE_UNAVAILABLE | 503 | 所需服务不可用 |
| 0004 | TIMEOUT_ERROR | 504 | 操作超时（含信号量获取超时） |
| 0005 | VALIDATION_ERROR | 400 | 请求校验失败 |
| 0006 | RATE_LIMITED | 429 | 请求速率超限 |
| 0007 | DEPENDENCY_ERROR | 502 | 外部依赖调用失败 |

### 1xxx — 认证 — [filled by F20]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 1001 | AUTH_INVALID_KEY | 401 | API 密钥无效或缺失 |
| 1002 | AUTH_EXPIRED_KEY | 401 | API 密钥已过期 |
| 1003 | AUTH_FORBIDDEN | 403 | 权限不足 |
| 1004 | AUTH_RATE_LIMITED | 429 | 该密钥请求速率超限 |
| 1005 | AUTH_BODY_TOO_LARGE | 413 | 请求体超过最大限制 |

### 2xxx — 意图 — [filled by F16]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 2001 | INTENT_CLASSIFY_FAILED | 500 | 意图分类 LLM 调用失败 |
| 2002 | INTENT_UNKNOWN | 400 | 无法确定意图或缺少必填字段 |
| 2003 | INTENT_TIMEOUT | 504 | 意图分类超时 |
| 2004 | INTENT_INVALID_INPUT | 400 | 输入过短或格式异常，无法分类 |

### 3xxx — RAG — [filled by F15b]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 3001 | RAG_COLLECTION_NOT_FOUND | 404 | 请求的集合不存在 |
| 3002 | RAG_RETRIEVAL_FAILED | 400 | 集合名称无效或检索查询失败 |
| 3003 | RAG_NO_RESULTS | 200 | 检索未返回相关文档 |
| 3004 | RAG_GENERATION_FAILED | 500 | 回答生成 LLM 调用失败 |
| 3005 | RAG_INDEXING_FAILED | 500 | 文档索引失败 |
| 3006 | RAG_DOCUMENT_NOT_FOUND | 404 | 请求的文档不存在 |
| 3007 | RAG_RERANK_NOT_ENABLED | 400 | 请求了重排序但未启用 |

### 4xxx — 多模态 — [reserved]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 4001 | MULTIMODAL_INVALID_INPUT | 400 | 无效或不可达的多模态输入 |
| 4002 | MULTIMODAL_PROCESSING_FAILED | 500 | 多模态处理失败 |

### 5xxx — 保留 — [reserved]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 5001 | RESERVED_5001 | - | 保留用于业务特定用途 |
| 5002 | RESERVED_5002 | - | 保留用于业务特定用途 |
| 5003 | RESERVED_5003 | - | 保留用于业务特定用途 |

### 6xxx — 知识库 — [filled by F05, F15a/F15b/F15c]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 6001 | KB_UPLOAD_FAILED | 500 | 文件上传失败 |
| 6002 | KB_FILENAME_EXISTS | 409 | 文件名已存在 |
| 6003 | KB_FILE_NOT_FOUND | 404 | 文件未找到 |
| 6004 | KB_FORMAT_UNSUPPORTED | 415 | 不支持的文件格式（仅支持 markdown） |
| 6005 | KB_VECTOR_WRITE_FAILED | 500 | 向量写入失败 |
| 6006 | KB_CHUNK_LIMIT_EXCEEDED | 413 | 分块数量超过 max_chunks 限制 |

### 7xxx — 智能体 — [filled by F11, F12]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 7001 | AGENT_STATE_INVALID | 400 | 无效的状态转换 |
| 7002 | AGENT_TOOL_NOT_FOUND | 404 | 引用的工具未注册 |
| 7003 | AGENT_EXECUTION_FAILED | 500 | 智能体执行循环失败 |
| 7004 | AGENT_MAX_ITERATIONS | 500 | 智能体超过最大迭代次数 |
| 7005 | AGENT_ORCHESTRATION_FAILED | 500 | 多智能体编排失败 |

### 8xxx — 工作流 — [filled by F13]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 8001 | WORKFLOW_NODE_NOT_FOUND | 404 | 引用的节点不存在 |
| 8002 | WORKFLOW_EDGE_INVALID | 400 | 无效的条件边配置 |
| 8003 | WORKFLOW_EXECUTION_FAILED | 500 | 工作流执行失败 |
| 8004 | WORKFLOW_CYCLE_DETECTED | 400 | 工作流 DAG 包含环 |
| 8005 | WORKFLOW_STATE_ERROR | 400 | 无效的工作流状态转换 |

### 9xxx — 任务队列 / 提示词 / SSE — [filled by F07, F08, F17]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 9001 | TASK_NOT_FOUND | 404 | 引用的任务不存在 |
| 9002 | TASK_ALREADY_RUNNING | 409 | 任务已处于运行状态 |
| 9003 | TASK_SUBMIT_FAILED | 500 | 提交任务到队列失败 |
| 9004 | PROMPT_NOT_FOUND | 404 | 提示词模板文件未找到 |
| 9005 | PROMPT_PATH_INVALID | 400 | 提示词路径包含非法字符或路径遍历 |
| 9006 | PROMPT_WRITE_FAILED | 500 | 写入提示词模板失败 |
| 9007 | SSE_CONNECTION_LOST | 200 | SSE 流式传输期间客户端断开连接 |

### 模型网关 — 使用 11xx 编码（按约定）— [filled by F04]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 1101 | MODEL_TIMEOUT | 504 | 模型调用超时 |
| 1102 | LOCAL_MODEL_UNAVAILABLE | 503 | 本地 vLLM 服务不可用（熔断开启） |
| 1103 | MODEL_FORMAT_ERROR | 502 | 模型返回格式错误的响应 |
| 1104 | CLOUD_MODEL_ERROR | 503 | 云端 API 调用失败（熔断开启） |

### 基础设施 — 使用 12xx 编码 — [filled by F02]

| Code | Name | HTTP Status | Description |
|------|------|-------------|-------------|
| 1201 | DATABASE_ERROR | 500 | 数据库连接或查询失败 |
| 1202 | QDRANT_UNAVAILABLE | 503 | Qdrant 连接失败 |
| 1203 | REDIS_ERROR | 503 | Redis 连接或操作失败 |

## 代码中的错误层级

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

## 注册与查找 — [filled by F03]

所有错误码在 `app/core/errors.py` 中注册为集中式注册表。域模块抛出类型化异常；中间件层捕获并映射为结构化 API 响应。

[filled by F03, F05, F07, F08, F17]