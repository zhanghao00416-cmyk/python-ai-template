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
    def __init__(self, intent: str, user_id: str, session_id: str):
        """初始化流，绑定请求上下文。"""

    async def start(self) -> AsyncGenerator[str, None]:
        """发送 start 事件。"""

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
        """发送 citation 事件。"""

    async def progress(self, current: int, total: int, node: str | None = None) -> AsyncGenerator[str, None]:
        """发送 progress 事件。"""

    async def usage(self, input_tokens: int, output_tokens: int, model: str) -> AsyncGenerator[str, None]:
        """发送 usage 事件（Token 统计）。"""

    async def done(self) -> AsyncGenerator[str, None]:
        """发送 done 事件。"""

    async def error(self, code: str, message: str) -> AsyncGenerator[str, None]:
        """发送 error 事件。code 必须为 AI_%04d 字符串（由 format_error_code 生成）。"""
```

### error 事件载荷示例

```json
{
  "event": "error",
  "data": {
    "code": "AI_2003",
    "message": "Intent classification timed out"
  }
}
```

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

Service 内部应集成断连检测：

- 发送事件前检查 `request.is_disconnected()`
- 检测到断连时停止生成、释放资源
- 日志记录断连事件

---

## 心跳策略

| 场景 | 心跳方式 |
|------|----------|
| Chat / RAG | `heartbeat` 事件，间隔 15s |
| Workflow 执行 | `progress` 事件兼做心跳 |
| Agent 工具执行 | `heartbeat` 事件，间隔 15s |

---

## 工单映射

本规范由 **F06 SSE 流式服务** 实现。
