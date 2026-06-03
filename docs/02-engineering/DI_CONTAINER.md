# DI 容器设计

## 概述

项目在 `app/core/di.py` 中使用轻量级依赖注入容器，与 FastAPI 的 `Depends` 系统集成。容器遵循注册/解析/覆盖模式。

## 容器 API — [TBD: filled by F01]

### 核心方法

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

### 注册模式

```python
# Singleton (default) — one instance shared across the app
container.register(LLMGateway, llm_gateway_factory, singleton=True)

# Transient — new instance per resolve
container.register(SomeHandler, some_handler_factory, singleton=False)

# Override for testing
container.override(LLMGateway, mock_llm_gateway_factory)
```

## FastAPI 集成 — [TBD: filled by F01]

DI 容器与 FastAPI 之间的桥接在 `app/api/deps.py` 中：

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

## 注册顺序 — [TBD: filled by F01]

注册在应用启动时于 `app/main.py` 中完成：

1. 配置加载（`core/config.py`）
2. 基础设施注册（`infra/` 工厂）
3. 服务注册（`services/` 工厂）
4. 领域服务注册（`domain/` 工厂）
5. API 路由挂载

注册必须遵循依赖方向：infra → services → domain。

## 单例生命周期 — [TBD: filled by F01]

| 阶段 | 操作 |
|-------|--------|
| 启动 | `container.register()` 注册所有工厂 |
| 请求 | `container.resolve()` 通过 `Depends()` 解析 |
| 测试 | 测试前用 `container.override()` 注入 mock，测试后 `container.reset()` 恢复 |
| 关闭 | `container.cleanup()` 释放资源 |

## 模块注册参考 — [TBD: filled by subsequent work orders]

| 模块 | 注册类型 | 单例 | 工单 |
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

## 测试策略

```python
# In conftest.py or per-test:
container.override(LLMGateway, lambda: MockLLMGateway())
# ... run test ...
container.reset(LLMGateway)
```

所有服务依赖均通过容器解析，使每个组件均可通过 mock 替代进行测试。

[TBD: filled by work orders F01, F02, F04–F10]