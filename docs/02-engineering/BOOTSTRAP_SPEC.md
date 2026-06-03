# 应用启动编排规范

## 概述

`app/bootstrap.py` 负责应用启动/关闭时的有序初始化和清理。所有基础设施（数据库、Redis、Qdrant、Prompt、知识库种子）的初始化必须通过 bootstrap 编排，禁止散落在各模块的 `@app.on_event` 中。

---

## 启动顺序

```
1. setup_logging()          — structlog JSON 日志初始化
2. init_infra()             — 数据库连接池、Redis 连接、Qdrant 客户端
3. init_qdrant_collections() — 自动创建声明的知识集合 + payload 索引 + 稀疏向量索引
4. seed_prompt_defaults()   — 检查 prompts/ 目录，补缺基准副本到当前目录
5. preload_prompts()         — 预加载所有 prompt 模板到内存缓存
6. init_model_gateways()     — 初始化 LLM Gateway 熔断器 + 信号量
```

### FastAPI 集成

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup()
    yield
    await shutdown()

app = FastAPI(lifespan=lifespan)
```

---

## 关闭顺序

```
1. shutdown_infra()   — 关闭数据库连接池、Redis 连接、Qdrant 客户端
2. 日志：shutdown_complete
```

---

## 各初始化步骤详解

### 1. setup_logging()

- 读取 `logging.level` 配置
- 配置 structlog：JSON 格式、trace_id/request_id/user_id 注入、敏感值脱敏
- 脱敏规则：键名含 secret/password/token/key/auth/credential 时替换为 `***REDACTED***`

### 2. init_infra()

| 组件 | 初始化 | 健康检查 |
|------|--------|----------|
| PostgreSQL | `create_async_engine()` + `async_sessionmaker` | `SELECT 1` |
| Redis | `aioredis.from_url()` | `PING` |
| Qdrant | `QdrantClient(url)` | `GET /healthz` |

失败策略：**启动失败时日志警告但不阻塞**（Qdrant/Redis 可降级运行），数据库失败则阻塞启动。

### 3. init_qdrant_collections()

- 读取 `configs/default.yaml` 的 `knowledge.collections` 配置
- 对每个声明的集合：
  - 检查是否存在，不存在则创建
  - 创建 payload 索引：`doc_type`, `source`, `tag`, `uploader`, `doc_id`
  - 创建稀疏向量索引（BM25）：`sparse_vector_name` = `bm25`
- 失败仅告警，不阻塞启动

### 4. seed_prompt_defaults()

- 扫描 `prompts/prompts_default/` 目录
- 对比 `prompts/` 当前目录
- 缺失的 prompt 文件从基准副本复制
- 新增的 prompt 文件（当前有但基准没有）保留不动

### 5. preload_prompts()

- `PromptLoader` 实例加载所有 `prompts/**/*.md` 文件
- 缓存到内存（`dict[str, str]`）
- 后续调用 `prompt_loader.load(domain, name)` 直接从缓存返回
- **无运行时热更**：改 prompt 文件后需重启进程

### 6. init_model_gateways()

- 创建 4 个熔断器实例：`llm_text`, `llm_vllm`, `multimodal`, `embedding`
- 创建信号量管理器，按配置初始化各信号量
- 注册到 DI 容器

---

## 配置加载顺序

```
优先级（高→低）：
1. 环境变量 / .env
2. Docker Secrets
3. configs/override.yaml
4. configs/default.yaml
```

由 `app/core/config.py` 统一管理，`Settings` 类使用 pydantic-settings 加载。

---

## 健康检查端点

```python
GET /api/v1/health

Response:
{
    "status": "ok",
    "version": "0.1.0",
    "uptime": 123.4,
    "dependencies": {
        "database": "ok",
        "redis": "ok",
        "qdrant": "ok"
    }
}
```

- `status: "degraded"` — 非关键依赖（Redis/Qdrant）不可用
- `status: "error"` — 数据库不可用

---

## 工单映射

- 启动编排由 **F01 项目骨架** 实现 `bootstrap.py`
- `init_qdrant_collections` 由 **F05 向量库** 集成
- `seed_prompt_defaults` 由 **F08 Prompt 管理器** 集成
- `init_model_gateways` 由 **F04 LLM Gateway** 集成