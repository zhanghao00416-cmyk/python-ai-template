# AGENTS.md — Python AI Template

## 0. 会话生命周期（每次必做）

### 0.1 启动顺序

编码或改 docs 前，按顺序执行：

1. 确认当前目录。
2. 读取 `progress.md` — 当前阶段、活跃工单、已验证状态。
3. 读取 `feature_list.json` — 选择**唯一** `in_progress` 或优先级最高的未完成项。
4. 读取 `session-handoff.md`（若存在且非空）— 上一轮交接。
5. 运行 `init.sh`（bash）或 `init.ps1`（PowerShell）— 环境 / Harness / docs 健康检查。
6. 读取 `docs/00-meta/FACT_REGISTRY.md` — 禁止凭记忆陈述的事实清单。
7. 读取 `ARCHITECTURE.md` + `docs/01-architecture/API_CONTRACT.md` + `docs/01-architecture/ERROR_CODE.md`。
8. 在回复**首段**输出「约束摘要」（≥5 条，必须来自已读文件）。

若 `init.sh` 失败：**先修 Harness 或基础环境**，不要在坏起点上叠新功能。

### 0.2 执行工单时额外读取

执行工单 FNN 时：

1. 查 `docs/00-meta/DEPENDENCY_MAP.md` 表 1–2（本仓依赖）。
2. **阶段 1**：读完工单列出的全部 docs + 前序代码，**禁止写代码**。
3. **阶段 2**：仅实现本工单范围。
4. **阶段 3**：对照 `evaluator-rubric.md` 自审 → 更新 `feature_list.json` + `progress.md`（**含下一任务**，见 §6.1）→ 填 `session-handoff.md`。

**硬规则：**

- 一次会话 / 一次 PR **只执行一条**工单。
- 禁止跨工单合并生成。
- 禁止跳过阶段 1→2→3。

### 0.3 文档 `[TBD: filled by Fxx]` 约定

- **不表示章节为空**：表示「该段落在工单 Fxx 阶段 2 实现、阶段 3 回填 docs」；章节内表格/字段/伪代码通常已可指导实现。
- **阶段 1**：以章节现有内容 + `DEPENDENCY_MAP` 为准，勿因 TBD 标题跳过阅读。
- **阶段 3**：本工单改动的契约须同步对应 doc，并将相关 `[TBD: filled by Fxx]` 改为 `[filled by Fxx]` 或删除 TBD 标记。

### 0.4 禁止行为

- **禁止**在完成 0.1/0.2 规定读取前写业务代码或改契约 docs。
- **禁止**凭记忆陈述 `FACT_REGISTRY.md` 中列出的任何事实；必须以文件为准。
- 发现记忆与文件不一致时，标记：**「事实修正：记忆 X → 文件实际 Y」**。
- **禁止**因「代码已写」就把 `feature_list.json` 标为 `passing`。
- **禁止**悄悄改弱验证规则或跳过 `init.sh`。
- **禁止**在 docs 与代码冲突时以代码为准（**docs 优先**，除非工单明确要求同步改 docs）。

### 0.5 上下文管理与工单拆分

- 单工单上下文占用超过 **50%** 时，拆分子任务或请求 Context Reset，并更新 `session-handoff.md`。
- 审核通过项只输出 ✓；失败项才展开（**沉默即成功**）。
- 工单代码产出超过 **500 行**或验证命令超过 **10 个测试文件**时，建议拆分为子工单（如 F15a/F15b/F15c），拆分后在 `工单/` 目录新建对应文件并更新 `work_orders.yaml`。
- 单工单连续 **3 轮对话**未完成时，强制写入 `session-handoff.md` 断点信息（阶段、已完成的步骤、未完成的原因），不要硬撑。

### 0.6 协议违反即回卷

以下任一情形，声明 **「协议违反，重置流程」** 并从 0.1 重来：

- 未输出约束摘要就写代码。
- 引用了未 `read_file` 的文件内容。
- 输出了 `FACT_REGISTRY` 中的事实但未从仓库文件确认。

### 0.7 变更流程

修改已有功能/接口时，**不要**口头描述修改；**必须**走变更单流程：

| 类型 | 代号 | 适用 | 模板 |
|------|------|------|------|
| 热修复 | `hotfix` | Bug、逻辑错误、单模块小改 | `templates/hotfix_template.md` |
| 接口变更 | `api-change` | 改路径/字段/错误码/SSE 事件 | `templates/api_change_template.md` |
| 功能变更 | `feature-change` | 跨多模块、新行为、域逻辑大改 | `templates/feature_change_template.md` |

详见 `docs/00-meta/CHANGE_WORKFLOW.md`。

**修改 passing 功能的代码 → 必须走变更单，禁止直接改。**

变更单编号规则：`变更工单/CO-NNN_描述.md`（NNN 从 001 递增），在 `progress.md` 变更历史段记录。

---

## 1. 项目身份

Python 自包含 AI 平台模板。脱离具体业务，提供 14 项可复用能力。

---

## 2. 事实来源层级

冲突时按此顺序裁决：

```
1. docs/01-architecture/API_CONTRACT.md
2. docs/01-architecture/ERROR_CODE.md
3. ARCHITECTURE.md
4. docs/01-architecture/DOMAIN_MAP.md
5. docs/02-engineering/*.md
6. docs/03-ai/*.md
7. docs/04-kb/QDRANT_COLLECTION_CONFIG.md
8. 当前 app/ 实现（仅当 docs 未覆盖时）
9. 工单 bullet（历史参考；与 docs 冲突以 docs 为准）
```

Harness 自身说明：`docs/00-meta/FACT_REGISTRY.md`。

---

## 3. 分层宪法（不可协商）

```
依赖方向（严格）：

api → domain → services → infra
api → schemas
api → tools（只注册调用，不实现工具逻辑）
domain → agent（编排调用引擎）
domain → workflow（编排调用引擎）
domain → tools（使用工具）
domain ← agent/workflow（域编排是调用者）
agent → tools（使用工具）
agent → services（使用 LLM/context 等服务）
workflow → tools
workflow → services
services → infra

core 全局共享，无方向限制。
schemas 由 api/domain 共享。

禁止：
  api 直连 infra
  domain 硬编码 prompt
  domain 直连 LLM provider（必须经 services/llm/gateway）
  绕过 model gateway 调模型
  agent 直接访问数据库（必须经 domain/repo）
  循环依赖
```

---

## 4. 功能状态规则

遵循 feature_list.json：

- 每次只激活一个 not_started 功能
- 不要因为"代码已经写了"就把功能标记为完成
- 功能验证命令通过才可标 passing
- passing 不可回退
- blocked 必须注明原因和阻塞工单编号
- 修改 passing 功能的代码 → 必须走变更流程（见 §0.7）
- 优先依赖仓库里的持久化文件（feature_list.json、progress.md、session-handoff.md），而不是聊天记录

---

## 5. 执行流程

1. 读 feature_list.json → 选下一个 not_started 功能
2. 读 session-handoff.md → Next 指针指向的工单
3. 读 docs/00-meta/DEPENDENCY_MAP.md → 确认前序依赖
4. 打开工单文件，按三段式执行：
   - **阶段1**：读工单「需要读的文件」，只读不写，输出差异与文件清单
   - **阶段2**：写代码（schemas → domain → services/infra → api + 测试）
   - **阶段3**：自审验证（对照契约、分层、错误码，发现问题直接修补）
5. 验证命令通过 → 更新 feature_list.json 状态为 passing + 写证据
6. 更新 session-handoff.md（Next 指向下一个工单）
7. 仓库处于安全状态后提交

如果基础验证一开始就失败，先修基础状态，不要在坏的起点上继续叠新功能。

---

## 6. 定义完成（Definition of Done）

功能或工单只有在**全部**满足时才算 `passing`：

1. 目标行为已实现（或 docs 已更新到位）。
2. `init.sh` 通过（含 `scripts/check-architecture.sh`）。
3. 工单阶段 3 自审完成，`evaluator-rubric.md` 无 Block 项。
4. 证据写入 `feature_list.json` 的 `evidence` 数组。
5. `progress.md` 已更新且 **§7.1 下一任务指针** 已写入；`session-handoff.md` 含下一会话开场白。
6. 架构规则未违反（见 §3）。
7. 若改 API / 错误码，**API_CONTRACT / ERROR_CODE 已同步**。

---

## 7. 会话收尾（每次结束前）

1. 更新 `progress.md`（**必须**含下一任务指针，§7.1）。
2. 更新 `feature_list.json`（状态 + evidence；同步下一项 `in_progress`）。
3. 填写 `session-handoff.md`（含 §11 下一会话开场白）。
4. 跑 `clean-state-checklist.md` 逐项确认。
5. 仅在安全可恢复时 commit；commit message 注明工单号或 feature id。

### 7.1 `progress.md` 自动续接规则（阶段 3 强制）

阶段 3 **必须**更新 `progress.md` 的「当前活跃任务」表，使**下一 session 人类无需改文件**即可开工。

**每次必须写入或更新：**

| 字段 | 规则 |
|------|------|
| `last_updated` | 当天日期 |
| `last_ticket` | 本 session 完成的工单路径或 feature id |
| `last_verified` | 一句话：本轮跑过的验证 |
| `active_feature_id` | 下一项 feature id（来自 `feature_list.json`） |
| `active_ticket` | 下一工单路径；无工单时写 `—` |
| `status` | 下一任务状态：`not_started`（新工单从阶段1）或 `in_progress`（本 session 未做完） |
| `goal` | 下一 session 第一件事（如「工单 F04 阶段1只读」） |

**禁止：** 阶段 3 结束时 `active_ticket` 仍指向**已完成**的工单且未给出下一任务。

---

## 8. 修改 vs 新建规则

| 场景 | 操作 |
|------|------|
| 修改 not_started 工单，改动 ≤ 30% | 修改原工单 |
| 修改 not_started 工单，改动 > 30% | 关闭原工单，新开工单 |
| 修改 active 工单 | 直接修改原工单 |
| 修改 passing 功能的代码 | **禁止**，必须走变更流程（见 §0.7） |
| 需求变更影响 passing 功能 | 走变更单（见 `docs/00-meta/CHANGE_WORKFLOW.md`） |
| 新增计划外功能 | 新开工单，编号递增 |

新业务必须先在 docs/ 下补齐事实文档，再写工单。更新工单后同步 `configs_work_orders/work_orders.yaml`，再运行 `python scripts/generate_orders.py --orders-only`（仅改文案）或全量生成（**会合并保留** `feature_list.json` 的 state/evidence，禁止在未备份时裸跑覆盖进度）。

---

## 9. 工程品质

每个生成的模块必须满足：

- async 优先
- 类型提示
- 结构化日志（structlog JSON 格式）
- 超时保护
- 异常包装
- 企业可读命名

避免演示风格代码。单文件保持可维护性和专注性。

---

## 10. 安全与稳定性

- API Key 认证（可配置关闭，预留 ENABLE_AUTH 开关）
- 外部依赖调用需超时
- LLM 推理需并发信号量保护
- SSE 流需断开检测和心跳
- 请求需 user_id / session_id / trace_id / request_id 传播
- 失败必须返回结构化业务错误码
- 不允许原始堆栈跟踪到客户端

---

## 11. 模型网关规则

双通道统一网关，提供者切换由配置驱动：

| 任务类型 | 默认通道 | 降级通道 |
|---------|---------|---------|
| 文本任务 | Qwen 云 API | 本地 vLLM |
| 多模态任务 | 配置指定 | 无 |

业务服务永远不直接绑定到一个提供者实现。stream=True/False 统一为一个方法，不拆两个。

---

## 12. 知识库规则

- 多集合支持，集合配置从 configs/default.yaml 加载
- 启动时自动创建声明的集合（含 payload 索引 + 稀疏向量索引）
- 支持动态创建/删除集合
- 类型/类别为可配置维度，不在代码中硬编码
- RAG 检索支持按集合/类型/类别多维过滤
- 仅支持 markdown 文档
- Prompt 文件位于 prompts/，运行时加载，不做热更

---

## 13. Agent / Workflow 规则

Agent 引擎和 Workflow 引擎独立于业务：

- agent/ 提供引擎能力（状态机 / ReAct / 协作策略）
- workflow/ 提供编排能力（StateGraph DAG / 条件边 / 并发节点）
- domain/ 负责业务编排，调用 agent 和 workflow 引擎
- Agent 轨迹（TrajectoryEntry）统一记录，接入评估框架
- Agent 状态枚举见 docs/01-architecture/ERROR_CODE.md，不在代码中硬编码

---

## 14. 仓库增长规则

添加新业务功能时：

- 优先添加新域包
- 尽可能保持网关抽象不变
- 避免修改不相关的稳定模块
- 保持分层

本仓库必须通过有界模块增长，而不是不受控制的文件扩展。

---

## 15. 快速导航

| 文件 | 用途 |
|------|------|
| `CLAUDE.md` | Claude Code 速查 |
| `progress.md` | 当前进度与活跃任务 |
| `feature_list.json` | 功能 / Harness 项状态 |
| `session-handoff.md` | 跨会话交接 |
| `init.sh` | 统一启动与健康检查 |
| `evaluator-rubric.md` | 阶段 3 自审 |
| `clean-state-checklist.md` | 收尾清单 |
| `docs/00-meta/FACT_REGISTRY.md` | 禁止猜测的事实 |
| `docs/00-meta/DEPENDENCY_MAP.md` | 工单依赖索引 |
| `docs/00-meta/CHANGE_WORKFLOW.md` | 修改功能/接口流程 |
| `docs/00-meta/API_CHANGE_CHECKLIST.md` | 接口变更逐项勾选 |
| `docs/00-meta/FEATURE_DEV_WORKFLOW.md` | 功能开发 4 步流程 |
| `docs/02-engineering/SSE_STREAM_SPEC.md` | SSE 事件协议规范 |
| `docs/02-engineering/CIRCUIT_BREAKER_SPEC.md` | 熔断器/信号量规范 |
| `docs/02-engineering/BOOTSTRAP_SPEC.md` | 启动编排规范 |