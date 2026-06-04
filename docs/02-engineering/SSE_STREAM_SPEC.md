# SSE Stream Service 规范

## 概述

SSE Stream Service 是 `app/services/sse_stream.py` 的核心封装，负责将 10 种 SSE 事件类型的格式化逻辑与业务领域完全隔离。业务层只调用语义方法，不接触 SSE 传输细节。

---

## 10 种事件类型

| 事件 | 数据字段 | 描述 |
|------|----------|------|
| `start` | `intent`, `user_id`, `session_id` | 流开始；intent 指示域（qa/task/chat/retrieve_only/agent/workflow） |
| `intent` | `intent`, `confidence`, `layer_used` | 意图分类结果 |
| `chunk` | `content` | 流式文本 token |
| `structured` | `data`, `user_id?`, `session_id?` | 结构化数据载荷 |
| `citation` | `sources` | 知识库检索引用 |
| `heartbeat` | `ts` | 保活心跳，间隔由 `sse.heartbeat_interval` 配置（默认 15s） |
| `progress` | `current`, `total`, `node?` | 多步操作进度指示（工作流节点等） |
| `usage` | `input_tokens`, `output_tokens`, `model` | Token 用量统计，必须在 `done` 之前发送 |
| `done` | `reason` | 流正常结束 |
| `error` | `code`, `message` | 错误；`code` 为字符串 `AI_%04d`（如 `AI_2003`），与 REST 整数码对应，见 `ERROR_CODE.md` |

---

## 事件顺序规则

```
start → [intent]? → [route]? → [heartbeat]* → chunk* → [structured]? → [citation]? → [progress]* → [usage]? → done
               → [agent]* → [tool]*
                                                                                                    ↘ error (anytime)
```

- `start` 必须是第一个事件
- `done` 或 `error` 必须是最后一个事件
- `heartbeat` 在等待 LLM 响应期间周期性发送
- `progress` 兼做心跳（workflow 场景中不再额外发 heartbeat）
- `structured` 和 `citation` 在有数据时发送
- `usage` 在所有涉及 LLM 调用的流中必须发送，位于 `done` 之前
- `intent` 在意图分类完成后发送（仅 `/run` 接口）
- `error` 可在任何时刻中断流

---

## SSEStreamService 接口设计

```python
class SSEStreamService:
    def __init__(
        self,
        intent: str,
        user_id: str,
        session_id: str,
        is_disconnected: Callable[[], bool] | Callable[[], Any] | None = None,
    ):
        """初始化流，绑定请求上下文。is_disconnected 回调用于断连检测。"""

    async def start(self) -> AsyncGenerator[str, None]:
        """发送 start 事件。每次调用前检查断连。"""

    async def intent(self, intent: str, confidence: float, layer_used: str) -> AsyncGenerator[str, None]:
        """发送 intent 事件（意图分类结果）。"""

    async def heartbeat(self) -> AsyncGenerator[str, None]:
        """发送 heartbeat 事件。"""

    async def chunk(self, content: str) -> AsyncGenerator[str, None]:
        """发送 chunk 事件。"""

    async def structured(
        self,
        data: Any,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """发送 structured 事件。"""

    async def citation(self, sources: list[dict]) -> AsyncGenerator[str, None]:
        """发送 citation 事件。空 sources 列表时静默跳过。"""

    async def progress(self, current: int, total: int, node: str | None = None) -> AsyncGenerator[str, None]:
        """发送 progress 事件。"""

    async def usage(self, input_tokens: int, output_tokens: int, model: str) -> AsyncGenerator[str, None]:
        """发送 usage 事件（Token 统计）。"""

    async def done(self) -> AsyncGenerator[str, None]:
        """发送 done 事件。"""

    async def error(self, code: int, message: str) -> AsyncGenerator[str, None]:
        """发送 error 事件。code 为 ErrorCode 整数，内部调用 format_error_code 转为 AI_xxxx 字符串。"""

    async def safe_start_then_error(self, code: int, message: str) -> AsyncGenerator[str, None]:
        """若尚未 start，先发 start 再发 error+done；若已 start，直接发 error+done。用于异常兜底。"""


async def wrap_with_heartbeat(
    main_gen: AsyncGenerator[str, None],
    sse: SSEStreamService,
    interval: float | None = None,
) -> AsyncGenerator[str, None]:
    """合并主事件流与周期性心跳。使用 asyncio.Queue 解耦避免 CancelledError 关闭主生成器。"""
```

### error 事件载荷示例

SSE 线格式：`data: {"type":"error","code":"AI_2003","message":"Intent classification timed out"}\n\n`

业务代码调用 `sse.error(code=ErrorCode.INTENT_TIMEOUT, message="Intent classification timed out")`，传入整数 ErrorCode，内部通过 `format_error_code()` 转为 `AI_xxxx` 字符串。

---

## 使用模式

### Chat / RAG 流式回答

```python
sse = SSEStreamService(intent="chat", user_id=user_id, session_id=session_id)

async for event in sse.start():
    yield event

# 流式 LLM 回答
stream = await gateway.text_chat(messages, stream=True, task=TextTask.CHAT)
if isinstance(stream, str):
    async for event in sse.chunk(stream):
        yield event
else:
    async for chunk_text in stream:
        async for event in sse.chunk(chunk_text):
            yield event

# Token 统计
async for event in sse.usage(input_tokens=150, output_tokens=300, model="qwen-plus"):
    yield event

async for event in sse.done():
    yield event
```

### Orchestrated (/run) 流式回答

```python
sse = SSEStreamService(intent="qa", user_id=user_id, session_id=session_id)

async for event in sse.start():
    yield event

# 意图分类结果
async for event in sse.intent(intent="qa", confidence=0.95, layer_used="keyword"):
    yield event

# RAG 检索引用
async for event in sse.citation(sources=citation_list):
    yield event

# 流式回答
async for chunk_text in stream:
    async for event in sse.chunk(chunk_text):
        yield event

async for event in sse.usage(input_tokens=300, output_tokens=500, model="qwen-plus"):
    yield event

async for event in sse.done():
    yield event
```

### Workflow 多步处理

```python
async for event in sse.start():
    yield event
# 节点进度
async for event in sse.progress(current=2, total=5, node="rag_search"):
    yield event
# 流式回答
async for event in sse.chunk(text):
    yield event
async for event in sse.usage(input_tokens=200, output_tokens=400, model="qwen-plus"):
    yield event
async for event in sse.done():
    yield event
```

---

## 断连检测

Service 内部集成断连检测：

- 构造时传入 `is_disconnected` 回调（sync 或 async）
- 每次发送事件前调用回调检查连接状态
- 检测到断连时抛出 `asyncio.CancelledError("Client disconnected")`，停止生成、释放资源
- 日志记录断连事件（structlog `sse_client_disconnected`）
- 默认 `is_disconnected=lambda: False`（不断连）

---

## 心跳策略

| 场景 | 心跳方式 |
|------|----------|
| Chat / RAG | `heartbeat` 事件，间隔 15s |
| Workflow 执行 | `progress` 事件兼做心跳 |
| Agent 工具执行 | `heartbeat` 事件，间隔 15s |

心跳通过 `wrap_with_heartbeat()` 函数实现，使用 `asyncio.Queue` 解耦主生成器与心跳定时器，避免 `asyncio.wait_for` 取消 `__anext__()` 导致 CancelledError 关闭主生成器。

配置项：
- `settings.sse.heartbeat_interval`：心跳间隔（秒），默认 15
- `settings.server.debug_sse_output`：SSE 调试日志开关，默认 False

---

## 工单映射

本规范由 **F06 SSE 流式服务** 实现。
