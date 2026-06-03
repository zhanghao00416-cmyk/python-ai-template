# 工单 F11：Agent 基类 + 状态机 + ReAct 循环 + 三引擎（react/workflow/orchestrator）

## 元数据
- **id**: F11
- **state**: not_started
- **dependencies**: [F04, F10]
- **patches**: 无
- **supersedes**: 无
- **superseded-by**: 无

## 功能三元组
- **行为**：Agent 执行 3 步 tool/skill 调用，轨迹记录完整（IDLE→THINKING→ACTING→OBSERVING→DONE），支持 react/workflow/orchestrator 三种引擎
- **验证**：`pytest tests/test_11_agent.py`
- **状态**：not_started → active → passing

## 验收标准（全部通过才能标 passing）
- [ ] `pytest tests/test_11_agent.py` 通过
- [ ] 分层依赖检查通过（`scripts/check-architecture.sh` 或 Windows 等价流程）
- [ ] 相关测试通过（pytest）
- [ ] `feature_list.json` 状态 + evidence 已更新

## 关键约束
- 依赖方向严格遵守 `ARCHITECTURE.md`
- 错误码：`docs/01-architecture/ERROR_CODE.md`（REST 整数 code；SSE 用 `AI_%04d`）
- 主 API 选型：`API_CONTRACT.md`「API 选型决策表」（F14+ 业务域必读）
- Phase: Agent + Workflow
- `[TBD: filled by Fxx]` 见 `AGENTS.md` §0.3 — 不表示章节为空

## 不做（本工单范围外）
- 不做本功能三元组描述之外的事情
- 不修改已 passing 功能的代码（走 `docs/00-meta/CHANGE_WORKFLOW.md`）

---

## ━━━ 阶段 1：只读不写（禁止生成代码）━━━

### 1.1 前序代码依赖（必须 read_file）

- F04: `app/services/llm/gateway.py`
- F10: `app/tools/registry.py`

### 1.2 必读 docs（DEPENDENCY_MAP 表 2 + 工单列表）

- `docs/02-engineering/AGENT_SPEC.md`
- `docs/00-meta/DEPENDENCY_MAP.md`（本工单 F11 行）
- `ARCHITECTURE.md`（分层规则）

### 1.3 阶段 1 交付物

1. 与现有实现/契约的差异清单
2. 错误码与边界条件（引用 ERROR_CODE 表号）
3. 预计新增/修改文件清单（可与 §2.2 对照，允许阶段 1 微调）
4. 明确「不做」范围确认
5. （可选）`TestNewHarness/` 对照差异表 — 见 `docs/00-meta/DEPENDENCY_MAP.md` 表 3

### 1.4 可选外部参考（TestNewHarness）

- 路径：`TestNewHarness/`（本仓库子目录，**非** Python 依赖）
- 索引：`docs/00-meta/DEPENDENCY_MAP.md` **表 3**（工单 → 老项目只读路径）
- **阶段 1**：只读；**阶段 2**：按差异表重写，**禁止**整文件复制

**阶段 1 通过后才可进入阶段 2。**

---

## ━━━ 阶段 2：正式生成代码 ━━━

### 2.1 契约对齐（填写或确认）

| 项 | 约定 |
|----|------|
| 路由 / 能力 | （从 API_CONTRACT 或工单行为填写） |
| 响应 | JSON envelope / SSE（见 SSE_STREAM_SPEC） |
| 错误 | REST 整数 `code`；SSE `error` 用 `AI_%04d` |

### 2.2 实现清单（路径级）

| 路径 | 职责 |
|------|------|
| `app/schemas/` | 请求/响应模型（对齐 API_CONTRACT） |
| `app/domain/` | 领域 service + repo（如需持久化） |
| `app/services/` | 可复用服务（如需） |
| `app/infra/` | 外部依赖适配（如需） |
| `app/api/v1/` | 路由注册（无业务逻辑） |
| `tests/test_f11_*.py` | 工单验证测试 |

> 工单 YAML 未配置 `phase2_checklist` 时使用上表；阶段 1 须根据 docs 细化路径。

### 2.3 环境 / 命令

- 验证：`pytest tests/test_11_agent.py`
- 若依赖 PG/Redis/Qdrant：`docker compose up -d postgres redis`（按需）

---

## ━━━ 阶段 3：自审、验证、交接 ━━━

1. 对照 `evaluator-rubric.md` 自审（无 Block 项）
2. 契约与分层：`API_CONTRACT` / `ARCHITECTURE` / `check-architecture`
3. docs 同步：

- 本工单改动的 API/错误码/数据模型须同步对应 `docs/`（见 DEPENDENCY_MAP 表 2）
- 将相关 `[TBD: filled by Fxx]` 改为 `[filled by Fxx]`

4. 更新 `feature_list.json`（passing + evidence）、`progress.md`（§7.1 下一任务）、`session-handoff.md`

---

## ━━━ 执行指令（复制给代码工具）━━━

```text
按 AGENTS.md §0.1 启动；执行工单 F11，严格阶段 1→2→3。
阶段 1：读 DEPENDENCY_MAP F11 行 + 上文 docs + 前序代码，首段约束摘要 ≥5 条，输出 §1.3 交付物，禁止写代码。
阶段 2：仅实现 §2.2 清单；验证：pytest tests/test_11_agent.py
阶段 3：自审 + 更新 feature_list / progress / session-handoff
```

## ━━━ 执行指令结束 ━━━
