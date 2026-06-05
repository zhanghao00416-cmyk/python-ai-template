# 安全策略

## 概述

本文档定义了 Python AI 模板的安全模型，涵盖认证、限流、输入验证和数据保护。安全强制配置位于 `app/middleware/`。

## 认证 — [filled by F20]

### API 密钥认证

```python
# 基于请求头的 API 密钥
X-API-Key: <api_key>
```

- API 密钥以哈希值形式存储在配置中
- 密钥验证在 `app/middleware/auth.py` 中执行
- 开发环境下可通过配置 (`AUTH_ENABLED: false`) 禁用认证
- 禁用时，使用 `X-User-Id` 请求头或配置中的默认 `user_id`

### 密钥存储 — [filled by F20]

- 生产环境：环境变量或 Docker Secrets (`${API_KEYS}`)
- 开发环境：`.env` 文件
- 密钥绝不存储在 YAML 配置文件中，也不提交至版本控制

### 认证中间件 — [filled by F20]

```python
class AuthMiddleware:
    async def __call__(self, request: Request, call_next: Callable):
        """
        1. 检查认证是否启用（配置）
        2. 提取 X-API-Key 请求头
        3. 与已配置的密钥进行验证
        4. 若无效：返回 401 {code: 1001, message: "Unauthorized"}
        5. 若有效：设置 request.state.user_id 并继续
        """
```

### 豁免端点 — [filled by F20]

| 端点 | 原因 |
|------|------|
| GET /api/v1/health | 健康检查 |
| GET /metrics | Prometheus 指标 |

## 限流 — [filled by F20]

### 基于 Redis 的限流

```python
class RateLimiter:
    def __init__(self, redis: RedisClient, config: RateLimitConfig):
        self.redis = redis
        self.config = config

    async def check(self, key: str) -> bool:
        """
        使用 Redis INCR + EXPIRE 实现滑动窗口限流。
        Key: rate_limit:{api_key}:{window}
        未超限返回 True，超限返回 False。
        """
```

### 配置 — [filled by F20]

```yaml
rate_limit:
  enabled: true
  default:
    requests: 100         # 每个窗口最大请求数
    window_seconds: 60    # 窗口时长
  endpoints:
    /api/v1/chat:
      requests: 30
      window_seconds: 60
    /api/v1/kb/query:
      requests: 50
      window_seconds: 60
```

### 限流响应 — [filled by F20]

超出限流时：

```json
{
  "code": 1004,
  "message": "Rate limit exceeded. Retry after 30s.",
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

HTTP 状态码：429 Too Many Requests。

响应头：`Retry-After: 30`、`X-RateLimit-Limit: 100`、`X-RateLimit-Remaining: 0`。

## 输入验证 — [filled by F03]

### Pydantic 模式

所有 API 输入均通过 `app/schemas/` 中的 Pydantic 模型进行验证：

```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: UUID | None = None
    model: str | None = None
    stream: bool = True
```

### 验证规则 — [filled by F03]

| 字段 | 规则 |
|------|------|
| 消息文本 | 最多 10,000 字符，不允许原始 HTML |
| 会话 ID | 有效的 UUID 格式 |
| 集合名称 | 字母数字 + 下划线，最多 64 字符 |
| 文档内容 | 每次上传最大 5MB |
| 提示词名称 | 字母数字 + 下划线，最多 128 字符 |

### 输出清洗 — [filled by F03]

- API 响应中不包含原始堆栈跟踪
- 错误消息通过错误码系统映射
- LLM 输出不做清洗（本模板信任模型输出）

## 请求上下文传播 — [filled by F03]

每个请求必须携带：

| 请求头 | 来源 | 传播至 |
|--------|------|--------|
| `X-Trace-Id` | 自动生成或客户端 | 所有日志、数据库记录 |
| `X-Request-Id` | 自动生成的 UUID | 所有日志、错误响应 |
| `X-User-Id` | 认证中间件 | 所有日志、数据库记录 |
| `X-Session-Id` | 客户端请求 | 所有日志、消息记录 |

这些通过 `app/middleware/trace.py` 设置，并通过 `contextvars` 访问。

## 跨域资源共享 (CORS) — [filled by F01]

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["X-API-Key", "X-Trace-Id", "X-Request-Id", "X-User-Id", "X-Session-Id"],
)
```

## 数据保护 — [filled by F20]

- YAML 配置文件中不含密钥（使用 `.env` 或 Docker Secrets）
- API 密钥比较前先进行哈希处理
- 不记录个人身份信息（user_id 为不透明标识符）
- SSE 流不暴露内部错误细节
- Redis 键设有 TTL（无无限期数据保留）

## 安全响应头 — [filled by F01]

| 响应头 | 值 |
|--------|-----|
| X-Content-Type-Options | nosniff |
| X-Frame-Options | DENY |
| Content-Security-Policy | default-src 'none' |

[filled by work orders F01, F03, F20]