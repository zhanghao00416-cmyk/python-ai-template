# 工具 / 技能 / MCP 规范

## 概述

工具层提供**三层能力模型**：Tool（原子工具）、Skill（可组合技能）和 MCP（外部协议适配）。此模型取代了之前扁平的 `@tool/@skill` 装饰器模型，通过更清晰的分层同时支持编程式注册和基于 YAML 的声明式定义。

---

## 1. 三层能力模型

| 概念 | 定义 | 配置位置 | 代码位置 |
|------|------|----------|----------|
| **Tool** | 原子可执行能力（单次 IO/函数调用） | 编程式注册 | `app/tools/` |
| **Skill** | 可组合技能包：提示词 + 绑定工具 + 可选知识库范围 + 可选固定子流程 | `skills/*.yaml` + `prompts/skills/*.md` | `app/domain/skills/` |
| **MCP** | 外部工具协议适配器 | `configs/default.yaml` mcp_servers | `app/tools/mcp_adapter.py` |

### 1.1 Tool

Tool 是一个带有类型化参数的单个异步函数。没有子流程，没有提示词。

```python
# app/tools/retrieve_knowledge.py
from app.tools.registry import tool

@tool(name="retrieve_knowledge", description="Search knowledge base for relevant documents")
async def retrieve_knowledge(query: str, collection: str | None = None,
                               payload_filters: dict | None = None,
                               top_k: int = 3) -> list[dict]:
    """Retrieve documents from Qdrant vector store."""
    ...
```

### 1.2 Skill

Skill 将提示词、绑定工具和可选约束打包为一个可复用的技能包。Skill 通过 YAML 声明并在启动时加载。

```yaml
# skills/rag_answer.yaml
id: rag_answer
description: "Retrieve from knowledge base and generate grounded answer"
prompt: prompts/skills/rag_answer.md
tools:
  - retrieve_knowledge
kb_scope:
  collection: null
  filter: {}
constraints:
  max_citations: 3
execution: fixed
```

| 字段 | 说明 |
|------|------|
| `id` | 唯一的技能标识符 |
| `description` | 用于注册列表的单行描述 |
| `prompt` | 提示词文件路径（相对于项目根目录） |
| `tools` | 本技能授权使用的 Tool 名称列表 |
| `kb_scope` | 可选的知识库过滤默认值（null = 从请求中继承） |
| `constraints` | 可选的执行约束（max_citations、timeout 等） |
| `execution` | `fixed`（阶段 1）或 `llm_select`（阶段 3+） |

### 1.3 Step 能力并集

当工作流步骤同时引用 skill 和 tool 时，**可见能力集合**为并集：

```
step_capabilities = skill_tools ∪ step.tools ∪ agent.default_tools
```

这意味着：
- 步骤可以**仅使用 tool**（无 skill 提示词）
- 步骤可以**仅使用 skill**（skill 提供提示词和工具）
- 步骤可以**同时使用两者**（skill 提示词 + 额外裸工具）

---

## 2. Tool 注册表 — [TBD: filled by F10]

### 注册 API

```python
class ToolRegistry:
    def register(self, name: str, fn: Callable, description: str = "",
                 category: str = "tool", timeout: float = 30.0) -> None:
        """Register a tool, skill function, or MCP proxy."""

    def get(self, name: str) -> ToolDefinition:
        """Retrieve a tool by name."""

    def list_tools(self, category: str | None = None) -> list[ToolDefinition]:
        """List all registered tools, optionally filtered by category."""

    async def call(self, name: str, **kwargs) -> Any:
        """Execute a tool by name with given arguments."""

    def override(self, name: str, fn: Callable) -> None:
        """Replace a tool's implementation (for testing)."""
```

### Tool 定义

```python
class ToolDefinition:
    name: str
    description: str
    category: str                 # "tool" | "skill" | "mcp"
    parameters: dict              # JSON Schema for parameters
    return_type: type
    fn: Callable                  # The actual implementation
    timeout: float = 30.0
    requires_auth: bool = False
```

---

## 3. Skill 注册表 — [TBD: filled by F10+]

### 加载

Skill 在启动时从 `skills/*.yaml` 加载：

```python
class SkillRegistry:
    def __init__(self, tools: ToolRegistry):
        self._skills: dict[str, SkillDefinition] = {}
        self._tools = tools

    def load_from_yaml(self, path: str) -> None:
        """Load a skill YAML declaration and validate tool references."""

    def get(self, skill_id: str) -> SkillDefinition:
        """Retrieve a skill by id."""

    def list_skills(self) -> list[SkillDefinition]:
        """List all registered skills."""

    async def run(self, skill_id: str, context: SkillContext) -> SkillResult:
        """Execute a skill: load prompt → inject context → run sub-flow or delegate to agent."""
```

### Skill 定义

```python
class SkillDefinition:
    id: str
    description: str
    prompt_path: str               # Route to prompts/skills/{id}.md
    tools: list[str]               # Bound tool names
    kb_scope: dict | None          # Default KB filter
    constraints: dict | None
    execution: str                 # "fixed" | "llm_select"
```

### Skill 目录结构

```
skills/
├── _schema.yaml              # Schema documentation
├── rag_answer.yaml            # Built-in: RAG Q&A skill
└── (project-specific skills)

prompts/skills/
├── rag_answer.md              # Skill prompt
└── (project-specific prompts)
```

---

## 4. MCP 适配器协议 — [TBD: filled by F10]

### 适配器架构

```
Agent/Workflow/Domain
       ↓
   ToolRegistry
       ↓
   MCPAdapter (if tool category == "mcp")
       ↓
   MCP Client (JSON-RPC over stdio/SSE)
       ↓
   External MCP Server
```

### MCP 配置

```yaml
# configs/default.yaml
mcp_servers:
  - name: "external_search"
    url: "http://localhost:8080/mcp"
    transport: "sse"
    timeout: 30.0
    tools:
      - name: "web_search"
        description: "Search the web"
```

---

## 5. 内建工具 — [TBD: filled by F10]

| 名称 | 类别 | 说明 | 阶段 |
|------|------|------|------|
| `retrieve_knowledge` | tool | 对知识库进行向量搜索（共享 `RAGRetriever`） | F15b |
| `calculator` | tool | 算术计算 | F10 |
| `datetime_now` | tool | 获取当前日期/时间 | F10 |
| `http_call` | tool | HTTP 请求代理 | F10+ |
| `seq_thinking` | tool | 结构化推理链 | F10+ |

---

## 6. 内建技能 — [TBD: filled by F10+]

| ID | 工具 | 提示词 | 知识库范围 | 执行模式 |
|----|------|--------|------------|----------|
| `rag_answer` | `retrieve_knowledge` | `prompts/skills/rag_answer.md` | 可配置 | fixed |

---

## 7. 错误处理

| 场景 | 错误码 | 行为 |
|------|--------|------|
| 工具未找到 | `7002 AGENT_TOOL_NOT_FOUND` | 返回错误给调用方 |
| 技能未找到 | `7002 AGENT_TOOL_NOT_FOUND` | 返回错误给调用方 |
| 工具执行超时 | `0004 TIMEOUT_ERROR` | 中止并报告 |
| MCP 服务器不可用 | `0003 SERVICE_UNAVAILABLE` | 降级或失败 |
| 工具参数无效 | `0005 VALIDATION_ERROR` | 立即拒绝 |
| 技能工具引用无效 | `7002 AGENT_TOOL_NOT_FOUND` | 注册时即失败 |

---

## 8. 集成点

| 调用方 | 方式 |
|--------|------|
| **Agent**（ACTING 阶段） | `tool_registry.call(name, **kwargs)` 或 `skill_registry.run(id, ctx)` |
| **Workflow**（节点函数） | 在节点函数中使用相同的注册表调用 |
| **Domain**（业务编排） | 业务逻辑的直接注册表调用 |
| **POST /run** | 编排器解析步骤 → skill + tool → 注册表调用 |
| **API**（独立端点） | 直接 tool 调用，如 `/rag/retrieve`、`/embed` 等 |

**核心规则**：能力 API 端点（`/rag/retrieve`、`/embed`）和 `/run` 内部的 tool 调用**共享同一领域层实现**。不进行逻辑分叉。

---

## 9. 新项目自定义

基于本模板创建新项目时：

1. 在 `skills/*.yaml` 中添加项目专属的 skill 定义
2. 在 `prompts/skills/*.md` 中添加技能提示词
3. 在 `app/tools/*.py` 中添加项目工具
4. 在 `ToolRegistry` 启动时注册新工具
5. 在 `workflows/*.yaml` 中添加引用新 skill/tool 的工作流步骤

**模板维护**：引擎代码（`ToolRegistry`、`SkillRegistry`、`SkillRunner`）
**项目自定义**：Skill YAML、工具实现、工作流定义