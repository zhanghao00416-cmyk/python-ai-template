# 功能开发流程

本文档定义新功能从讨论到交付的标准流程。

---

## 四步流程

```
讨论对齐 → 更新 docs → 新建工单 → 阶段 1→2→3 写代码
```

| 步骤 | 做什么 | 交付物 |
|------|--------|--------|
| 1. 讨论 | 明确边界、API/SSE/错误码 | 讨论结论：做什么、不做什么 |
| 2. 改 docs | 把结论写成事实来源 | 更新 `docs/` 对应文件 |
| 3. 建工单 | 拆成可执行单元 | 工单文件 + `DEPENDENCY_MAP.md` 更新 |
| 4. 写代码 | 严格三段式 | 代码 + 测试 + 自审 + 评审 |

**原则**：一次会话/一次 PR **只执行一条**工单。

**文档 TBD**：`[TBD: filled by Fxx]` 表示实现回填责任，不表示章节无内容（见 `AGENTS.md` §0.3、`FACT_REGISTRY.md` §0）。

**主 API 选型**：实现业务域前必读 `API_CONTRACT.md` 内「API 选型决策表」，避免 `/run` 与 `/chat`/`/kb/query` 职责混用。

**外部参考**：子目录 `TestNewHarness/`（T0 产品）见 `DEPENDENCY_MAP.md` 表 3；阶段 1 只读对照，阶段 2 按本仓 docs 重写。

---

## 修改已有功能

**新功能**用本流程；**修改已有功能/接口**用 `docs/00-meta/CHANGE_WORKFLOW.md`。

三种变更类型：

| 类型 | 代号 | 模板 |
|------|------|------|
| 热修复 | `hotfix` | `templates/hotfix_template.md` |
| 接口变更 | `api-change` | `templates/api_change_template.md` |
| 功能变更 | `feature-change` | `templates/feature_change_template.md` |

修改 passing 功能的代码 **禁止**直接改，必须走变更流程。

---

## 讨论阶段必对齐的 5 个问题

1. **系统边界**：这个功能属于哪一层？（api / domain / services / infra / agent / workflow / tools）
2. **对外契约**：新路由还是改现有？JSON 还是 SSE？
3. **默认值与限制**：top_k、超时、集合名等
4. **错误策略**：失败返回哪个 AI_xxxx
5. **非目标**：明确不做的事

讨论结论必须写入 docs，避免代码阶段反复猜测。

---

## 按影响面选择 docs

| 变更类型 | 必读/必改 docs |
|----------|----------------|
| 新 API / 改字段 | `API_CONTRACT.md` + `ERROR_CODE.md` + `DOMAIN_MAP.md` |
| RAG / 检索 | `RAG_PIPELINE_SPEC.md` + `QDRANT_COLLECTION_CONFIG.md` |
| Agent / Workflow | `AGENT_SPEC.md` + `WORKFLOW_SPEC.md` |
| Prompt / 模型 | `docs/03-ai/*` + `prompts/` |
| 数据模型 | `DATA_MODEL.md` + `PERSISTENCE_LAYER.md` |
| 纯内部重构 | 可跳过 API_CONTRACT，仍建议简短工单 + 测试 |

---

## 工单三段式

- **阶段 1**：读 DEPENDENCY_MAP、必读 docs、前序代码 → 输出差异与文件清单 → **禁止写代码**
- **阶段 2**：schemas → domain → services/infra → api + 测试
- **阶段 3**：对照契约自审，输出修改文件清单 + 评审评分

给 Agent 的指令示例：

```text
执行工单 F04：LLM Gateway（策略模式），严格阶段 1→2→3；
先读 AGENTS.md、feature_list.json、DEPENDENCY_MAP 工单 F04 行。
```

---

## 何时可简化

| 场景 | 是否仍需 docs + 工单 |
|------|---------------------|
| 新 API / 改字段 / 新错误码 | **必须** docs + 工单 |
| 纯 bugfix、契约不变 | 可简化工单，需测试复现 |
| 新增 Agent/Workflow | **必须** 先定 AGENT_SPEC / WORKFLOW_SPEC |