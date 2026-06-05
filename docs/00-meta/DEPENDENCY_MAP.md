# 工单依赖速查

本文档是跨工单代码依赖和文档依赖的集中索引。执行工单前必须查阅本章确认前序依赖。

## 查询规则

- 表 1 列出的前序代码文件，必须读取确认实际字段/函数签名，不得凭记忆推断
- 表 2 列出的 docs 文件，必须全量读取后才能开始生成代码
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

## 新功能开发时

添加新工单时，必须同步更新本文件：

1. 在表 1 添加新行，列出新工单依赖的前序代码文件
2. 在表 2 添加新行，列出必读 docs
3. 更新 `configs_work_orders/work_orders.yaml` 中的 dependencies 字段
4. 重新运行 `python scripts/generate_orders.py --orders-only`（仅改工单文案）或全量生成（会合并保留 `feature_list.json` 的 state/evidence）