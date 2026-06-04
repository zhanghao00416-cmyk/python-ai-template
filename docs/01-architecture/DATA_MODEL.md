# 数据模型

## 概述

本文档定义 Python AI Template 的数据库模型框架。主数据存储为 PostgreSQL（AsyncEngine + SQLAlchemy），通过 `infra/database.py` 的 BaseRepo 管理。Redis 用于缓存、限流和会话状态。Qdrant 用于向量存储。

## PostgreSQL 表

### sessions — [filled by F02]

存储聊天/对话会话。

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | 会话标识符 |
| user_id | VARCHAR(255) | 所属用户标识符 |
| title | VARCHAR(500) | 会话显示标题 |
| intent_type | VARCHAR(50) | 分类意图类型（qa/task/chat/retrieve_only） |
| model_config | JSONB | 该会话的模型配置 |
| created_at | TIMESTAMPTZ | 会话创建时间 |
| updated_at | TIMESTAMPTZ | 最后更新时间 |
| metadata | JSONB | 可扩展的会话元数据 |

### messages — [filled by F09]

存储会话中的单条消息。F09 实现 `app/domain/session/repo.py` 中的 `MessageRepo(BaseRepo[MessageModel])` 和 `app/domain/session/service.py` 中的 `SessionService`，提供消息追加、查询、更新和上下文窗口截断能力。

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | 消息标识符 |
| session_id | UUID (FK → sessions.id) | 所属会话 |
| role | VARCHAR(20) | 消息角色：user / assistant / system / tool |
| content | TEXT | 消息内容 |
| token_count | INTEGER | 用于上下文窗口管理的 Token 计数 |
| model_name | VARCHAR(100) | 生成时使用的 LLM 模型 |
| citations | JSONB | 来自 RAG 的引用参考 |
| tool_calls | JSONB | 工具调用请求（用于 agent 消息） |
| tool_results | JSONB | 工具调用结果（用于 tool 消息） |
| created_at | TIMESTAMPTZ | 消息创建时间 |
| metadata | JSONB | 可扩展的消息元数据 |

### tasks — [filled by F07]

存储 ARQ 任务队列的异步任务记录。

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | 任务标识符 |
| task_type | VARCHAR(50) | 任务类型：kb_upload / agent_run / workflow_run / batch_import / batch_eval / batch_embed / custom |
| status | VARCHAR(20) | 任务状态：pending / running / completed / failed |
| input_data | JSONB | 任务输入载荷 |
| output_data | JSONB | 任务结果载荷（完成时） |
| error_message | TEXT | 错误消息（失败时） |
| progress | FLOAT | 任务进度百分比（0.0–1.0） |
| callback_url | VARCHAR(2048) | 任务完成时回调 URL（可选） |
| created_at | TIMESTAMPTZ | 任务创建时间 |
| started_at | TIMESTAMPTZ | 任务开始时间 |
| completed_at | TIMESTAMPTZ | 任务完成时间 |
| user_id | VARCHAR(255) | 任务所有者 |
| metadata | JSONB | 可扩展的任务元数据 |

### agent_trajectories — [TBD: filled by F11, F12]

存储 Agent 执行轨迹，用于可观测性和评估。

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | 轨迹记录标识符 |
| session_id | UUID (FK → sessions.id) | 所属会话 |
| agent_name | VARCHAR(100) | Agent 标识符 |
| step_index | INTEGER | ReAct 循环中的步骤编号 |
| state | VARCHAR(30) | 该步骤的 Agent 状态（IDLE/THINKING/ACTING/OBSERVING/DONE） |
| thought | TEXT | Agent 的推理文本 |
| action | JSONB | 工具调用规格 |
| observation | JSONB | 工具调用结果 |
| token_usage | JSONB | Token 消耗记录 |
| created_at | TIMESTAMPTZ | 步骤时间戳 |

### prompt_templates — [filled by F08]

存储 Prompt 模板元数据和当前版本（实际内容从 `prompts/` 目录加载，修改写入 DB）。

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | 模板标识符 |
| name | VARCHAR(255, UNIQUE) | 模板名称（与文件名一致） |
| directory | VARCHAR(100) | 目录分组（如 agents、skills） |
| description | TEXT | 模板描述 |
| content | TEXT | 当前模板内容 |
| variables | JSONB | 自动提取的模板变量定义 |
| version | INTEGER | 当前版本号（自增） |
| baseline_content | TEXT | 来自 prompts/ 目录的原始内容 |
| baseline_version | INTEGER | 基线版本号 |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 最后修改时间 |

### prompt_template_versions — [filled by F08]

存储 Prompt 模板的版本历史，支持回滚到任意历史版本。

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | 版本记录标识符 |
| template_id | UUID (FK → prompt_templates.id) | 所属模板 |
| version | INTEGER | 版本号 |
| content | TEXT | 该版本的模板内容 |
| description | TEXT | 该版本的描述 |
| updated_by | VARCHAR(255) | 变更操作人 |
| created_at | TIMESTAMPTZ | 版本创建时间 |

## Redis 数据结构 — [filled by F02, F09]

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `rate_limit:{api_key}` | STRING (counter) | 可配置 | 限流计数器 |
| `session_ctx:{session_id}` | HASH | `ContextSettings.redis_cache_ttl`（默认 3600s） | 会话上下文缓存（F09：由 `ContextManager` 管理，消息追加时失效） |
| `task_status:{task_id}` | HASH | 任务 TTL | 异步任务状态 |

## Qdrant 集合 — [TBD: filled by F05]

详细的向量存储 Schema 见 `docs/04-kb/QDRANT_COLLECTION_CONFIG.md`。

## 实体关系

```
sessions 1──N messages
sessions 1──N agent_trajectories
sessions 1──N tasks (indirect, via task_type)
prompt_templates 1──N prompt_template_versions
```

## 迁移策略 — [filled by F02]

- 使用 Alembic 管理迁移
- 从 SQLAlchemy 模型自动生成迁移
- 修改数据模型的工单必须包含迁移

## 仓库访问模式

所有数据库访问通过继承自 `infra/database.py:BaseRepo` 的 `domain/*/repo.py` 进行：

```python
class BaseRepo:
    async def get_by_id(id)
    async def create(data)
    async def update(id, data)
    async def delete(id)
    async def list(filters, pagination)
```

领域代码不直接写原始 SQL；所有查询通过 repo 抽象层执行。

[filled by F05, F07, F08, F09; remaining: F11]