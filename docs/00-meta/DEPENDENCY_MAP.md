# 工单依赖速查

本文档是跨工单代码依赖和文档依赖的集中索引。执行工单前必须查阅本章确认前序依赖。

## 查询规则

- 表 1 列出的前序代码文件，必须读取确认实际字段/函数签名，不得凭记忆推断
- 表 2 列出的 docs 文件，必须全量读取后才能开始生成代码
- 表 3（TestNewHarness）为**可选**阶段 1 对照，**不**替代表 1/2，**禁止**整文件复制进本仓
- 若本工单编号未在表中出现，则无跨工单硬依赖，仅需读取工单自身阶段 1 列出的 docs

## Harness 文件（非工单依赖，但会话必查）

| 文件 | 用途 |
|------|------|
| `progress.md` | 当前阶段 `design` / `implement` / `maintain` |
| `feature_list.json` | 活跃 feature id 与 evidence |
| `init.sh` | 健康检查 |
| `docs/00-meta/FACT_REGISTRY.md` | 禁止猜测的事实清单 |
| `docs/00-meta/CHANGE_WORKFLOW.md` | 修改功能/接口流程 |
| `docs/00-meta/API_CHANGE_CHECKLIST.md` | 接口变更逐项勾选 |

---

## 表 1：跨工单代码依赖

| 工单 | 依赖的前序代码文件 |
|------|------------------|
| F02 | F01: app/main.py, app/core/config.py, app/core/di.py |
| F03 | F01: app/core/errors.py, app/core/response.py, app/core/context.py |
| F04 | F01: app/core/config.py; F03: app/core/errors.py, app/middleware/* |
| F05 | F02: app/infra/database.py, app/infra/redis_client.py |
| F06 | F03: app/core/response.py, app/core/constants.py |
| F07 | F02: app/infra/redis_client.py |
| F08 | F01: app/core/config.py |
| F09 | F02: app/infra/database.py, app/domain/*/repo.py |
| F10 | F01: app/core/di.py |
| F11 | F04: app/services/llm/gateway.py, F10: app/tools/registry.py |
| F12 | F11: app/agent/base.py, app/agent/state.py, app/agent/react.py |
| F13 | F10: app/tools/registry.py |
| F14 | F06: app/services/sse_stream.py, F09: app/services/context_manager.py, F04: app/services/llm/gateway.py |
| F15a | F05: app/infra/vector_store.py, F08: app/services/prompt_manager.py |
| F15b | F15a: app/domain/knowledge/service.py, F06: app/services/sse_stream.py |
| F15c | F15b: app/domain/knowledge/service.py, app/api/v1/knowledge.py |
| F16 | F04: app/services/llm/gateway.py, F08: app/services/prompt_manager.py |
| F17 | F08: app/services/prompt_manager.py |
| F18 | F03: app/core/logging.py, app/core/tracing.py, F04: app/services/llm/gateway.py |
| F19 | F11: app/agent/base.py, app/agent/state.py |
| F20 | F02: app/infra/redis_client.py, F03: app/middleware/exception.py |
| F21 | F01-F14, F15a, F15b, F15c, F16-F20 全部 |

---

## 表 2：跨 docs 事实依赖

| 工单 | 必读 docs |
|------|----------|
| F01 | ARCHITECTURE.md, docs/02-engineering/DI_CONTAINER.md, docs/02-engineering/BOOTSTRAP_SPEC.md |
| F02 | docs/01-architecture/DATA_MODEL.md, docs/02-engineering/PERSISTENCE_LAYER.md |
| F03 | docs/01-architecture/ERROR_CODE.md |
| F04 | docs/02-engineering/LLM_GATEWAY_SPEC.md, docs/01-architecture/ERROR_CODE.md |
| F05 | docs/04-kb/QDRANT_COLLECTION_CONFIG.md |
| F06 | docs/01-architecture/API_CONTRACT.md (SSE Event Protocol) |
| F07 | docs/02-engineering/PERSISTENCE_LAYER.md |
| F08 | docs/01-architecture/API_CONTRACT.md |
| F09 | docs/02-engineering/CONTEXT_MANAGEMENT_SPEC.md |
| F10 | docs/02-engineering/TOOLS_MCP_SPEC.md |
| F11 | docs/02-engineering/AGENT_SPEC.md |
| F12 | docs/02-engineering/AGENT_SPEC.md |
| F13 | docs/02-engineering/WORKFLOW_SPEC.md |
| F14 | docs/03-ai/CHAT_WORKFLOW_SPEC.md, docs/01-architecture/API_CONTRACT.md |
| F15a | docs/04-kb/QDRANT_COLLECTION_CONFIG.md, docs/03-ai/RAG_PIPELINE_SPEC.md (分块+元数据部分) |
| F15b | docs/03-ai/RAG_PIPELINE_SPEC.md (召回+rerank部分), docs/01-architecture/API_CONTRACT.md |
| F15c | docs/01-architecture/API_CONTRACT.md |
| F16 | docs/03-ai/INTENT_ROUTING_SPEC.md, docs/01-architecture/API_CONTRACT.md |
| F17 | docs/01-architecture/API_CONTRACT.md |
| F18 | ARCHITECTURE.md（可观测性部分） |
| F19 | docs/02-engineering/AGENT_SPEC.md (轨迹部分) |
| F20 | docs/02-engineering/SECURITY_POLICY.md |
| F21 | docs/02-engineering/DEPLOYMENT_GUIDE.md |

---

## 表 3：TestNewHarness 外部参考（可选 · 阶段 1 只读）

> **路径根目录**：`TestNewHarness/`（相对本模板仓库根目录的子目录，T0 产品 `maintain_t0`，非本仓实现源）  
> **权威仍为本仓**：`docs/01-architecture/API_CONTRACT.md` 等；与老项目冲突 **以本仓 docs 为准**。

### 使用规则

| 阶段 | 允许 | 禁止 |
|------|------|------|
| **1** | `read_file` 对照；输出「差异表」（路径/类名/契约/分层） | 写代码；把老项目当事实来源 |
| **2** | 按差异表**重写**算法步骤到本仓 §2.2 路径 | 复制整文件/整目录；`pip`/PYTHONPATH 引用 TestNewHarness |
| **3** | 在 evidence 注明「参考 TestNewHarness 某模块，已按契约改写」 | 未跑本仓 pytest 即标 passing |

阶段 1 差异表建议列：`老路径` | `新路径` | `契约差异` | `决策（重写/跳过）`。

### 工单 → 老项目对照（有则读，无则跳过）

| 工单 | TestNewHarness 可参考（只读） | 说明 |
|------|------------------------------|------|
| F02 | — | 老项目无等价 Alembic/PG 骨架时按 DATA_MODEL 新写 |
| F03 | `app/middleware/exception.py`, `trace.py`, `app/core/errors.py` | 错误类型需改为 `AppError` + 整数 code |
| F04 | `app/infra/model_gateway.py`, `circuit_breaker.py`, `semaphore_manager.py` | **须迁到** `app/services/llm/gateway.py`，禁止 api/domain 直连 |
| F05 | `app/infra/qdrant_client.py`, `app/domain/rag/*` | 路径改为 `infra/vector_store`；API 用 `/kb/*` 非 `/rag/retrieve` |
| F06 | `app/services/sse_stream.py` | 断连回调、`is_disconnected`；SSE error 用 `AI_%04d` |
| F07 | — | 老项目 ARQ 任务队列若无可跳过 |
| F08 | `app/prompts/loader.py`, `app/services/prompt_store.py` | 对齐 prompts/ 与版本策略 |
| F09 | — | 会话表在本仓 F02 新建后实现 |
| F10 | — | 老项目无通用 tools registry |
| F11 | — | 无 `app/agent/`；仅可参考编排思路 |
| F12 | — | 无多 Agent 引擎 |
| F13 | — | 无 Workflow DAG；读老项目 `TestNewHarness/docs/03-ai/ORCHESTRATION_SPEC.md` |
| F14 | `app/domain/chat/service.py`, `app/api/chat.py` | **勿**照搬路由；用 `/api/v1/chat`，勿复制 `/run` 进 chat 域 |
| F15a | `app/domain/knowledge/service.py` | 上传/分块；契约 `/kb/collections/...` |
| F15b | `app/domain/rag/service.py`, `retriever.py`, `retrieve.py` | 召回/rerank；能力 API 为 `/kb/query` |
| F15c | 上两者 + `app/api/knowledge.py`, `rag.py` | E2E 对照，按本仓 API 决策表拆职责 |
| F16 | `app/domain/intent/service.py` | 三层意图漏斗 |
| F17 | `app/domain/prompt_admin/service.py`, `app/api/prompt_admin.py` | 路径可能为 `/admin/prompts` vs 本仓契约，以 API_CONTRACT 为准 |
| F18 | `app/core/metrics.py`, `trace.py` | 指标与 trace |
| F19 | — | 评估框架新写 |
| F20 | `app/middleware/signature.py`（若有鉴权） | 对齐 SECURITY_POLICY |
| F21 | `docker-compose`、部署相关 docs | 去掉 vision/video 等产品依赖 |

### 老项目平台草案 docs（编排 /run 必读）

| 文件 | 用途 |
|------|------|
| `TestNewHarness/docs/03-ai/ORCHESTRATION_SPEC.md` | `/run` 编排语义 |
| `TestNewHarness/docs/01-architecture/API_CONTRACT_PLATFORM.md` | 平台 API v1 草案 |
| `TestNewHarness/docs/03-ai/SKILL_MODEL_SPEC.md` | skills/workflows 声明式模型 |
| `TestNewHarness/docs/00-meta/PLATFORM_TEMPLATE_PLAN.md` | Fork 保留/删除清单 |

### Harness / 联调文档（人类与 Agent）

| 文件 | 用途 |
|------|------|
| `TestNewHarness/使用说明.md` | maintain_t0 变更流程（勿重跑老工单 01–31） |
| `TestNewHarness/API_INTEGRATION_GUIDE.md` | 中台联调速查；细节仍以本仓 API_CONTRACT 为准 |
| `TestNewHarness/scripts/validate-harness.sh` | Harness 自检项借鉴 |

### 契约漂移速查（重写时必对）

| 项 | TestNewHarness（产品） | python-ai-template（本仓） |
|----|------------------------|----------------------------|
| 编排入口 | `/pc/agent` 等产品端点 | `POST /api/v1/run` |
| 检索 | `POST /api/v1/rag/retrieve` 等 | `POST /api/v1/kb/query` |
| 知识库 | `/knowledge/*` 等 | `/api/v1/kb/collections*` |
| LLM | `app/infra/model_gateway.py` | `app/services/llm/gateway.py` |
| 错误 | `BusinessException` 等 | `AppError`，REST 整数 / SSE `AI_%04d` |
| Agent/Workflow | 无通用引擎 | `app/agent/`, `app/workflow/`（F11–F13） |

### 明确不要参考（产品专用）

`app/domain/vision`, `video`, `pc_agent`；`app/api/vision`, `video`, `pc_agent`；眼镜/多模态专用 prompts 与 docs。

---

## 新功能开发时

添加新工单时，必须同步更新本文件：

1. 在表 1 添加新行，列出新工单依赖的前序代码文件
2. 在表 2 添加新行，列出必读 docs
3. 更新 `configs_work_orders/work_orders.yaml` 中的 dependencies 字段
4. 重新运行 `python scripts/generate_orders.py --orders-only`（仅改工单文案）或全量生成（会合并保留 `feature_list.json` 的 state/evidence）