# Security Policy

## Overview

This document defines the security model for the Python AI Template, covering authentication, rate limiting, input validation, and data protection. Security enforcement is configured in `app/middleware/`.

## Authentication — [TBD: filled by F20]

### API Key Authentication

```python
# Header-based API key
X-API-Key: <api_key>
```

- API keys are stored as hashed values in configuration
- Key validation occurs in `app/middleware/auth.py`
- Authentication can be disabled via config (`AUTH_ENABLED: false`) for development
- When disabled, a default `user_id` is used from `X-User-Id` header or config

### Key Storage — [TBD: filled by F20]

- Production: Environment variables or Docker Secrets (`${API_KEYS}`)
- Development: `.env` file
- Keys are never stored in YAML config files or committed to version control

### Auth Middleware — [TBD: filled by F20]

```python
class AuthMiddleware:
    async def __call__(self, request: Request, call_next: Callable):
        """
        1. Check if auth is enabled (config)
        2. Extract X-API-Key header
        3. Validate against configured keys
        4. If invalid: return 401 {code: 1001, message: "Unauthorized"}
        5. If valid: set request.state.user_id and continue
        """
```

### Exempt Endpoints — [TBD: filled by F20]

| Endpoint | Reason |
|----------|--------|
| GET /api/v1/health | Health check |
| GET /metrics | Prometheus metrics |

## Rate Limiting — [TBD: filled by F20]

### Redis-Based Rate Limiting

```python
class RateLimiter:
    def __init__(self, redis: RedisClient, config: RateLimitConfig):
        self.redis = redis
        self.config = config

    async def check(self, key: str) -> bool:
        """
        Sliding window rate limit using Redis INCR + EXPIRE.
        Key: rate_limit:{api_key}:{window}
        Returns True if under limit, False if over limit.
        """
```

### Configuration — [TBD: filled by F20]

```yaml
rate_limit:
  enabled: true
  default:
    requests: 100         # Max requests per window
    window_seconds: 60    # Window duration
  endpoints:
    /api/v1/chat:
      requests: 30
      window_seconds: 60
    /api/v1/kb/query:
      requests: 50
      window_seconds: 60
```

### Rate Limit Response — [TBD: filled by F20]

When rate limit is exceeded:

```json
{
  "code": 1004,
  "message": "Rate limit exceeded. Retry after 30s.",
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

HTTP status: 429 Too Many Requests.

Headers: `Retry-After: 30`, `X-RateLimit-Limit: 100`, `X-RateLimit-Remaining: 0`.

## Input Validation — [TBD: filled by F03]

### Pydantic Schemas

All API inputs are validated through Pydantic models in `app/schemas/`:

```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: UUID | None = None
    model: str | None = None
    stream: bool = True
```

### Validation Rules — [TBD: filled by F03]

| Field | Rule |
|-------|------|
| Message text | Max 10,000 characters, no raw HTML |
| Session ID | Valid UUID format |
| Collection name | Alphanumeric + underscore, max 64 chars |
| Document content | Max 5MB per upload |
| Prompt name | Alphanumeric + underscore, max 128 chars |

### Output Sanitization — [TBD: filled by F03]

- No raw stack traces in API responses
- Error messages are mapped through the error code system
- LLM output is not sanitized (trust model output for this template)

## Request Context Propagation — [TBD: filled by F03]

Every request must carry:

| Header | Source | Propagated To |
|--------|--------|--------------|
| `X-Trace-Id` | Auto-generated or client | All logs, DB records |
| `X-Request-Id` | Auto-generated UUID | All logs, error responses |
| `X-User-Id` | Auth middleware | All logs, DB records |
| `X-Session-Id` | Client request | All logs, message records |

These are set via `app/middleware/trace.py` and accessible through `contextvars`.

## CORS — [TBD: filled by F01]

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["X-API-Key", "X-Trace-Id", "X-Request-Id", "X-User-Id", "X-Session-Id"],
)
```

## Data Protection — [TBD: filled by F20]

- No secrets in YAML config files (use `.env` or Docker Secrets)
- API keys hashed before comparison
- No PII logged (user_id is opaque identifier)
- SSE streams do not expose internal error details
- Redis keys have TTL (no indefinite data retention)

## Security Headers — [TBD: filled by F01]

| Header | Value |
|--------|-------|
| X-Content-Type-Options | nosniff |
| X-Frame-Options | DENY |
| Content-Security-Policy | default-src 'none' |

[TBD: filled by work orders F01, F03, F20]