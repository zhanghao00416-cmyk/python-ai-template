# Tools / Skills / MCP Specification

## Overview

The tools layer provides a **three-tier capability model**: Tools (atomic), Skills (composable), and MCP (external). This replaces the previous flat `@tool/@skill` decorator model with a clearer separation that supports both programmatic registration and YAML-based declaration.

---

## 1. Three-Tier Capability Model

| Concept | Definition | Config Location | Code Location |
|---------|-----------|----------------|---------------|
| **Tool** | Atomic executable capability (single IO/function) | Programmatic registration | `app/tools/` |
| **Skill** | Composable capability pack: prompt + bound tools + optional KB scope + optional fixed sub-flow | `skills/*.yaml` + `prompts/skills/*.md` | `app/domain/skills/` |
| **MCP** | External tool protocol adapter | `configs/default.yaml` mcp_servers | `app/tools/mcp_adapter.py` |

### 1.1 Tool

A tool is a single async function with typed parameters. No sub-flow, no prompt.

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

A skill bundles a prompt, bound tools, and optional constraints into a reusable pack. Skills are declared in YAML and loaded at startup.

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

| Field | Description |
|-------|-------------|
| `id` | Unique skill identifier |
| `description` | One-line description for registry listing |
| `prompt` | Path to prompt file (relative to project root) |
| `tools` | List of Tool names this skill is authorized to use |
| `kb_scope` | Optional knowledge base filter defaults (null = inherit from request) |
| `constraints` | Optional execution constraints (max_citations, timeout, etc.) |
| `execution` | `fixed` (Phase 1) or `llm_select` (Phase 3+) |

### 1.3 Step Capability Union

When a workflow step references both skills and tools, the **visible capability set** is the union:

```
step_capabilities = skill_tools ∪ step.tools ∪ agent.default_tools
```

This means:
- Steps can use **only tools** (no skill prompt)
- Steps can use **only skills** (skill provides both prompt and tools)
- Steps can use **both** (skill prompt + extra bare tools)

---

## 2. Tool Registry — [TBD: filled by F10]

### Registration API

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

### Tool Definition

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

## 3. Skill Registry — [TBD: filled by F10+]

### Loading

Skills are loaded from `skills/*.yaml` at startup:

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

### Skill Definition

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

### Skill Directory Structure

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

## 4. MCP Adapter Protocol — [TBD: filled by F10]

### Adapter Architecture

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

### MCP Configuration

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

## 5. Builtin Tools — [TBD: filled by F10]

| Name | Category | Description | Phase |
|------|----------|-------------|-------|
| `retrieve_knowledge` | tool | Vector search over knowledge base (shares `RAGRetriever`) | F15b |
| `calculator` | tool | Arithmetic calculations | F10 |
| `datetime_now` | tool | Current date/time | F10 |
| `http_call` | tool | HTTP request proxy | F10+ |
| `seq_thinking` | tool | Structured reasoning chain | F10+ |

---

## 6. Builtin Skills — [TBD: filled by F10+]

| ID | Tools | Prompt | KB Scope | Execution |
|----|-------|--------|----------|-----------|
| `rag_answer` | `retrieve_knowledge` | `prompts/skills/rag_answer.md` | configurable | fixed |

---

## 7. Error Handling

| Scenario | Error Code | Behavior |
|----------|-----------|----------|
| Tool not found | `7002 AGENT_TOOL_NOT_FOUND` | Return error to caller |
| Skill not found | `7002 AGENT_TOOL_NOT_FOUND` | Return error to caller |
| Tool execution timeout | `0004 TIMEOUT_ERROR` | Abort and report |
| MCP server unavailable | `0003 SERVICE_UNAVAILABLE` | Fallback or fail |
| Invalid tool parameters | `0005 VALIDATION_ERROR` | Reject immediately |
| Skill tool reference invalid | `7002 AGENT_TOOL_NOT_FOUND` | Fail at registration time |

---

## 8. Integration Points

| Caller | How |
|--------|-----|
| **Agent** (during ACTING phase) | `tool_registry.call(name, **kwargs)` or `skill_registry.run(id, ctx)` |
| **Workflow** (node function) | Same registry calls within node functions |
| **Domain** (business orchestration) | Direct registry calls for business logic |
| **POST /run** | Orchestrator resolves step → skills + tools → registry calls |
| **API** (standalone endpoints) | Direct tool calls for `/rag/retrieve`, `/embed`, etc. |

**Key rule**: Capability API endpoints (`/rag/retrieve`, `/embed`) and `/run`-internal tool calls **share the same domain-layer implementation**. No logic fork.

---

## 9. New Project Customization

When forking this template for a new project:

1. Add new `skills/*.yaml` for project-specific skills
2. Add new `prompts/skills/*.md` for skill prompts
3. Add new `app/tools/*.py` for project tools
4. Register new tools in `ToolRegistry` startup
5. Add workflow steps referencing new skills/tools in `workflows/*.yaml`

**Template-maintained**: Engine code (`ToolRegistry`, `SkillRegistry`, `SkillRunner`)
**Project-customized**: Skill YAML, tool implementations, workflow definitions