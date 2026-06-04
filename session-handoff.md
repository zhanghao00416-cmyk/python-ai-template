# 会话交接

> 每轮长会话结束前填写。新会话先读 `progress.md`，再读本文件。

## 当前已验证

- **明确可用**：
  - Harness 全套（AGENTS / progress / feature_list / FACT_REGISTRY / CHANGE_WORKFLOW / init）
  - 架构文档 25 个 `docs/**/*.md` + `ARCHITECTURE.md`
  - 工单系统 23 条（F15→F15a/b/c）+ 模板 + 生成脚本
  - configs（default.yaml + models.yaml + agents.yaml）
  - **F01 已 passing**：13/13 测试通过
  - **F02 已 passing**：42/42 测试通过（9 集成跳过需 PG/Redis）
  - **F03 已 passing**：49 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F04 已 passing**：51 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F05 已 passing**：52 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F06 已 passing**：32 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F07 已 passing**：47 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F08 已 passing**：46 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F09 已 passing**：57 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F10 已 passing**：64 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F11 已 passing**：64 单元测试通过；全量 504 passed；架构合规通过
- **F12 已 passing**：49 单元测试通过；全量 553 passed；架构合规 6/6
- F11 实现内容：
  - `app/agent/state.py`：AgentState 枚举（7 状态）+ 状态转换规则（含自循环）+ transition()
  - `app/agent/trajectory.py`：TokenUsage / ToolCall / TrajectoryEntry / AgentResult
  - `app/agent/base.py`：BaseAgent ABC（run/think/act/observe/should_continue）
  - `app/agent/react.py`：ReactAgent ReAct 循环（注入 think_fn、max_iterations、token 累积）
  - `app/schemas/agent.py`：AgentRunRequest/Response、TrajectoryStep/Detail
  - `app/domain/agent_orchestration/repo.py`：AgentTrajectoryRepo 持久化
  - `app/domain/agent_orchestration/service.py`：AgentOrchestrationService 业务编排
  - `app/api/v1/agent.py`：POST /agent/run + GET /agent/trajectories + GET /agent/trajectories/{task_id}
  - `prompts/agents/react_template.md`：ReAct prompt 模板
  - `tests/test_11_agent.py`：64 项测试
- **本轮跑过的验证**：
  - `pytest tests/` — 553 passed, 9 skipped
  - 架构合规测试通过

## 本轮改动（2026-06-04 F12）

- **F12 实现**：
  - 新建 `app/agent/orchestrator.py`（OrchestratorAgent + SubTask/SubTaskResult + DebateStrategy/DebateRound/DebateResult）
  - 修改 `app/agent/__init__.py`（导出 6 个新符号）
  - 修改 `app/domain/agent_orchestration/service.py`（_create_engine orchestrator 支持 + _build_sub_agents + _load_orchestrator_config）
  - 新建 `tests/test_12_multi_agent.py`（49 项测试）
  - 更新 `docs/02-engineering/AGENT_SPEC.md`（F11+F12 TBD→filled）
  - 更新 `evaluator-rubric.md`（F12 Accept 记录）
  - 更新 `feature_list.json`（F12→passing, F13→in_progress）
  - 更新 `progress.md`（F12 完成，下一 F13）

## 仍损坏或未验证

- **外部依赖**：PG/Redis/Qdrant 未实际运行（集成测试跳过，本地 `docker compose up` 后可验证）
- F12 scope 外的功能均 not_started（F13 已 in_progress）

## 下一步最佳动作

| 字段 | 值 |
|------|-----|
| **feature_id** | `F13` |
| **active_ticket** | `工单/F13_workflow_dag_engine.md` |
| **从哪开始** | 工单 F13 **阶段 1**（只读，禁止写代码） |
| **不要动** | 勿跳阶段；勿口头改功能（走变更单） |

## 下一会话开场白（上班复制这一条）

```text
按 AGENTS.md 0.1 启动，执行 progress.md 中的 active 任务（工单 F13 Workflow DAG 引擎）。
先运行 init.ps1，再读 FACT_REGISTRY、ARCHITECTURE、WORKFLOW_SPEC、DEPENDENCY_MAP。
严格阶段 1 只读，首段约束摘要 ≥5 条，输出阶段 1 交付物（含差异表）。
```

## 若要新加/改接口（备忘）

复制 `templates/` 对应变更模板，阶段 0 只写动机；Chat 加一句「我不知道涉及哪些文件，请阶段1定位」。

## 命令速查

人类上手见 **`使用手册.md`**；仓库入口 **`README.md`**。

```bash
cd /path/to/python-ai-template
bash init.sh          # Git Bash / WSL / Linux
```

```powershell
cd C:\path\to\python-ai-template
.\init.ps1            # Windows PowerShell（推荐）
```

## 活跃工单

| 工单 | 阶段 | 备注 |
|------|------|------|
| F01 项目骨架 | **passing** | 13/13 测试通过 |
| F02 数据库模型+Redis | **passing** | 42/42 测试通过，9 集成跳过 |
| F03 错误体系+中间件 | **passing** | 49 单元测试通过，架构 6/6 |
| F04 LLM Gateway | **passing** | 51 单元测试通过，架构 6/6 |
| F05 向量库+Qdrant | **passing** | 52 单元测试通过，架构 6/6 |
| F06 SSE 流式服务 | **passing** | 32 单元测试通过，架构 6/6 |
| F07 异步任务队列 | **passing** | 47 单元测试通过，架构 6/6 |
| F08 Prompt 管理器 | **passing** | 46 单元测试通过，架构 6/6 |
| F09 上下文管理器 | **passing** | 57 单元测试通过，架构 6/6 |
| F10 Tools 注册中心 | **passing** | 64 单元测试通过，架构 6/6 |
| F11 Agent 基类+状态机 | **passing** | 64 单元测试通过，全量 504 passed |
| F12 多 Agent 协作 | **passing** | 49 单元测试通过，全量 553 passed |
| F13 Workflow DAG 引擎 | **in_progress** | 下一 session 从阶段1开始 |