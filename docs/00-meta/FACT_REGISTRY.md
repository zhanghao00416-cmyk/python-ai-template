# 事实注册表（禁止凭记忆陈述）

Agent 在代码、docs、回复中涉及下列事实时，**必须先读取对应源文件**。源文件冲突时按 `AGENTS.md` §2 层级裁决。

**本表是索引，不是替代源文件。**

---

## 0. Harness 文档约定

### 0.1 `[TBD: filled by Fxx]` 标记

- **含义**：该段落由工单 Fxx 在阶段 2 实现、阶段 3 同步 docs；**不是**「内容缺失」。
- **阶段 1**：必须阅读 TBD 章节内已有表格/字段/示例，不得因标题跳过。
- **阶段 3**：实现后更新对应 doc，将 TBD 改为 `[filled by Fxx]` 或删除标记。

### 0.2 错误码双格式（见 `ERROR_CODE.md` § Canonical Format）

| 场景 | 格式 |
|------|------|
| REST JSON `code` | 整数，如 `2003`（成功 `0`） |
| SSE `error` 事件 `code` | 字符串 `AI_2003` |
| Python `AppError.code` | 整数 `2003` |

### 0.3 主 API 选型（见 `API_CONTRACT.md` 决策表）

- 编排对话 → `POST /api/v1/run`
- 纯聊天域 → `POST /api/v1/chat`
- 纯 RAG → `POST /api/v1/kb/query`
- 知识库 CRUD/上传 → `/api/v1/kb/collections*`

---

## 1. 源文件索引

| 事实类别 | 权威源文件 |
|----------|------------|
| API 路径、请求/响应字段、SSE 子集 | `docs/01-architecture/API_CONTRACT.md` |
| 错误码、HTTP 状态 | `docs/01-architecture/ERROR_CODE.md` |
| 分层、依赖方向、目录结构 | `ARCHITECTURE.md` |
| 数据模型、表结构 | `docs/01-architecture/DATA_MODEL.md` |
| 业务域边界 | `docs/01-architecture/DOMAIN_MAP.md` |
| 环境变量、部署 | `docs/02-engineering/DEPLOYMENT_GUIDE.md` |
| LLM Gateway 规范 | `docs/02-engineering/LLM_GATEWAY_SPEC.md` |
| Agent / Workflow 规范 | `docs/02-engineering/AGENT_SPEC.md`、`WORKFLOW_SPEC.md` |
| SSE 流式规范 | `docs/02-engineering/SSE_STREAM_SPEC.md` |
| 熔断器 / 信号量 | `docs/02-engineering/CIRCUIT_BREAKER_SPEC.md` |
| 启动编排 | `docs/02-engineering/BOOTSTRAP_SPEC.md` |
| RAG / 意图 / 对话流程 | `docs/03-ai/*.md` |
| 向量库配置 | `docs/04-kb/QDRANT_COLLECTION_CONFIG.md` |
| 老项目对照索引（可选） | `docs/00-meta/DEPENDENCY_MAP.md` 表 3 TestNewHarness |

---

## 2. 高频易错事实（必须以文件为准）

> 下列为**常见考点**，具体取值、边界、例外以源文件为准；勿把本表当最终契约。

### 2.1 全局

| 项 | 核验要点 |
|----|----------|
| API 前缀 | `/api/v1` |
| 追踪字段 | `user_id`、`session_id`、`trace_id`、`request_id`（body + contextvars） |
| 配置优先级 | `/run/secrets` → `.env`/环境变量 → override.yaml → default.yaml（见 `secrets/README.md`） |
| DI 容器 | `app/core/di.py`（register/resolve/override），`app/api/deps.py` 桥接 FastAPI Depends |
| 认证开关 | `security.enable_auth`（默认 true，开发可 false） |

### 2.2 SSE 事件

| 项 | 核验要点 |
|----|----------|
| 通用 8 种 | `start` / `intent` / `chunk` / `structured` / `citation` / `heartbeat` / `progress` / `usage` |
| 终止 2 种 | `done` / `error` |
| heartbeat 周期 | `sse.heartbeat_interval`（默认 15s） |
| 事件顺序 | `start` 总是第一个；`done` 或 `error` 总是最后一个 |

### 2.3 模型网关

| 项 | 核验要点 |
|----|----------|
| 按任务分流 | `configs/models.yaml` routing 段：intent/rag_rewrite/rag_merge/final/chat/multimodal/embedding |
| 双通道 | qwen_cloud（默认）/ vllm（本地降级） |
| stream 统一 | gateway 一个方法同时支持 stream=True/False |
| 熔断器 | 每个通道独立：llm_text / llm_vllm / multimodal / embedding |

### 2.4 知识库

| 项 | 核验要点 |
|----|----------|
| 默认集合 | `general` + `safety`（configs/default.yaml 配置） |
| 集合配置来源 | `configs/default.yaml` qdrant.collections |
| 仅支持格式 | markdown |
| 文档3元数据 | `doc_type`(类型) / `source`(来源) / `tag`(标签) |
| 分块策略 | fixed_overlap / delimiter_max / semantic / paragraph |
| 父子分块 | enable_parent_child 通用选项；父分块固定 fixed_overlap；子命中→返回父上下文 |
| 召回策略 | keyword / similarity / hybrid / rrf |
| RAG 检索过滤 | 按集合/doc_type/source/tag/uploader 多维过滤 |
| 父子分块检索 | 匹配子分块 → parent_id 查父分块 → 返回父上下文 + 子定位 |

### 2.5 Agent / Workflow

| 项 | 核验要点 |
|----|----------|
| Agent 状态 | IDLE / THINKING / ACTING / OBSERVING / DONE / ERROR |
| Agent 引擎位置 | `app/agent/`（独立于业务域） |
| Workflow 引擎位置 | `app/workflow/`（StateGraph DAG） |
| 轨迹记录 | TrajectoryEntry，接入评估框架 |

---

## 3. 变更流程

1. 先改权威源文件（通常 `API_CONTRACT` / `ERROR_CODE`）。
2. 再改本表索引（若仍适用）。
3. 同步 `DOMAIN_MAP.md`。
4. 若影响实现，新建/更新工单 + `DEPENDENCY_MAP`。
5. 在 `progress.md` 记录「事实变更」摘要。

---

## 4. Agent 自检

输出涉及上表任一项前，自问：

- [ ] 我是否已读取对应源文件？
- [ ] 约束摘要是否引用了实际读到的内容？
- [ ] 若与记忆不符，是否标记「事实修正」？