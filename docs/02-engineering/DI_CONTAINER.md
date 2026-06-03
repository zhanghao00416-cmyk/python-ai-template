# DI Container Design

## Overview

The project uses a lightweight dependency injection container in `app/core/di.py` that integrates with FastAPI's `Depends` system. The container follows a register/resolve/override pattern.

## Container API — [TBD: filled by F01]

### Core Methods

```python
class DIContainer:
    def register(cls, factory: Callable, singleton: bool = True) -> None:
        """Register a factory for a type. Singleton by default."""

    def resolve(cls) -> Any:
        """Resolve a registered type, creating instance(s) as needed."""

    def override(cls, factory: Callable) -> None:
        """Replace a registration (for testing). Returns on next reset()."""

    def reset(cls) -> None:
        """Remove override, restoring original registration."""

    def cleanup(self) -> None:
        """Dispose all singleton instances (for app shutdown)."""
```

### Registration Patterns

```python
# Singleton (default) — one instance shared across the app
container.register(LLMGateway, llm_gateway_factory, singleton=True)

# Transient — new instance per resolve
container.register(SomeHandler, some_handler_factory, singleton=False)

# Override for testing
container.override(LLMGateway, mock_llm_gateway_factory)
```

## FastAPI Integration — [TBD: filled by F01]

The bridge between DI container and FastAPI is in `app/api/deps.py`:

```python
# api/deps.py
from core.di import container
from fastapi import Depends

def get_llm_gateway() -> LLMGateway:
    return container.resolve(LLMGateway)

# In router:
@router.post("/chat")
async def chat(gateway: LLMGateway = Depends(get_llm_gateway)):
    ...
```

## Registration Order — [TBD: filled by F01]

Registration happens at application startup in `app/main.py`:

1. Configuration loaded (`core/config.py`)
2. Infrastructure registered (`infra/` factories)
3. Services registered (`services/` factories)
4. Domain services registered (`domain/` factories)
5. API routers mounted

Registration must follow the dependency direction: infra → services → domain.

## Singleton Lifecycle — [TBD: filled by F01]

| Phase | Action |
|-------|--------|
| Startup | `container.register()` all factories |
| Request | `container.resolve()` via `Depends()` |
| Testing | `container.override()` with mocks before test, `container.reset()` after |
| Shutdown | `container.cleanup()` to dispose resources |

## Module Registration Reference — [TBD: filled by subsequent work orders]

| Module | Registered Type | Singleton | Work Order |
|--------|----------------|-----------|------------|
| infra/database | AsyncEngine, BaseRepo subclasses | Yes | F02 |
| infra/redis_client | Redis client | Yes | F02 |
| infra/vector_store | VectorStoreClient | Yes | F05 |
| services/llm | LLMGateway | Yes | F04 |
| services/sse_stream | SSEStreamService | Yes | F06 |
| services/prompt_manager | PromptManager | Yes | F08 |
| services/context | ContextManager | Yes | F09 |
| services/task_queue | TaskQueueService | Yes | F07 |
| domain/chat | ChatService | No | F14 |
| domain/knowledge | KnowledgeService | No | F15a–F15c |
| domain/intent | IntentService | No | F16 |

## Testing Strategy

```python
# In conftest.py or per-test:
container.override(LLMGateway, lambda: MockLLMGateway())
# ... run test ...
container.reset(LLMGateway)
```

All service dependencies are resolved through the container, making every component testable with mock replacements.

[TBD: filled by work orders F01, F02, F04–F10]