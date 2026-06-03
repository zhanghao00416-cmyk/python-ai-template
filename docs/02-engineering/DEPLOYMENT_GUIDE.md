# 部署指南

## 概述

本文档提供了 Python AI Template 的部署框架。涵盖 Docker、Docker Compose、配置管理和生产就绪检查。

## 前置条件 — [TBD: filled by F21]

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 运行时 |
| PostgreSQL | 15+ | 主数据库 |
| Redis | 7+ | 缓存、限流、会话状态 |
| Qdrant | 1.7+ | 向量存储 |

## Docker — [TBD: filled by F21]

### Dockerfile — [TBD: filled by F21]

```dockerfile
FROM python:3.11-slim
# 多阶段构建：builder + runtime
# Builder：安装依赖
# Runtime：复制应用，使用 uvicorn 运行
```

关键要求：
- 多阶段构建以最小化镜像体积
- 运行时使用非 root 用户
- 健康检查端点
- 环境变量注入

### Docker Compose — [TBD: filled by F21]

```yaml
services:
  app:
    build: .
    ports: ["6006:6006"]
    env_file: .env
    depends_on: [postgres, redis, qdrant]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6006/api/v1/health"]

  postgres:
    image: postgres:15
    volumes: [pgdata:/var/lib/postgresql/data]
    environment: ...

  redis:
    image: redis:7-alpine
    volumes: [redisdata:/data]

  qdrant:
    image: qdrant/qdrant:latest
    volumes: [qdrantdata:/qdrant/storage]
```

## 配置管理 — [filled by F01]

### 优先级（高 → 低）

1. `/run/secrets/<name>` 文件 — 参见 `secrets/README.md`（`qwen_api_key`、`api_key`、`jwt_secret`）
2. 环境变量 / 仓库根目录 `.env` — `docker-compose` `env_file: .env`
3. `configs/override.yaml`
4. `configs/default.yaml`

将 `.env.example` 复制为仓库根目录的 `.env`。支持旧版 TestNewHarness 密钥，如 `TEXT_MODEL__QWEN_API_KEY`。

### 必需环境变量 — [TBD: filled by F21]

| 变量 | 说明 | 示例 |
|------|------|------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql+asyncpg://user:pass@localhost:5432/db` |
| `REDIS_URL` | Redis 连接字符串 | `redis://localhost:6379/0` |
| `QDRANT_URL` | Qdrant 连接字符串 | `http://localhost:6333` |
| `QWEN_API_KEY` | Qwen 云端 API 密钥 | `sk-...` |
| `LLM_DEFAULT_CHANNEL` | 默认 LLM 通道 | `qwen_cloud` |
| `AUTH_ENABLED` | 启用 API 密钥认证 | `true` |
| `API_KEYS` | 逗号分隔的 API 密钥 | `key1,key2` |

### 密钥管理

- 本地：`secrets/` → 在 compose 中以只读方式挂载到 `/run/secrets`
- `.env` 在本仓库中被跟踪；`secrets/*` 被忽略（`secrets/README.md` 除外）
- 变量名参见 `.env.example`

## 启动流程 — [TBD: filled by F21]

### 应用启动序列

1. 加载配置（YAML → `.env` → `/run/secrets`；参见 `app/core/config.py`）
2. 初始化 DI 容器
3. 初始化数据库（如已配置则运行迁移）
4. 初始化 Redis 连接
5. 初始化 Qdrant 客户端并创建缺失的集合
6. 加载 Prompt 模板
7. 注册 API 路由
8. 启动 uvicorn 服务器

### 健康检查 — [TBD: filled by F01]

```
GET /api/v1/health
→ { "status": "ok", "version": "...", "uptime": 123.4 }
```

包含依赖健康状态：
- PostgreSQL：ping
- Redis：ping
- Qdrant：健康检查
- LLM：预热调用（可选，由配置驱动）

## 生产就绪检查清单 — [TBD: filled by F21]

- [ ] `feature_list.json` 所有项均为 `passing`
- [ ] 架构检查通过（`scripts/check-architecture.sh`）
- [ ] 所有测试通过（`pytest`）
- [ ] Docker 镜像构建成功
- [ ] `docker-compose up` 启动所有服务
- [ ] 健康检查端点返回 200
- [ ] API 认证正常工作（或开发环境有意禁用）
- [ ] 限流已配置
- [ ] CORS 来源已限制（非 `*`）
- [ ] 日志输出结构化 JSON
- [ ] 密钥未出现在代码或配置文件中
- [ ] 数据库迁移具有幂等性
- [ ] Qdrant 集合在启动时自动创建
- [ ] SSE 流端到端正常工作

## 监控 — [TBD: filled by F18]

- Prometheus 指标位于 `/metrics`
- 结构化 JSON 日志（structlog）
- Trace ID 在所有请求中传播
- 按模型/任务的 Token 使用量追踪

## 扩展考量 — [TBD: filled by F21]

| 关注点 | 策略 |
|--------|------|
| LLM 并发 | 信号量限制（可配置） |
| 数据库连接 | AsyncEngine 连接池（可配置大小） |
| Redis 连接 | 连接池 |
| Qdrant | 通过 Qdrant 集群水平扩展 |
| 应用实例 | 负载均衡后水平扩展 |

[TBD: filled by work orders F01, F18, F21]