# Workflow 引擎规范

## 概述

Workflow 引擎（`app/workflow/`）提供基于 StateGraph 的 DAG 执行引擎，独立于业务领域。它同时支持编程式图构建和基于 YAML 的声明式工作流定义。

各领域定义工作流图；引擎通过节点函数、条件边、并发分支和状态管理来执行它们。

---

## 1. 两种工作流定义模式

| 模式 | 配置方式 | 适用场景 |
|------|----------|----------|
| **编程式** | Python `StateGraph` API | 复杂逻辑、自定义条件 |
| **声明式** | `workflows/*.yaml` | 标准流程、项目可定制 |

两种模式共享相同的执行引擎和状态管理。

---

## 2. YAML 声明式工作流

### 2.1 目录结构

```
workflows/
├── _schema.yaml          # Schema 文档
├── default.yaml          # 默认问答工作流
└── (项目特定工作流)
```

### 2.2 工作流 YAML 格式

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

### 2.3 步骤字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 工作流内唯一步骤标识符 |
| `agent` | 是 | 来自 `AgentRegistry` 的 Agent 名称（映射到 `prompts/agents/{name}.md`） |
| `skills` | 否 | 要装备的 Skill ID 列表（与 `tools` 取并集） |
| `tools` | 否 | 要装备的工具名称列表 |
| `when` | 否 | 条件表达式（阶段 3+） |

### 2.4 执行语义

| 阶段 | 支持 |
|------|------|
| 阶段 1 | 仅线性 `steps` |
| 阶段 2 | `when` 条件分支 |
| 阶段 3 | `parallel` 并发步骤、`llm_select` 技能执行 |

### 2.5 匹配规则

当 `POST /run` 收到请求时，编排器：

1. 通过 `IntentRouter` 分类意图
2. 将意图与所有 `workflows/*.yaml` 的 `match.intents` 进行匹配
3. 若无匹配则回退到 `default_qa`
4. 执行匹配的工作流步骤

---

## 3. 编程式 StateGraph — [filled by F13]

### 3.1 核心概念

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

### 3.2 节点函数

```python
async def node_function(state: StateSchema) -> dict:
    """
    A node receives the current state and returns a partial state update.
    Must be async. Returns only the fields to update.
    """
    return {"field_to_update": new_value}
```

### 3.3 边类型

| 类型 | 说明 |
|------|------|
| 固定边 | 无条件：A → B 始终执行 |
| 条件边 | 基于状态路由：A → condition(state) → B 或 C |

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

## 4. DAG 执行 — [filled by F13]

### 4.1 执行模型

1. 从输入初始化状态
2. 从 `entry_point` 节点开始（或第一个 YAML 步骤）
3. 执行节点函数 → 将结果合并到状态
4. 沿边推进（如有条件边则评估）
5. 若存在并行边，并发执行目标节点（受 `workflow.max_concurrent_nodes` 限制）
6. 重复直到到达终端节点
7. 返回最终状态

### 4.2 并行执行

```
        [A]
       / | \
     [B] [C] [D]   ← 并发执行
       \ | /
        [E]
```

所有并行分支必须完成后才能执行合并节点。

### 4.3 环路检测

- DAG 验证在图编译时运行
- 检测到环路时在执行前抛出 `WORKFLOW_CYCLE_DETECTED (8004)`
- 不允许运行时环路

---

## 5. Workflow 注册表

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

工作流在应用启动时从 `workflows/*.yaml` 和编程式注册中注册。

---

## 6. /run 编排流程

`POST /api/v1/run` 端点使用工作流引擎：

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

### 6.1 能力解析

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

### 6.2 /run 的 SSE 事件

| 事件 | 说明 |
|------|------|
| `start` | 流开始 |
| `route` | 选中的工作流（可选，可对客户端隐藏） |
| `agent` | Agent 步骤开始 |
| `tool` | 工具调用结果 |
| `citation` | RAG 引用来源 |
| `chunk` | 流式文本 |
| `heartbeat` | 保活（约 15 秒） |
| `done` | 流完成 |
| `error` | 错误，附带 AI_xxxx 错误码 |

注意：`structured`、`progress` 是业务特定的，不包含在默认模板 `/run` 中。`intent` 和 `usage` 事件按 API_CONTRACT.md 包含。

---

## 7. 错误处理

| 场景 | 错误码 | 行为 |
|------|--------|------|
| 节点未找到 | `8001 WORKFLOW_NODE_NOT_FOUND` | 工作流失败 |
| 无效边 | `8002 WORKFLOW_EDGE_INVALID` | 工作流失败 |
| 节点执行错误 | `8003 WORKFLOW_EXECUTION_FAILED` | 记录错误，标记任务失败 |
| 检测到环路 | `8004 WORKFLOW_CYCLE_DETECTED` | 编译时失败 |
| 无效状态转换 | `8005 WORKFLOW_STATE_ERROR` | 工作流失败 |
| 工作流未找到 | `2101 WORKFLOW_NOT_FOUND` | 回退到 `default_qa` |
| 技能未找到 | `7002 AGENT_TOOL_NOT_FOUND` | 步骤失败 |

---

## 8. 与领域的集成 — [filled by F13]

```python
# In domain/orchestration/service.py (F14+)
async def run_orchestration(request: RunRequest) -> AsyncGenerator[str, None]:
    workflow = registry.match(intent)
    async for event in engine.execute(workflow, context):
        yield event
```

工作流引擎不包含业务逻辑 — 它仅执行图节点。

---

## 9. 新项目定制

| 定制内容 | 位置 |
|----------|------|
| 工作流定义 | `workflows/*.yaml` |
| Agent 提示词 | `prompts/agents/*.md` |
| Skill 定义 | `skills/*.yaml` |
| Skill 提示词 | `prompts/skills/*.md` |
| 步骤级工具 | 添加到 `app/tools/` 并注册 |

**模板维护**：引擎代码（`StateGraph`、`WorkflowRegistry`、`WorkflowEngine`）
**项目定制**：YAML 定义、Agent 提示词、工具实现