# Domain Responsibility Map

## Overview

This document maps each domain package to its responsibilities and defines the boundaries between domains. Domains live under `app/domain/` and follow strict layering rules from `ARCHITECTURE.md §3`.

## Layering Rules (Recap)

```
api → domain → services → infra
domain → agent (orchestration)
domain → workflow (orchestration)
domain → tools (usage)
domain ← agent/workflow (domain is the caller)
```

Domains must not:
- Directly access provider SDKs (must go through `services/` or `infra/`)
- Hard-code prompts (must use `services/prompt_manager`)
- Directly call LLM providers (must use `services/llm/gateway`)

## Domain Registry

### chat — [TBD: filled by F14]

| Aspect | Detail |
|--------|--------|
| Package | `app/domain/chat/` |
| Responsibility | Chat conversation management, message handling, context window assembly |
| Key Files | `service.py`, `repo.py`, `schemas.py` |
| Depends On | `services/llm`, `services/context`, `services/sse_stream` |
| API Endpoints | POST /api/v1/chat, GET/DELETE session, GET messages |
| Data Model | `sessions`, `messages` |
| Work Orders | F14 |

### knowledge — [TBD: filled by F05, F15a/F15b/F15c]

| Aspect | Detail |
|--------|--------|
| Package | `app/domain/knowledge/` |
| Responsibility | Knowledge base management: collections, documents, indexing, RAG retrieval |
| Key Files | `service.py`, `repo.py`, `schemas.py` |
| Depends On | `services/llm`, `infra/vector_store`, `services/prompt_manager` |
| API Endpoints | Collection CRUD, document upload/delete, RAG query |
| Data Model | Qdrant collections, document metadata |
| Work Orders | F05, F15a, F15b, F15c |

### intent — [TBD: filled by F16]

| Aspect | Detail |
|--------|--------|
| Package | `app/domain/intent/` |
| Responsibility | Intent classification and routing: three-layer pipeline (keyword → similarity → LLM), multi-intent detection |
| Key Files | `service.py`, `schemas.py` |
| Depends On | `services/llm`, `services/prompt_manager` |
| API Endpoints | POST /api/v1/intent |
| Data Model | None (stateless classification) |
| Work Orders | F16 |

### prompt_admin — [TBD: filled by F08, F17]

| Aspect | Detail |
|--------|--------|
| Package | `app/domain/prompt_admin/` |
| Responsibility | Prompt template query, modify (auto-version + rollback), version history, baseline reset |
| Key Files | `service.py`, `repo.py`, `schemas.py` |
| Depends On | `services/prompt_manager` |
| API Endpoints | Prompt list (with detail), modify, versions history, reset |
| Data Model | `prompt_templates`, `prompt_template_versions` |
| Work Orders | F08, F17 |

### agent_orchestration — [TBD: filled by F11, F12]

| Aspect | Detail |
|--------|--------|
| Package | `app/domain/agent_orchestration/` |
| Responsibility | Business orchestration layer that calls `agent/` engine for task delegation, multi-agent coordination |
| Key Files | `service.py`, `schemas.py` |
| Depends On | `agent/` (engine), `services/llm`, `domain/chat` |
| API Endpoints | POST /api/v1/agent/run, trajectory retrieval |
| Data Model | `agent_trajectories` |
| Work Orders | F11, F12 |

### workflow_orchestration — [TBD: filled by F13]

| Aspect | Detail |
|--------|--------|
| Package | `app/domain/workflow_orchestration/` |
| Responsibility | Business orchestration layer that calls `workflow/` engine for DAG execution |
| Key Files | `service.py`, `schemas.py` |
| Depends On | `workflow/` (engine), `domain/knowledge`, `domain/intent` |
| API Endpoints | POST /api/v1/workflow/run, task status |
| Data Model | `tasks` |
| Work Orders | F13 |

## Cross-Domain Boundaries

### What domains can call

| Caller | Can Call | Cannot Call |
|--------|----------|-------------|
| `chat` | `services/llm`, `services/context`, `services/sse_stream` | `infra/` directly |
| `knowledge` | `services/llm`, `infra/vector_store` (via service), `services/prompt_manager` | `agent/`, `workflow/` |
| `intent` | `services/llm`, `services/prompt_manager` | `infra/` directly |
| `agent_orchestration` | `agent/` engine, `services/llm`, `domain/chat` | `infra/` directly |
| `workflow_orchestration` | `workflow/` engine, `domain/knowledge`, `domain/intent` | `infra/` directly |

### Shared services (not owned by any single domain)

| Service | Package | Used By |
|---------|---------|---------|
| LLM Gateway | `services/llm/` | All domains |
| SSE Stream | `services/sse_stream/` | `chat`, `knowledge` |
| Context Manager | `services/context/` | `chat`, `agent` |
| Prompt Manager | `services/prompt_manager/` | All domains |
| Task Queue | `services/task_queue/` | `workflow_orchestration` |

[TBD: filled by work orders F05, F08, F11–F17]