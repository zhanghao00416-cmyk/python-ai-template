# 域职责映射

## 概述

本文档将每个域包映射到其职责，并定义域之间的边界。域位于 `app/domain/` 下，遵循 `ARCHITECTURE.md §3` 中的严格分层规则。

## 分层规则（回顾）

```
api → domain → services → infra
domain → agent (编排调用)
domain → workflow (编排调用)
domain → tools (使用)
domain ← agent/workflow (域编排是调用者)
```

域禁止：
- 直接访问提供商 SDK（必须通过 `services/` 或 `infra/`）
- 硬编码提示词（必须使用 `services/prompt_manager`）
- 直接调用 LLM 提供商（必须使用 `services/llm/gateway`）

## 域注册表

### session — [filled by F09]

| 方面 | 详情 |
|------|------|
| 包 | `app/domain/session/` |
| 职责 | 会话 CRUD、消息追加/查询/更新、会话过期标记 |
| 关键文件 | `service.py`, `repo.py` |
| 依赖 | `services/context_manager`（上下文窗口截断 + Redis 缓存） |
| API 端点 | F14 负责：POST /api/v1/chat, GET/DELETE session, GET messages |
| 数据模型 | `sessions`, `messages` |
| 工单 | F09（服务层）, F14（API 层） |

### chat — [filled by F14]

| 方面 | 详情 |
|------|------|
| 包 | `app/domain/chat/` |
| 职责 | 聊天对话管理、消息处理、上下文窗口组装 |
| 关键文件 | `service.py`, `repo.py`, `schemas.py` |
| 依赖 | `services/llm`, `services/context`, `services/sse_stream` |
| API 端点 | POST /api/v1/chat, GET/DELETE session, GET messages |
| 数据模型 | `sessions`, `messages` |
| 工单 | F14 |

### knowledge — [filled by F05, F15a/F15b/F15c]

| 方面 | 详情 |
|------|------|
| 包 | `app/domain/knowledge/` |
| 职责 | 知识库管理：集合、文档、索引、RAG 检索 |
| 关键文件 | `service.py`, `repo.py`, `schemas.py` |
| 依赖 | `services/llm`, `infra/vector_store`, `services/prompt_manager` |
| API 端点 | Collection CRUD, document upload/delete, RAG query |
| 数据模型 | Qdrant collections, document metadata |
| 工单 | F05, F15a, F15b, F15c |

### intent — [filled by F16]

| 方面 | 详情 |
|------|------|
| 包 | `app/domain/intent/` |
| 职责 | 意图分类与路由：三层管道（关键词 → 相似度 → LLM）、多意图检测 |
| 关键文件 | `service.py`, `schemas.py` |
| 依赖 | `services/llm`, `services/prompt_manager` |
| API 端点 | POST /api/v1/intent |
| 数据模型 | None（无状态分类） |
| 工单 | F16 |

### prompt_admin — [filled by F08, F17]

| 方面 | 详情 |
|------|------|
| 包 | `app/domain/prompt_admin/` |
| 职责 | 提示词模板查询、修改（自动版本 + 回滚）、版本历史、基线重置 |
| 关键文件 | `service.py`, `repo.py`, `schemas.py` |
| 依赖 | `services/prompt_manager` |
| API 端点 | Prompt list (with detail), modify, versions history, reset |
| 数据模型 | `prompt_templates`, `prompt_template_versions` |
| 工单 | F08, F17 |

### agent_orchestration — [filled by F11, F12]

| 方面 | 详情 |
|------|------|
| 包 | `app/domain/agent_orchestration/` |
| 职责 | 业务编排层，调用 `agent/` 引擎进行任务委派、多 Agent 协调 |
| 关键文件 | `service.py`, `schemas.py` |
| 依赖 | `agent/` (engine), `services/llm`, `domain/chat` |
| API 端点 | POST /api/v1/agent/run, trajectory retrieval |
| 数据模型 | `agent_trajectories` |
| 工单 | F11, F12 |

### workflow_orchestration — [filled by F13]

| 方面 | 详情 |
|------|------|
| 包 | `app/domain/workflow_orchestration/` |
| 职责 | 业务编排层，调用 `workflow/` 引擎执行 DAG |
| 关键文件 | `service.py`, `schemas.py` |
| 依赖 | `workflow/` (engine), `domain/knowledge`, `domain/intent` |
| API 端点 | POST /api/v1/workflow/run, task status |
| 数据模型 | `tasks` |
| 工单 | F13 |

## 跨域边界

### 域可以调用什么

| 调用方 | 可以调用 | 不可调用 |
|--------|----------|----------|
| `chat` | `services/llm`, `services/context`, `services/sse_stream` | `infra/` directly |
| `knowledge` | `services/llm`, `infra/vector_store` (via service), `services/prompt_manager` | `agent/`, `workflow/` |
| `intent` | `services/llm`, `services/prompt_manager` | `infra/` directly |
| `agent_orchestration` | `agent/` engine, `services/llm`, `domain/chat` | `infra/` directly |
| `workflow_orchestration` | `workflow/` engine, `domain/knowledge`, `domain/intent` | `infra/` directly |

### 共享服务（不属于任何单一域）

| 服务 | 包 | 使用方 |
|------|------|--------|
| LLM Gateway | `services/llm/` | 所有域 |
| SSE Stream | `services/sse_stream/` | `chat`, `knowledge` |
| Context Manager | `services/context_manager.py` | `session`, `chat`, `agent` |
| Prompt Manager | `services/prompt_manager/` | 所有域 |
| Task Queue | `services/task_queue/` | `workflow_orchestration` |

[filled by work orders F05, F08, F09, F11–F17]