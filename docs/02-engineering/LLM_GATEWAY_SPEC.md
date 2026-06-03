# LLM Gateway Specification

## Overview

The LLM Gateway (`app/services/llm/`) provides a unified call pipeline for all LLM interactions. It uses the Strategy Pattern to abstract provider switching, enforces concurrency control via semaphores, and integrates with the observability layer for token tracking and latency logging.

## Architecture — [TBD: filled by F04]

```
Caller (domain/service)
       ↓
   LLMGateway (unified interface)
       ↓
   LLMRouter (strategy selection by config)
       ↓
   ProviderAdapter (qwen_cloud | vllm | ...)
       ↓
   External API (Qwen Cloud / vLLM server)
```

## Strategy Pattern — [TBD: filled by F04]

### Base Strategy

```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Non-streaming generation."""

    @abstractmethod
    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        """Streaming generation yielding chunks."""
```

### Provider Adapters — [TBD: filled by F04]

| Adapter | Task Type | Default Channel | Fallback |
|---------|-----------|----------------|----------|
| QwenCloudProvider | Text | qwen_cloud API | vLLM |
| VLLMProvider | Text | Local vLLM server | None |
| MultimodalProvider | Vision/Video | Config-specified | None |

### Routing Logic — [TBD: filled by F04]

```python
class LLMRouter:
    def select_provider(self, task_type: str, model: str | None = None) -> LLMProvider:
        """
        Route based on:
        1. Explicit model override in request
        2. Task type → default channel mapping from config
        3. Fallback channel if primary fails
        """
```

## Unified Call Pipeline — [TBD: filled by F04]

Every LLM call goes through:

1. **Pre-processing**: Inject system prompt, validate parameters
2. **Concurrency control**: Acquire semaphore permit (configurable concurrency limit)
3. **Timeout**: Enforce per-request timeout
4. **Provider call**: Delegate to selected adapter
5. **Post-processing**: Normalize response format
6. **Observability**: Log token usage, latency, success/failure
7. **Error handling**: Wrap provider errors into structured `AI_xxxx` error codes

## Request/Response Models — [TBD: filled by F04]

```python
class LLMRequest:
    messages: list[Message]
    model: str | None         # Override model selection
    task_type: str            # "text" | "vision" | "video_analysis" | "embedding"
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    timeout: float = 30.0
    metadata: dict = {}       # trace_id, user_id, session_id

class LLMResponse:
    content: str
    model: str                # Actual model used
    input_tokens: int
    output_tokens: int
    finish_reason: str
    metadata: dict
```

## Streaming Protocol — [TBD: filled by F04]

```python
class LLMChunk:
    content: str | None       # Delta content
    finish_reason: str | None
    input_tokens: int | None  # Available on last chunk
    output_tokens: int | None # Available on last chunk
```

## Concurrency Control — [TBD: filled by F04]

AI inference is resource-heavy. All LLM calls must be wrapped in semaphore protection:

```python
llm_semaphore = asyncio.Semaphore(config.LLM_MAX_CONCURRENT)

async def generate(self, request):
    async with llm_semaphore:
        # ... provider call ...
```

No unlimited async fanout is permitted.

## Error Handling — [TBD: filled by F04]

| Provider Error | Mapped Code | Action |
|----------------|-------------|--------|
| Connection timeout | `0004 TIMEOUT_ERROR` | Retry with fallback |
| Rate limit (429) | `0006 RATE_LIMITED` | Backoff and retry |
| Auth failure (401/403) | `1001 AUTH_INVALID_KEY` | Fail immediately |
| Model not found | `0003 SERVICE_UNAVAILABLE` | Retry with fallback |
| Invalid request | `0005 VALIDATION_ERROR` | Fail immediately |

## Token Tracking — [TBD: filled by F18]

Every call records:
- `input_tokens`, `output_tokens`
- `model`, `task_type`
- `user_id`, `session_id`
- `latency_ms`
- Success/failure

Exposed via `/metrics` endpoint in Prometheus format.

## Configuration — [TBD: filled by F04]

```yaml
llm:
  max_concurrent: 5
  default_timeout: 30.0
  channels:
    text:
      default: qwen_cloud
      fallback: vllm
    multimodal:
      default: qwen_cloud_vision
      fallback: null
  providers:
    qwen_cloud:
      api_key: ${QWEN_API_KEY}
      base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    vllm:
      base_url: http://localhost:8000
```

[TBD: filled by work orders F04, F18]