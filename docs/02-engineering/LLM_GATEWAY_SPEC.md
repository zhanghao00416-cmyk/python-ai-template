# LLM 网关规范

## 概述

LLM 网关（`app/services/llm/`）为所有 LLM 交互提供统一的调用管道。它使用策略模式抽象提供者切换，通过信号量实施并发控制，并集成可观测层用于令牌追踪和延迟日志记录。

## 架构 — [TBD: filled by F04]

```
调用方 (domain/service)
        ↓
    LLMGateway (统一接口)
        ↓
    LLMRouter (按配置选择策略)
        ↓
    ProviderAdapter (qwen_cloud | vllm | ...)
        ↓
    外部 API (Qwen Cloud / vLLM server)
```

## 策略模式 — [TBD: filled by F04]

### 基础策略

```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Non-streaming generation."""

    @abstractmethod
    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        """Streaming generation yielding chunks."""
```

### 提供者适配器 — [TBD: filled by F04]

| 适配器 | 任务类型 | 默认通道 | 降级通道 |
|--------|----------|----------|----------|
| QwenCloudProvider | 文本 | qwen_cloud API | vLLM |
| VLLMProvider | 文本 | 本地 vLLM 服务 | 无 |
| MultimodalProvider | 多模态 | 配置指定 | 无 |

### 路由逻辑 — [TBD: filled by F04]

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

## 统一调用管道 — [TBD: filled by F04]

每次 LLM 调用都经过：

1. **预处理**：注入系统提示词，校验参数
2. **并发控制**：获取信号量许可（可配置并发上限）
3. **超时**：强制执行单请求超时
4. **提供者调用**：委托至选定的适配器
5. **后处理**：标准化响应格式
6. **可观测性**：记录令牌用量、延迟、成功/失败
7. **错误处理**：将提供者错误包装为结构化 `AI_xxxx` 错误码

## 请求/响应模型 — [TBD: filled by F04]

```python
class LLMRequest:
    messages: list[Message]
    model: str | None         # Override model selection
    task_type: str            # "text" | "multimodal" | "embedding"
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

## 流式协议 — [TBD: filled by F04]

```python
class LLMChunk:
    content: str | None       # Delta content
    finish_reason: str | None
    input_tokens: int | None  # Available on last chunk
    output_tokens: int | None # Available on last chunk
```

## 并发控制 — [TBD: filled by F04]

AI 推理属于资源密集型操作。所有 LLM 调用必须包裹在信号量保护中：

```python
llm_semaphore = asyncio.Semaphore(config.LLM_MAX_CONCURRENT)

async def generate(self, request):
    async with llm_semaphore:
        # ... provider call ...
```

不允许无限制的异步扇出。

## 错误处理 — [TBD: filled by F04]

| 提供者错误 | 映射错误码 | 处理动作 |
|-----------|-----------|---------|
| 连接超时 | `0004 TIMEOUT_ERROR` | 使用降级通道重试 |
| 速率限制 (429) | `0006 RATE_LIMITED` | 退避后重试 |
| 认证失败 (401/403) | `1001 AUTH_INVALID_KEY` | 立即失败 |
| 模型未找到 | `0003 SERVICE_UNAVAILABLE` | 使用降级通道重试 |
| 无效请求 | `0005 VALIDATION_ERROR` | 立即失败 |

## 令牌追踪 — [TBD: filled by F18]

每次调用记录：
- `input_tokens`、`output_tokens`
- `model`、`task_type`
- `user_id`、`session_id`
- `latency_ms`
- 成功/失败

通过 `/metrics` 端点以 Prometheus 格式暴露。

## 配置 — [TBD: filled by F04]

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