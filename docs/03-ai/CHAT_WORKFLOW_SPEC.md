# 对话工作流规范

## 概述

对话工作流（`app/domain/chat/`）管理会话、消息持久化、上下文窗口组装、LLM 交互以及 SSE 流式响应。它是核心的用户面向交互模式。

## 对话请求流程 — [filled by F14]

```
POST /api/v1/chat (SSE)
    ↓
API 层 (api/chat.py)
    ↓
ChatService (domain/chat/service.py)
    ↓
┌──────────────────────────────────┐
│ 1. 解析或创建会话                  │
│ 2. 持久化用户消息                  │
│ 3. 构建上下文窗口                  │
│ 4. 调用 LLM 网关（流式）           │
│ 5. 流式推送 SSE 事件               │
│ 6. 持久化助手消息                  │
│ 7. 更新会话元数据                  │
└──────────────────────────────────┘
    ↓
SSE 事件流推送至客户端
```

## SSE 事件协议 — [filled by F06, F14]

对话端点返回一个 SSE 流，包含以下事件：

```
event: start
data: {"session_id": "uuid", "message_id": "uuid"}

event: chunk
data: {"content": "partial text", "message_id": "uuid"}

event: citation
data: {"sources": [{"doc_id": "...", "heading": "...", "score": 0.95}], "message_id": "uuid"}

event: heartbeat
data: {"ts": "2024-01-01T00:00:00Z"}

event: done
data: {"message_id": "uuid", "reason": "complete", "input_tokens": 50, "output_tokens": 120}

event: error
data: {"code": "AI_1001", "message": "Unauthorized"}
```

### 事件生命周期

1. `start` — 立即发送，包含会话 ID 和消息 ID
2. `chunk` — 每个 LLM 流式 token 组发送一次
3. `citation` — 当 RAG 来源可用时发送（可选）
4. `heartbeat` — 每 N 秒发送一次以防止超时（可配置，默认 15 秒）
5. `done` — LLM 生成完成时发送，包含 token 统计信息
6. `error` — 发生任何错误时发送，随后关闭流

## 会话生命周期 — [filled by F09, F14]

会话在首次对话请求时自动创建。调用方生成 `session_id`（UUID）；如果该 ID 不存在，则自动创建新会话。

### 自动创建会话

当对话请求携带的 `session_id` 不存在时：

1. 使用 `user_id`、`session_id`、`title`（可选）、`model_config`（可选）创建新会话
2. 首次设置的字段仅在创建时生效
3. 后续使用相同 `session_id` 的请求将复用该会话

### 获取会话

```python
GET /api/v1/chat/sessions/{session_id}
→ { "session_id": "uuid", "title": "...", "message_count": 5, "created_at": "...", "updated_at": "..." }
```

### 删除会话

```python
DELETE /api/v1/chat/sessions/{session_id}
→ { "code": 0, "message": "ok" }
```

## 消息持久化 — [filled by F09, F14]

### 添加用户消息

当对话请求到达时：

1. 如果提供了 `session_id`：验证会话是否存在
2. 如果没有 `session_id`：创建新会话
3. 通过 `ContextManager.add_message()` 持久化用户消息
4. 计算 token 数并存储在 `token_count` 字段中

### 添加助手消息

LLM 生成完成后：

1. 通过 `ContextManager.add_message()` 持久化完整的助手响应
2. 存储 `input_tokens` 和 `output_tokens`
3. 如果使用了 RAG，则存储 `citations`
4. 更新 `session.updated_at`

## 上下文窗口组装 — [filled by F09, F14]

调用 LLM 之前，对话服务组装上下文：

1. 从 `prompts/chat/system.md` 加载系统提示词
2. 通过 `ContextManager.get_context_window()` 检索对话历史
3. 应用截断策略（默认：`recent_priority`）
4. 合并：系统提示词 + 截断后的历史 + 用户消息
5. 确保总 token 数 ≤ 模型上下文限制

### 上下文窗口参数 — [filled by F14]

```python
class ChatContextConfig:
    max_context_tokens: int = 4096    # 总上下文窗口
    system_prompt_tokens: int = 500   # 系统提示词预算
    truncation_strategy: str = "recent_priority"
    include_citations: bool = True
```

## LLM 调用 — [filled by F04, F14]

- 使用 `LLMGateway.generate_stream()` 获取 SSE 响应
- 任务类型：`"chat"`
- 模型：来自会话配置或默认配置
- 并发：受 LLM 信号量管控
- 超时：可按对话请求配置

## 流式服务 — [filled by F06, F14]

SSE 流由 `services/sse_stream/` 管理：

```python
class SSEStreamService:
    async def create_stream(
        self,
        session_id: UUID,
        llm_stream: AsyncIterator[LLMChunk]
    ) -> EventSourceResponse:
        """
        1. 发送 'start' 事件
        2. 迭代 LLM 流，发送 'chunk' 事件
        3. 如有可用来源，发送 'citation' 事件
        4. 定期发送 'heartbeat' 事件
        5. 发送包含 token 统计的 'done' 事件
        6. 处理断开检测
        7. 出错时：发送 'error' 事件并关闭
        """
```

### 断开检测 — [filled by F06]

- 通过 asyncio 事件检测客户端断开
- 断开时：取消 LLM 流，发送日志事件
- 不允许遗留孤立的 LLM 调用

## API 端点 — [filled by F14]

| 方法 | 路径 | 描述 | 响应 |
|------|------|------|------|
| POST | /api/v1/chat | 对话补全（自动创建会话，SSE 或同步） | EventSourceResponse / JSON |
| GET | /api/v1/chat/sessions/{id} | 获取会话 | JSON |
| GET | /api/v1/chat/sessions/{id}/messages | 列出消息 | JSON |
| DELETE | /api/v1/chat/sessions/{id} | 删除会话（软删除，级联） | JSON |

## 错误码 — [filled by F14]

使用 `docs/01-architecture/ERROR_CODE.md` 中的系统错误码：

- `0004 TIMEOUT_ERROR` — LLM 超时
- `0003 SERVICE_UNAVAILABLE` — LLM 不可用
- `0005 VALIDATION_ERROR` — 无效请求
- `1001 AUTH_INVALID_KEY` — 缺少/无效的 API 密钥

[filled by work orders F04, F06, F09, F14]