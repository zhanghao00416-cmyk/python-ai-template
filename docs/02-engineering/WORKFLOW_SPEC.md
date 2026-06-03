# Workflow Engine Specification

## Overview

The Workflow engine (`app/workflow/`) provides a StateGraph-based DAG execution engine independent of business domains. It supports both programmatic graph construction and YAML-based declarative workflow definitions.

Domains define workflow graphs; the engine executes them with node functions, conditional edges, concurrent branches, and state management.

---

## 1. Two Workflow Definition Modes

| Mode | Configuration | Use Case |
|------|---------------|----------|
| **Programmatic** | Python `StateGraph` API | Complex logic, custom conditions |
| **Declarative** | `workflows/*.yaml` | Standard flows, project-customizable |

Both modes share the same execution engine and state management.

---

## 2. YAML Declarative Workflow

### 2.1 Directory Structure

```
workflows/
├── _schema.yaml          # Schema documentation
├── default.yaml          # Default Q&A workflow
└── (project-specific workflows)
```

### 2.2 Workflow YAML Format

```yaml
# workflows/default.yaml
id: default_qa
description: "General Q&A with optional knowledge retrieval"

match:
  intents:
    - qa
    - chat
    - task

steps:
  - id: policy
    agent: planner
    skills: []
    tools: []

  - id: retrieve
    agent: researcher
    skills:
      - rag_answer
    tools: []
    when: "{{ steps.policy.need_rag }}"

  - id: answer
    agent: synthesizer
    skills: []
    tools: []
```

### 2.3 Step Fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique step identifier within workflow |
| `agent` | Yes | Agent name from `AgentRegistry` (maps to `prompts/agents/{name}.md`) |
| `skills` | No | List of Skill IDs to equip (union with `tools`) |
| `tools` | No | List of bare Tool names to equip |
| `when` | No | Conditional expression (Phase 3+) |

### 2.4 Execution Semantics

| Phase | Supports |
|-------|----------|
| Phase 1 | Linear `steps` only |
| Phase 2 | `when` conditional branching |
| Phase 3 | `parallel` concurrent steps, `llm_select` skill execution |

### 2.5 Match Rules

When `POST /run` receives a request, the orchestrator:

1. Classifies intent via `IntentRouter`
2. Matches intent against all `workflows/*.yaml` `match.intents`
3. Falls back to `default_qa` if no match
4. Executes matched workflow steps

---

## 3. Programmatic StateGraph — [TBD: filled by F13]

### 3.1 Core Concepts

```python
class StateGraph:
    """
    Directed Acyclic Graph where:
    - Nodes are functions that transform state
    - Edges define execution order (with optional conditions)
    - State is a TypedDict passed between nodes
    """
    nodes: dict[str, NodeFunction]
    edges: list[Edge]
    conditional_edges: dict[str, ConditionalEdge]
    entry_point: str
    state_schema: type[TypedDict]
```

### 3.2 Node Function

```python
async def node_function(state: StateSchema) -> dict:
    """
    A node receives the current state and returns a partial state update.
    Must be async. Returns only the fields to update.
    """
    return {"field_to_update": new_value}
```

### 3.3 Edge Types

| Type | Description |
|------|-------------|
| Fixed edge | Unconditional: A → B always |
| Conditional edge | Route based on state: A → condition(state) → B or C |

```python
def route_intent(state) -> str:
    if state["intent"] == "qa":
        return "knowledge_node"
    elif state["intent"] == "chat":
        return "chat_node"
    else:
        return "fallback_node"
```

---

## 4. DAG Execution — [TBD: filled by F13]

### 4.1 Execution Model

1. Initialize state from input
2. Start at `entry_point` node (or first YAML step)
3. Execute node function → merge result into state
4. Follow edges (evaluate conditional edges if present)
5. If parallel edges exist, execute target nodes concurrently (bounded by `workflow.max_concurrent_nodes`)
6. Repeat until reaching a terminal node
7. Return final state

### 4.2 Parallel Execution

```
       [A]
      / | \
    [B] [C] [D]   ← executed in parallel
      \ | /
       [E]
```

All parallel branches must complete before merging nodes execute.

### 4.3 Cycle Detection

- DAG validation runs at graph compilation time
- Cycles raise `WORKFLOW_CYCLE_DETECTED (8004)` before execution
- No runtime cycles are permitted

---

## 5. Workflow Registry

```python
class WorkflowRegistry:
    def __init__(self):
        self._workflows: dict[str, CompiledWorkflow] = {}

    def register(self, name: str, graph: StateGraph) -> None:
        """Register a compiled workflow."""

    def register_from_yaml(self, path: str) -> None:
        """Load and register a YAML-defined workflow."""

    def get(self, name: str) -> CompiledWorkflow:
        """Retrieve a compiled workflow."""

    def match(self, intent: str) -> CompiledWorkflow:
        """Match intent to a workflow (falls back to default_qa)."""

    def list_workflows(self) -> list[str]:
        """List all registered workflow names."""
```

Workflows are registered at application startup from both `workflows/*.yaml` and programmatic registration.

---

## 6. /run Orchestration Flow

The `POST /api/v1/run` endpoint uses the workflow engine:

```
RunRequest
  → SessionStore.load(session_id)
  → IntentRouter.classify(query, session)
  → WorkflowRegistry.match(intent) → workflow_id
  → WorkflowEngine.run(workflow_id, ctx):
        for step in steps:
          agent = AgentRegistry.get(step.agent)
          capabilities = resolve_capabilities(step, agent)
          yield SSE start/agent/chunk/citation/heartbeat/done/error
          ctx.merge(agent output)
  → SessionStore.save(session_id, summary)
  → yield done
```

### 6.1 Capabilities Resolution

```python
def resolve_capabilities(step, agent) -> set[str]:
    tool_names = set()
    for skill_id in step.skills:
        skill = SkillRegistry.get(skill_id)
        tool_names |= set(skill.tools)
    tool_names |= set(step.tools)
    tool_names |= set(agent.default_tools)
    return tool_names
```

### 6.2 SSE Events for /run

| Event | Description |
|-------|-------------|
| `start` | Stream begins |
| `route` | Selected workflow (optional, can hide from client) |
| `agent` | Agent step begins |
| `tool` | Tool call result |
| `citation` | RAG reference sources |
| `chunk` | Streaming text |
| `heartbeat` | Keep-alive (~15s) |
| `done` | Stream complete |
| `error` | Error with AI_xxxx code |

Note: `structured`, `progress` are business-specific and not included in the default template `/run`. `intent` and `usage` events are included per API_CONTRACT.md.

---

## 7. Error Handling

| Scenario | Error Code | Behavior |
|----------|-----------|----------|
| Node not found | `8001 WORKFLOW_NODE_NOT_FOUND` | Fail workflow |
| Invalid edge | `8002 WORKFLOW_EDGE_INVALID` | Fail workflow |
| Node execution error | `8003 WORKFLOW_EXECUTION_FAILED` | Record error, mark task failed |
| Cycle detected | `8004 WORKFLOW_CYCLE_DETECTED` | Fail at compile time |
| Invalid state transition | `8005 WORKFLOW_STATE_ERROR` | Fail workflow |
| Workflow not found | `2101 WORKFLOW_NOT_FOUND` | Fall back to `default_qa` |
| Skill not found | `7002 AGENT_TOOL_NOT_FOUND` | Fail step |

---

## 8. Integration with Domain — [TBD: filled by F13]

```python
# In domain/orchestration/service.py (F14+)
async def run_orchestration(request: RunRequest) -> AsyncGenerator[str, None]:
    workflow = registry.match(intent)
    async for event in engine.execute(workflow, context):
        yield event
```

The workflow engine never contains business logic — it only executes graph nodes.

---

## 9. New Project Customization

| What to customize | Where |
|-------------------|-------|
| Workflow definitions | `workflows/*.yaml` |
| Agent prompts | `prompts/agents/*.md` |
| Skill definitions | `skills/*.yaml` |
| Skill prompts | `prompts/skills/*.md` |
| Step-level tools | Add to `app/tools/` + register |

**Template-maintained**: Engine code (`StateGraph`, `WorkflowRegistry`, `WorkflowEngine`)
**Project-customized**: YAML definitions, agent prompts, tool implementations