# Agent 引擎规格

## 概述

Agent 引擎（`app/agent/`）是独立于业务领域的执行引擎。它提供基于状态机的 Agent 生命周期、ReAct（推理-行动）循环执行以及多 Agent 协作策略。领域层编排 Agent 执行；Agent 永不直接访问数据库。

## 状态机 — [TBD: filled by F11]

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

### 状态转换规则 — [TBD: filled by F11]

| 从 | 到 | 触发条件 |
|----|----|----------|
| IDLE | THINKING | 收到用户输入 |
| THINKING | ACTING | LLM 决定调用工具 |
| THINKING | DONE | LLM 生成最终回答 |
| ACTING | OBSERVING | 工具调用完成 |
| OBSERVING | THINKING | 观察结果反馈给 LLM |
| 任意 | ERROR | 不可恢复异常 |
| 任意 | IDLE | 触发重置 |

## ReAct 循环 — [TBD: filled by F11]

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

### 轨迹记录 — [TBD: filled by F11]

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

### Prompt 模板 — [TBD: filled by F11]

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

## Agent 基类 — [TBD: filled by F11]

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

## 多 Agent 协作 — [TBD: filled by F12]

### 编排者模式

```python
class OrchestratorAgent(BaseAgent):
    """
    Coordinates multiple sub-agents to solve complex tasks.

    1. Decomposes task into sub-tasks
    2. Assigns sub-tasks to specialized agents
    3. Collects and synthesizes results
    """
    sub_agents: dict[str, BaseAgent]

    async def plan(self, input: str) -> list[SubTask]
    async def delegate(self, task: SubTask) -> AgentResult
    async def synthesize(self, results: list[AgentResult]) -> str
```

### 辩论策略 — [TBD: filled by F12]

```python
class DebateStrategy:
    """
    Multiple agents propose and critique solutions.

    1. Agent A proposes a solution
    2. Agent B critiques the solution
    3. Agent A revises based on critique
    4. Repeat for N rounds or until consensus
    """
    rounds: int = 3
    consensus_threshold: float = 0.8
```

### 子 Agent 通信 — [TBD: filled by F12]

- 子 Agent 通过编排者通信（不直接 Agent 之间通信）
- 共享上下文由编排者维护
- 每个子 Agent 拥有独立的轨迹记录
- 结果在编排者的最终回答中聚合

## 工具集成 — [TBD: filled by F11]

Agent 通过 `tools/registry` 使用工具：

```python
# Agent declares needed tools
class MyAgent(BaseAgent):
    tools = ["knowledge_search", "calculator"]

# Agent calls tool during ACTING phase
result = await tool_registry.call("knowledge_search", query="...")
```

Agent 永不实现工具逻辑——仅调用已注册的工具。

## 错误处理 — [TBD: filled by F11]

| 场景 | 错误码 | 行为 |
|------|--------|------|
| 无效状态转换 | `7001 AGENT_STATE_INVALID` | 记录日志并重置为 IDLE |
| 工具未找到 | `7002 AGENT_TOOL_NOT_FOUND` | 报告给 LLM，继续 ReAct |
| LLM 调用失败 | `0004 TIMEOUT_ERROR` | 重试或中止 |
| 达到最大迭代次数 | `7004 AGENT_MAX_ITERATIONS` | 返回部分结果 |
| 不可恢复失败 | `7003 AGENT_EXECUTION_FAILED` | 转换为 ERROR 状态 |

## 并发 — [TBD: filled by F11]

- 每次 Agent 执行在 LLM 信号量内运行
- 多 Agent 编排默认顺序执行子 Agent
- 并行子 Agent 执行需要显式配置

[TBD: filled by work orders F11, F12]