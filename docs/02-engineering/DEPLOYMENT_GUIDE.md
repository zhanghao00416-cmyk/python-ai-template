# 部署指南

## 概述

本文档提供了 Python AI Template 的部署框架。涵盖 Docker、Docker Compose、配置管理和生产就绪检查。

## 前置条件 — [filled by F21]

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 运行时 |
| PostgreSQL | 15+ | 主数据库 |
| Redis | 7+ | 缓存、限流、会话状态 |
| Qdrant | 1.7+ | 向量存储 |

## Docker — [filled by F21]

### Dockerfile — [filled by F21]

多阶段构建（builder + runtime）：
- **builder**：安装编译依赖 + pip install
- **runtime**：复制应用代码，非 root 用户运行，内置 HEALTHCHECK

关键要求：
- 多阶段构建以最小化镜像体积
- 运行时使用非 root 用户（`appuser:appgroup`）
- 健康检查端点：`HEALTHCHECK` 指令每 30s curl `/api/v1/health`
- 环境变量注入：`.env` + `/run/secrets` 挂载

### Docker Compose — [filled by F21]

服务清单：
- **postgres**：PostgreSQL 16，healthcheck `pg_isready`
- **redis**：Redis 7，healthcheck `redis-cli ping`
- **qdrant**：Qdrant v1.8.0，healthcheck `/healthz`
- **app**：FastAPI 应用，依赖上述服务健康就绪后启动

App 服务配置：
- `env_file: .env` — 加载环境变量
- `depends_on` + `condition: service_healthy` — 等依赖就绪
- `healthcheck` — 内置 `/api/v1/health` 检查
- `volumes` — `configs:ro`、`prompts:ro`、`secrets:ro` 只读挂载

## 配置管理 — [filled by F01, refined by F21]

### 优先级（高 → 低）

1. `/run/secrets/<name>` 文件 — 参见 `secrets/README.md`（`qwen_api_key`、`api_key`、`jwt_secret`）
2. 环境变量 / 仓库根目录 `.env` — `docker-compose` `env_file: .env`
3. `configs/override.yaml`
4. `configs/default.yaml`

将 `.env.example` 复制为仓库根目录的 `.env`。支持双下划线格式密钥，如 `TEXT_MODEL__QWEN_API_KEY`。

### 必需环境变量 — [filled by F21]

| 变量 | 说明 | 示例 |
|------|------|------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql+asyncpg://postgres:postgres@localhost:5432/ai_platform` |
| `REDIS_URL` | Redis 连接字符串 | `redis://localhost:6379/0` |
| `QDRANT_URL` | Qdrant 连接字符串 | `http://localhost:6333` |
| `TEXT_MODEL__QWEN_API_KEY` | Qwen 云端 API 密钥 | `sk-...` |
| `TEXT_MODEL__TEXT_MODEL_PROVIDER` | 默认 LLM 通道 | `qwen_cloud` |
| `SECURITY_ENABLE_AUTH` | 启用 API 密钥认证 | `true` / `false` |
| `SECURITY_API_KEY` | API 密钥（若未用 secrets） | `my-secret-key` |
| `LOGGING_LEVEL` | 日志级别 | `INFO` |

### 密钥管理

- 本地：`secrets/` → 在 compose 中以只读方式挂载到 `/run/secrets`
- `.env` 在本仓库中被跟踪；`secrets/*` 被忽略（`secrets/README.md` 除外）
- 变量名参见 `.env.example`

## 启动流程 — [filled by F21]

### 应用启动序列

1. 加载配置（YAML → `.env` → `/run/secrets`；参见 `app/core/config.py`）
2. 初始化 DI 容器（`app/core/di.py`）
3. 初始化数据库（如已配置则运行迁移 `alembic upgrade head`）
4. 初始化 Redis 连接（`app/infra/redis_client.py`）
5. 初始化 Qdrant 客户端并创建缺失的集合（`app/infra/vector_store/`）
6. 加载 Prompt 模板（`app/services/prompt_manager.py` seed + preload）
7. 注册 API 路由（`app/main.py`）
8. 启动 uvicorn 服务器（`uvicorn app.main:app --host 0.0.0.0 --port 6006`）

### 健康检查 — [filled by F01, enhanced by F21]

```
GET /api/v1/health
→ {
  "code": 0,
  "message": "ok",
  "data": {
    "status": "ok | degraded | error",
    "version": "0.1.0",
    "uptime": 123.4,
    "dependencies": {
      "database": { "status": "ok", "latency_ms": 3 },
      "redis": { "status": "ok", "latency_ms": 1 },
      "qdrant": { "status": "ok", "latency_ms": 5, "collections": [...] },
      "llm": { "status": "ok", "channels": { "qwen_cloud": { "status": "ok" }, "vllm": { "status": "open" } } }
    }
  }
}
```

包含依赖健康状态：
- PostgreSQL：ping + latency
- Redis：ping + latency
- Qdrant：list_collections + latency
- LLM：熔断器状态（`ok` / `open` / `half_open` / `unknown`）

## 生产就绪检查清单 — [filled by F21]

- [x] `feature_list.json` 所有项均为 `passing`（22/22）
- [x] 架构检查通过（`scripts/check-architecture.ps1` / `.sh`）
- [x] 所有测试通过（`pytest tests/` — 791 passed, 10 skipped）
- [x] Docker 镜像构建成功（多阶段 + 非 root + HEALTHCHECK）
- [x] `docker-compose up -d` 启动所有服务（含 healthcheck 依赖链）
- [x] 健康检查端点返回 200（含 DB/Redis/Qdrant/LLM 状态）
- [x] API 认证正常工作（X-API-Key，enable_auth 可配置）
- [x] 限流已配置（Redis INCR+EXPIRE，端点覆盖）
- [x] 日志输出结构化 JSON（structlog）
- [x] 密钥未出现在代码或配置文件中（仅 `.env.example` 留空）
- [x] 数据库迁移具有幂等性（Alembic `upgrade head`）
- [x] Qdrant 集合在启动时自动创建（bootstrap `_init_qdrant_collections`）
- [x] SSE 流端到端正常工作（start→chunk→usage→done）

## 监控 — [filled by F18, enhanced by F21]

- Prometheus 指标位于 `/metrics`（`GET /metrics` 返回 Prometheus 文本）
- 10 项指标：LLM（请求数/延迟/token/熔断器状态）、HTTP（请求数/延迟）、KB（文档数/查询延迟）、Agent（步数/延迟）
- 结构化 JSON 日志（structlog）+ Trace ID 传播
- 按模型/任务的 Token 使用量追踪

## 扩展考量 — [filled by F21]

| 关注点 | 策略 |
|--------|------|
| LLM 并发 | 信号量限制（可配置） |
| 数据库连接 | AsyncEngine 连接池（可配置大小） |
| Redis 连接 | 连接池 |
| Qdrant | 通过 Qdrant 集群水平扩展 |
| 应用实例 | 负载均衡后水平扩展 |

[filled by work orders F01, F18, F21]