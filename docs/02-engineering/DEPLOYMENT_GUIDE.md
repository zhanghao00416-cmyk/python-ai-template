# Deployment Guide

## Overview

This document provides the framework for deploying the Python AI Template. It covers Docker, Docker Compose, configuration management, and production readiness checks.

## Prerequisites — [TBD: filled by F21]

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.11+ | Runtime |
| PostgreSQL | 15+ | Primary database |
| Redis | 7+ | Caching, rate limiting, session state |
| Qdrant | 1.7+ | Vector store |

## Docker — [TBD: filled by F21]

### Dockerfile — [TBD: filled by F21]

```dockerfile
FROM python:3.11-slim
# Multi-stage build: builder + runtime
# Builder: install dependencies
# Runtime: copy app, run with uvicorn
```

Key requirements:
- Multi-stage build for minimal image size
- Non-root user for runtime
- Health check endpoint
- Environment variable injection

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

## Configuration Management — [filled by F01]

### Priority (High → Low)

1. `/run/secrets/<name>` files — see `secrets/README.md` (`qwen_api_key`, `api_key`, `jwt_secret`)
2. Environment variables / repo-root `.env` — `docker-compose` `env_file: .env`
3. `configs/override.yaml`
4. `configs/default.yaml`

Copy `.env.example` → `.env` at repo root. Legacy TestNewHarness keys such as `TEXT_MODEL__QWEN_API_KEY` are supported.

### Required Environment Variables — [TBD: filled by F21]

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@localhost:5432/db` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `QDRANT_URL` | Qdrant connection string | `http://localhost:6333` |
| `QWEN_API_KEY` | Qwen Cloud API key | `sk-...` |
| `LLM_DEFAULT_CHANNEL` | Default LLM channel | `qwen_cloud` |
| `AUTH_ENABLED` | Enable API key auth | `true` |
| `API_KEYS` | Comma-separated API keys | `key1,key2` |

### Secrets

- Local: `secrets/` → mounted read-only to `/run/secrets` in compose
- `.env` is tracked in this repo; `secrets/*` stays ignored (except `secrets/README.md`)
- See `.env.example` for variable names

## Startup Procedure — [TBD: filled by F21]

### Application Startup Sequence

1. Load configuration (YAML → `.env` → `/run/secrets`; see `app/core/config.py`)
2. Initialize DI container
3. Initialize database (run migrations if configured)
4. Initialize Redis connection
5. Initialize Qdrant client and create missing collections
6. Load prompt templates
7. Register API routes
8. Start uvicorn server

### Health Check — [TBD: filled by F01]

```
GET /api/v1/health
→ { "status": "ok", "version": "...", "uptime": 123.4 }
```

Includes dependency health:
- PostgreSQL: ping
- Redis: ping
- Qdrant: health check
- LLM: warm-up call (optional, config-driven)

## Production Readiness Checklist — [TBD: filled by F21]

- [ ] All feature_list.json items are `passing`
- [ ] Architecture check passes (`scripts/check-architecture.sh`)
- [ ] All tests pass (`pytest`)
- [ ] Docker image builds successfully
- [ ] `docker-compose up` starts all services
- [ ] Health endpoint returns 200
- [ ] API authentication works (or intentionally disabled for dev)
- [ ] Rate limiting is configured
- [ ] CORS origins are restricted (not `*`)
- [ ] Logging outputs structured JSON
- [ ] Secrets are not in code or config files
- [ ] Database migrations are idempotent
- [ ] Qdrant collections are auto-created on startup
- [ ] SSE streaming works end-to-end

## Monitoring — [TBD: filled by F18]

- Prometheus metrics at `/metrics`
- Structured JSON logging (structlog)
- Trace ID propagation through all requests
- Token usage tracking per model/task

## Scaling Considerations — [TBD: filled by F21]

| Concern | Strategy |
|---------|----------|
| LLM concurrency | Semaphore-limited (configurable) |
| DB connections | AsyncEngine pool (configurable size) |
| Redis connections | Connection pool |
| Qdrant | Horizontal scaling via Qdrant cluster |
| App instances | Horizontal scaling behind load balancer |

[TBD: filled by work orders F01, F18, F21]