# Agent Engine Specification

## Overview

The Agent engine (`app/agent/`) is an independent execution engine separate from business domains. It provides state-machine-based agent lifecycle, ReAct (Reason-Act) loop execution, and multi-agent collaboration strategies. Domain layers orchestrate agent execution; agents never access the database directly.

## State Machine — [TBD: filled by F11]

### Agent States

```
IDLE ──→ THINKING ──→ ACTING ──→ OBSERVING ──→ DONE
  │          │            │           │
  └──────────┴────────────┴───────────┘──→ ERROR
```

| State | Description |
|-------|-------------|
| IDLE | Agent initialized, awaiting first input |
| THINKING | Agent reasoning about next action (LLM call) |
| ACTING | Agent executing a tool call |
| OBSERVING | Agent processing tool result |
| DONE | Agent has produced final answer |
| ERROR | Agent encountered unrecoverable error |

### State Transition Rules — [TBD: filled by F11]

| From | To | Trigger |
|------|----|---------|
| IDLE | THINKING | User input received |
| THINKING | ACTING | LLM decides to call a tool |
| THINKING | DONE | LLM produces final answer |
| ACTING | OBSERVING | Tool call completed |
| OBSERVING | THINKING | Observation fed back to LLM |
| Any | ERROR | Unrecoverable exception |
| Any | IDLE | Reset triggered |

## ReAct Loop — [TBD: filled by F11]

### Execution Cycle

```
1. Receive user input (or previous observation)
2. THINKING: LLM generates reasoning + action plan
3. If action = tool_call:
   a. ACTING: Execute tool via registry
   b. OBSERVING: Record tool result
   c. Go to step 2 with observation appended
4. If action = final_answer:
   a. DONE: Return answer to caller
5. If max_iterations reached:
   a. DONE (with truncation notice)
```

### Trajectory Recording — [TBD: filled by F11]

Every step records a `TrajectoryEntry`:

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

Trajectories are stored via `domain/repo` (agent never writes to DB directly).

### Prompt Template — [TBD: filled by F11]

The ReAct prompt follows a structured format loaded from `prompts/agent/react_template.md`:

```
System: [role description]
Available tools: [tool list with signatures]

Thought: <reasoning>
Action: <tool_name>(<args>)
Observation: <tool_result>
... (repeat)
Thought: <final reasoning>
Final Answer: <answer>
```

## Agent Base Class — [TBD: filled by F11]

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

## Multi-Agent Collaboration — [TBD: filled by F12]

### Orchestrator Pattern

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

### Debate Strategy — [TBD: filled by F12]

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

### Sub-Agent Communication — [TBD: filled by F12]

- Sub-agents communicate through the orchestrator (no direct agent-to-agent)
- Shared context is maintained in the orchestrator
- Each sub-agent has its own trajectory record
- Results are aggregated in the orchestrator's final answer

## Tool Integration — [TBD: filled by F11]

Agents use tools through the `tools/registry`:

```python
# Agent declares needed tools
class MyAgent(BaseAgent):
    tools = ["knowledge_search", "calculator"]

# Agent calls tool during ACTING phase
result = await tool_registry.call("knowledge_search", query="...")
```

Agents never implement tool logic — they only invoke registered tools.

## Error Handling — [TBD: filled by F11]

| Scenario | Error Code | Behavior |
|----------|-----------|----------|
| Invalid state transition | `7001 AGENT_STATE_INVALID` | Log and reset to IDLE |
| Tool not found | `7002 AGENT_TOOL_NOT_FOUND` | Report to LLM, continue ReAct |
| LLM call fails | `0004 TIMEOUT_ERROR` | Retry or abort |
| Max iterations | `7004 AGENT_MAX_ITERATIONS` | Return partial result |
| Unrecoverable failure | `7003 AGENT_EXECUTION_FAILED` | Transition to ERROR |

## Concurrency — [TBD: filled by F11]

- Each agent execution runs within the LLM semaphore
- Multi-agent orchestration runs sub-agents sequentially by default
- Parallel sub-agent execution requires explicit config

[TBD: filled by work orders F11, F12]