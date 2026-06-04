# Agent 引擎规格

## 概述

Agent 引擎（`app/agent/`）是独立于业务领域的执行引擎。它提供基于状态机的 Agent 生命周期、ReAct（推理-行动）循环执行以及多 Agent 协作策略。领域层编排 Agent 执行；Agent 永不直接访问数据库。

## 状态机 — [filled by F11]

### Agent 状态

```
IDLE ──→ THINKING ──→ ACTING ──→ OBSERVING ──→ DONE
  │          │            │           │
  └──────────┴────────────┴───────────┘──→ ERROR
```

| 状态 | 描述 |
|------|------|
| IDLE | Agent 已初始化，等待首次输入 |
| THINKING | Agent 正在推理下一步行动（LLM 调用） |
| ACTING | Agent 正在执行工具调用 |
| OBSERVING | Agent 正在处理工具结果 |
| DONE | Agent 已生成最终回答 |
| ERROR | Agent 遇到不可恢复的错误 |

### 状态转换规则 — [filled by F11]

| 从 | 到 | 触发条件 |
|----|----|----------|
| IDLE | THINKING | 收到用户输入 |
| THINKING | ACTING | LLM 决定调用工具 |
| THINKING | DONE | LLM 生成最终回答 |
| ACTING | OBSERVING | 工具调用完成 |
| OBSERVING | THINKING | 观察结果反馈给 LLM |
| 任意 | ERROR | 不可恢复异常 |
| 任意 | IDLE | 触发重置 |

## ReAct 循环 — [filled by F11]

### 执行周期

```
1. 接收用户输入（或上一步观察结果）
2. THINKING：LLM 生成推理 + 行动计划
3. 若 action = tool_call：
   a. ACTING：通过注册表执行工具
   b. OBSERVING：记录工具结果
   c. 将观察结果追加后回到步骤 2
4. 若 action = final_answer：
   a. DONE：将回答返回给调用方
5. 若达到 max_iterations：
   a. DONE（附带截断通知）
```

### 轨迹记录 — [filled by F11]

每一步记录一个 `TrajectoryEntry`：

```python
class TrajectoryEntry:
    agent_name: str
    step_index: int
    state: AgentState
    thought: str          # LLM reasoning text
    action: ToolCall | None  # Tool specification
    observation: Any | None # Tool result
    token_usage: TokenUsage
    timestamp: datetime
```

轨迹通过 `domain/repo` 存储（Agent 永不直接写入数据库）。

### Prompt 模板 — [filled by F11]

ReAct prompt 遵循从 `prompts/agent/react_template.md` 加载的结构化格式：

```
System: [角色描述]
Available tools: [带签名的工具列表]

Thought: <推理过程>
Action: <tool_name>(<args>)
Observation: <tool_result>
... (重复)
Thought: <最终推理>
Final Answer: <回答>
```

## Agent 基类 — [filled by F11]

```python
class BaseAgent(ABC):
    name: str
    state: AgentState = AgentState.IDLE
    max_iterations: int = 10
    tools: list[str] = []     # Registered tool names

    async def run(self, input: str, context: dict) -> AgentResult:
        """Execute full ReAct loop."""

    @abstractmethod
    async def think(self, input: str, history: list) -> LLMResponse:
        """LLM reasoning step — must be implemented per agent."""

    async def act(self, tool_call: ToolCall) -> Any:
        """Execute a tool via the registry."""

    def observe(self, result: Any) -> str:
        """Format tool result for next reasoning step."""

    def should_continue(self) -> bool:
        """Check iteration limit and state."""
```

## 多 Agent 协作 — [filled by F12]

### 编排者模式

实现位于 `app/agent/orchestrator.py`。`OrchestratorAgent(BaseAgent)` 提供：

- `plan()` — 分解任务为 `SubTask` 列表（支持 LLM JSON 解析或 round-robin 降级）
- `delegate()` — 委派子任务给指定子 Agent，返回 `SubTaskResult`
- `synthesize()` — 汇总子 Agent 结果（支持 LLM 合成或拼接降级）
- `_run_loop()` — 完整生命周期：THINKING(plan) → [ACTING(delegate) → OBSERVING(result)]* → THINKING(synthesise) → DONE

数据模型：`SubTask`(frozen dataclass: task_id/description/agent_name/context)、`SubTaskResult`(frozen dataclass: task_id/agent_name/content/success/token_usage/trajectory)。

`max_sub_agents` 限制（默认 5，可配置于 `configs/agents.yaml` orchestrator 段）。

### 辩论策略 — [filled by F12]

`DebateStrategy` 实现于 `app/agent/orchestrator.py`：

- `rounds`（默认 3）——最大辩论轮数
- `consensus_threshold`（默认 0.8）——共识阈值
- `execute(proposer, critic, task_description)` — 执行 propose → critique → revise 循环
- 每轮从 critic 输出解析 `SCORE: X.X`，达到阈值即停止
- 返回 `DebateResult`（final_answer/rounds_completed/consensus_reached/history/total_token_usage）
- 历史由 `DebateRound`(round_index/proposal/critique/score) 列表组成

### 子 Agent 通信 — [filled by F12]

- 子 Agent 通过编排者通信（不直接 Agent 之间通信）
- 共享上下文由编排者维护（`SubTask.context` 传递）
- 每个子 Agent 拥有独立的轨迹记录（`SubTaskResult.trajectory`）
- 结果在编排者的最终回答中聚合（`synthesize()` 输出）
- 子 Agent 失败不阻塞编排——`delegate()` 捕获异常返回 `SubTaskResult(success=False)`

## 工具集成 — [filled by F11]

Agent 通过 `tools/registry` 使用工具：

```python
# Agent declares needed tools
class MyAgent(BaseAgent):
    tools = ["knowledge_search", "calculator"]

# Agent calls tool during ACTING phase
result = await tool_registry.call("knowledge_search", query="...")
```

Agent 永不实现工具逻辑——仅调用已注册的工具。

## 错误处理 — [filled by F11, F12]

| 场景 | 错误码 | 行为 |
|------|--------|------|
| 无效状态转换 | `7001 AGENT_STATE_INVALID` | 记录日志并重置为 IDLE |
| 工具未找到 | `7002 AGENT_TOOL_NOT_FOUND` | 报告给 LLM，继续 ReAct |
| LLM 调用失败 | `0004 TIMEOUT_ERROR` | 重试或中止 |
| 达到最大迭代次数 | `7004 AGENT_MAX_ITERATIONS` | 返回部分结果 |
| 不可恢复失败 | `7003 AGENT_EXECUTION_FAILED` | 转换为 ERROR 状态 |
| 多 Agent 编排失败 | `7005 AGENT_ORCHESTRATION_FAILED` | 编排逻辑异常时抛出（子 Agent 失败不触发，仅记录） |

## 并发 — [filled by F11, F12]

- 每次 Agent 执行在 LLM 信号量内运行
- 多 Agent 编排默认顺序执行子 Agent（`OrchestratorAgent._run_loop` 串行 delegate）
- 并行子 Agent 执行需要显式配置（F12 仅实现默认顺序执行）

[filled by work orders F11, F12]