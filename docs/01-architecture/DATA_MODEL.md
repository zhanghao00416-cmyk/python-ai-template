# Data Model

## Overview

This document defines the database model framework for the Python AI Template. The primary datastore is PostgreSQL (AsyncEngine + SQLAlchemy), managed through `infra/database.py` BaseRepo. Redis is used for caching, rate limiting, and session state. Qdrant is used for vector storage.

## PostgreSQL Tables

### sessions — [TBD: filled by F02, F09]

Stores chat/conversation sessions.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Session identifier |
| user_id | VARCHAR(255) | Owner user identifier |
| title | VARCHAR(500) | Session display title |
| intent_type | VARCHAR(50) | Classified intent type (qa/task/chat/retrieve_only) |
| model_config | JSONB | Model configuration for this session |
| created_at | TIMESTAMPTZ | Session creation time |
| updated_at | TIMESTAMPTZ | Last update time |
| metadata | JSONB | Extensible session metadata |

### messages — [TBD: filled by F09]

Stores individual messages within a session.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Message identifier |
| session_id | UUID (FK → sessions.id) | Parent session |
| role | VARCHAR(20) | Message role: user / assistant / system / tool |
| content | TEXT | Message content |
| token_count | INTEGER | Token count for context window management |
| model_name | VARCHAR(100) | LLM model used for generation |
| citations | JSONB | Citation references from RAG |
| tool_calls | JSONB | Tool call requests (for agent messages) |
| tool_results | JSONB | Tool call results (for tool messages) |
| created_at | TIMESTAMPTZ | Message creation time |
| metadata | JSONB | Extensible message metadata |

### tasks — [TBD: filled by F07]

Stores async task records for the ARQ task queue.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Task identifier |
| task_type | VARCHAR(50) | Task type: kb_upload / agent_run / workflow_run / batch_import / batch_eval / batch_embed / custom |
| status | VARCHAR(20) | Task status: pending / running / completed / failed |
| input_data | JSONB | Task input payload |
| output_data | JSONB | Task result payload (when completed) |
| error_message | TEXT | Error message (if failed) |
| progress | FLOAT | Task progress percentage (0.0–1.0) |
| created_at | TIMESTAMPTZ | Task creation time |
| started_at | TIMESTAMPTZ | Task start time |
| completed_at | TIMESTAMPTZ | Task completion time |
| user_id | VARCHAR(255) | Task owner |
| metadata | JSONB | Extensible task metadata |

### agent_trajectories — [TBD: filled by F11, F12]

Stores agent execution traces for observability and evaluation.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Trajectory record identifier |
| session_id | UUID (FK → sessions.id) | Parent session |
| agent_name | VARCHAR(100) | Agent identifier |
| step_index | INTEGER | Step number in ReAct loop |
| state | VARCHAR(30) | Agent state at this step (IDLE/THINKING/ACTING/OBSERVING/DONE) |
| thought | TEXT | Agent's reasoning text |
| action | JSONB | Tool call specification |
| observation | JSONB | Tool call result |
| token_usage | JSONB | Token consumption record |
| created_at | TIMESTAMPTZ | Step timestamp |

### prompt_templates — [TBD: filled by F08]

Stores prompt template metadata and version history (actual content loaded from `prompts/` directory).

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Template identifier |
| name | VARCHAR(255, UNIQUE) | Template name (matches filename) |
| directory | VARCHAR(100) | Directory group (e.g. agents, skills) |
| description | TEXT | Template description |
| content | TEXT | Current template content |
| variables | JSONB | Auto-extracted template variable definitions |
| version | INTEGER | Current version number (auto-incremented) |
| baseline_content | TEXT | Original content from prompts/ directory |
| baseline_version | INTEGER | Version number of the baseline |
| created_at | TIMESTAMPTZ | Creation time |
| updated_at | TIMESTAMPTZ | Last modification time |

### prompt_template_versions — [TBD: filled by F08]

Stores version history for prompt templates, enabling rollback to any previous version.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Version record identifier |
| template_id | UUID (FK → prompt_templates.id) | Parent template |
| version | INTEGER | Version number |
| content | TEXT | Template content at this version |
| description | TEXT | Description at this version |
| updated_by | VARCHAR(255) | Who made this change |
| created_at | TIMESTAMPTZ | Version creation time |

## Redis Data Structures — [TBD: filled by F02, F20]

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `rate_limit:{api_key}` | STRING (counter) | Configurable | Rate limit counter |
| `session_ctx:{session_id}` | HASH | Session TTL | Session context cache |
| `task_status:{task_id}` | HASH | Task TTL | Async task status |

## Qdrant Collections — [TBD: filled by F05]

See `docs/04-kb/QDRANT_COLLECTION_CONFIG.md` for detailed vector store schema.

## Entity Relationships

```
sessions 1──N messages
sessions 1──N agent_trajectories
sessions 1──N tasks (indirect, via task_type)
prompt_templates 1──N prompt_template_versions
```

## Migration Strategy — [TBD: filled by F02]

- Alembic for migration management
- Auto-generate migrations from SQLAlchemy models
- Each work order that modifies the data model must include a migration

## Repository Access Pattern

All database access goes through `domain/*/repo.py` which inherits from `infra/database.py:BaseRepo`:

```python
class BaseRepo:
    async def get_by_id(id)
    async def create(data)
    async def update(id, data)
    async def delete(id)
    async def list(filters, pagination)
```

Domain code never writes raw SQL; all queries go through repo abstractions.

[TBD: filled by work orders F02, F05, F07, F08, F09, F11]