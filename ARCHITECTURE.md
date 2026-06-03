# ARCHITECTURE.md

## 1. 项目定位

通用 Python AI 项目模板，脱离具体业务，提供 14 项可复用能力：

1. Chat 对话
2. 知识库管理（可配置集合/类型）
3. Prompt 配置
4. 历史记录与上下文管理
5. Agent（状态机 + ReAct）
6. 多 Agent 协作（Orchestrator + Debate）
7. Workflow（StateGraph DAG）
8. Tools / Skills / MCP
9. 云服务 / vLLM 模型切换
10. 统一配置管理（YAML + .env）
11. 可观测性（structlog + OTel + token 统计）
12. 评估框架（对话质量 + 轨迹评测）
13. API Server（FastAPI + SSE）
14. 异步任务队列（ARQ）

---

## 2. 运行时请求流

```
前端 / Java 中台 / 其他服务
        ↓
FastAPI API 层（请求解析 / 响应包装 / 依赖注入 / SSE 端点）
        ↓
Domain 层（业务编排）
        ↓
Services 层 ⟷ Agent 引擎 / Workflow 引擎 / Tools
        ↓
Infra 层（PG / Redis / Qdrant / LLM Gateway）
        ↓
PostgreSQL | Redis | Qdrant | Qwen Cloud API | vLLM
```

---

## 3. 强制工程分层

```
app/
├── main.py
├── api/          # FastAPI 路由器（纯薄层）
├── core/         # 全局内核（配置/错误/枚举/DI/日志/指标）
├── middleware/   # 跨切面中间件
├── schemas/      # Pydantic 请求/响应模型
├── domain/       # 业务领域编排 + repo
├── agent/        # Agent 引擎（独立于业务）
├── workflow/     # Workflow 引擎（独立于业务）
├── tools/        # 独立能力层（@tool/@skill/MCP）
├── services/     # 可复用业务服务（LLM/SSE/context/prompt/task）
├── infra/        # 外部提供者抽象 + 工程基础设施
├── eval/         # 评估框架
├── prompts/      # Prompt 文件加载器
└── utils/        # 小型无状态助手
```

### 各层职责

#### api/

FastAPI 路由器层。请求解析 / 响应包装 / 依赖注入 / SSE 端点暴露。

禁止：业务逻辑 / 原始模型调用 / 原始数据库调用。

#### core/

全局应用内核。配置 / DI 容器 / 常量 / 错误注册表 / 枚举 / contextvars / 响应模板 / 日志 / 指标 / 追踪。

没有业务实现。

#### middleware/

跨切面请求中间件。异常拦截 / trace 注入 / 认证 / 限流。

不允许领域逻辑。

#### schemas/

仅 Pydantic 请求/响应模型。API 契约 / DTO / 业务响应 schema。

没有可执行业务逻辑。

#### domain/

纯业务领域编排——仓库的语义中心。每个业务领域一个子目录，含 service.py 和 repo.py。

领域不能直接触碰提供者 SDK 实现。repo 继承 infra/database.py 的 BaseRepo。

#### agent/

Agent 引擎，独立于业务。Agent 抽象基类 / 状态机 / ReAct 循环 / 规划器 / 协作策略。

 agent 不直接访问数据库（必须经 domain/repo）。

#### workflow/

Workflow 引擎，独立于业务。StateGraph DAG 执行器 / 节点定义 / 工作流注册。

#### tools/

独立能力层。@tool / @skill 装饰器注册 + MCP 协议适配 + 内置工具。

不专属 agent，API / domain / workflow 均可调用。

#### services/

可复用业务执行服务。LLM Gateway / SSE 流式 / 上下文管理 / Prompt 管理 / 任务队列。

服务向领域提供可共享能力。

#### infra/

统一承载外部提供者抽象与工程基础设施。

PostgreSQL AsyncEngine + BaseRepo / Redis / Qdrant / 熔断器 / 信号量。

没有 FastAPI 依赖。没有领域逻辑。

#### eval/

评估框架。对话质量指标 / Agent 轨迹评测 / 评估执行器。

---

## 4. 依赖方向规则

```
api → domain → services → infra
api → schemas
api → tools（只注册调用）
domain → agent（编排调用引擎）
domain → workflow（编排调用引擎）
domain → tools（使用工具）
agent → tools, services
workflow → tools, services
services → infra
core 全局共享
schemas 由 api/domain 共享

禁止：
  api → infra 直接
  domain → LLM provider 直接（必须经 services/llm/gateway）
  绕过 model gateway
  agent → domain repo 直接
  循环依赖
```

---

## 5. 提供者抽象规则

所有第三方提供者必须被包装：

- LiteLLM / OpenAI 客户端 → services/llm/gateway
- Qdrant SDK → infra/vector_store
- PostgreSQL → infra/database (BaseRepo)
- Redis → infra/redis_client

每个提供者必须有一个统一的网关/仓储抽象。

原因：提供者切换 / 超时治理 / 熔断器插入 / 可观测性插入 / 测试替换。

---

## 6. 并发控制规则

AI 推理任务是重型的。以下操作必须始终受信号量保护：

- 文本 LLM 生成
- 多模态生成
- 批量 embedding 生成

不允许无限制的 async fanout。

---

## 7. 流式响应规则

SSE 端点基于 SSE-starlette。

- SSE 格式化必须在 services/sse_stream 保持隔离
- 需要心跳事件
- 需要断开检测
- 领域服务返回语义块，而非原始 EventSourceResponse 体

业务代码不能被传输细节污染。

---

## 8. 失败治理规则

所有外部依赖失败必须被规范化。没有原始堆栈跟踪到客户端。

```
提供者异常 → 网关规范化 → 业务错误映射 → API 结构化响应
```

熔断器和超时包装器插入在网关边界。

---

## 9. 可观测性规则

每个请求必须携带：trace_id / request_id / user_id / session_id

每个提供者调用必须日志：依赖名称 / 延迟 / 成功或失败 / token 用量。

LLM Gateway 统一收口 token 统计：每次调用自动记录 input_tokens / output_tokens / model / task_type / user_id。

---

## 10. 知识库规则

- 多集合支持，集合配置从 configs/default.yaml 加载
- 启动时自动创建声明的集合（含 payload 索引 + 稀疏向量索引）
- 支持动态创建/删除集合
- RAG 检索支持按集合/类型/类别多维过滤
- 类型/类别为可配置维度，不在代码中硬编码
- 仅支持 markdown 文档
- Prompt 文件位于 prompts/，Python 代码仅从文件加载

---

## 11. Agent / Workflow 规则

Agent 引擎和 Workflow 引擎独立于业务：
- agent/ 提供引擎能力（状态机 / ReAct / 协作策略）
- workflow/ 提供编排能力（StateGraph DAG / 条件边 / 并发节点）
- domain/ 负责业务编排，调用 agent 和 workflow 引擎
- Agent 轨迹（TrajectoryEntry）统一记录，接入评估框架

---

## 12. DI 容器规则

使用 app/core/di.py 轻量容器：
- register(cls, factory, singleton=True) 注册
- resolve(cls) 解析依赖
- override(cls, factory) 测试时替换
- 和 FastAPI Depends 配合，api/deps.py 做桥接

---

## 13. 配置管理规则

优先级（高→低）：

`/run/secrets` 文件 → 环境变量 / 仓库根 `.env` → `configs/override.yaml` → `configs/default.yaml`

复杂配置（模型路由/agent角色/知识库集合）用 YAML。
密钥用 .env 或 Docker Secrets，不写入 YAML。

---

## 14. 仓库增长规则

添加新业务功能时：

- 优先添加新域包
- 尽可能保持网关抽象不变
- 避免修改不相关的稳定模块
- 保持分层

本仓库必须通过有界模块增长，而不是不受控制的文件扩展。

---

## 15. 启动编排规则

所有基础设施初始化必须通过 `app/bootstrap.py` 编排，禁止散落在各模块。

启动顺序：

```
1. setup_logging()            — structlog JSON 日志
2. init_infra()               — PG / Redis / Qdrant 连接
3. init_qdrant_collections()  — 自动创建声明的知识集合 + 索引
4. seed_prompt_defaults()     — Prompts 基准副本补缺
5. preload_prompts()           — 预加载 Prompt 模板到内存
6. init_model_gateways()       — 熔断器 + 信号量
```

关闭顺序：

```
1. shutdown_infra() — 关闭连接池
2. 日志完成
```

详见 `docs/02-engineering/BOOTSTRAP_SPEC.md`。

---

## 16. 熔断器与降级规则

LLM Gateway 集成熔断器（三态：closed/open/half_open），按通道独立：

| 通道 | 熔断器实例 | 降级行为 |
|------|-----------|----------|
| qwen_cloud 文本 | `llm_text` | 降级到 vllm |
| vllm 文本 | `llm_vllm` | 返回 AI_1102 |
| 多模态 | `multimodal` | 返回 AI_1104 或 AI_1102 |
| Embedding | `embedding` | 返回 AI_1102 |

配置见 `configs/default.yaml` circuit_breaker 段。

文本通道降级由 Gateway 自动处理：qwen_cloud 熔断时切换到 vllm。

详见 `docs/02-engineering/CIRCUIT_BREAKER_SPEC.md`。

---

## 17. 模型网关按任务分流规则

LLM Gateway 支持**按任务类型选择通道和模型**，配置在 `configs/models.yaml` 的 routing 段：

```yaml
routing:
  intent:        { provider: qwen_cloud, model: qwen-plus }
  rag_rewrite:   { provider: qwen_cloud, model: qwen-plus }
  rag_merge:     { provider: qwen_cloud, model: qwen-plus }
  final:         { provider: qwen_cloud, model: qwen-plus, stream: true }
  chat:          { provider: qwen_cloud, model: qwen-plus, stream: true }
  multimodal:    { provider: qwen_cloud, model: qwen-vl-plus }
  embedding:     { provider: qwen_cloud, model: text-embedding-v3 }
```

每个任务类型可独立配置 provider、model、timeout、stream。未配置的任务类型继承 default 段。

代码调用模式：

```python
result = await gateway.text_chat(messages, stream=True, task=TextTask.INTENT)
```

Gateway 内部根据 task 参数查询 routing 配置，选择对应的 provider + model。

---

## 18. SSE 流式服务规则

SSE 格式化逻辑完全封装在 `app/services/sse_stream.py`，业务域只调用语义方法：

```python
sse = SSEStreamService(intent="chat", user_id=uid, session_id=sid)
async for event in sse.start():   yield event
async for event in sse.chunk(t):  yield event
async for event in sse.done():    yield event
```

10 种事件类型：start / intent / chunk / structured / citation / heartbeat / progress / usage / done / error

详见 `docs/02-engineering/SSE_STREAM_SPEC.md`。

---

## 19. JSON 修复服务

LLM 输出经常包含不规范 JSON（markdown 代码块包裹、多余逗号、单引号等）。

`app/services/json_repair.py` 提供统一修复：

- 剥离 markdown 代码块标记（```json ... ```）
- 修复常见 JSON 语法错误
- 尾部逗号、单引号、注释处理
- 修复失败返回 None，调用方走错误路径

所有 domain 层解析 LLM JSON 输出的地方必须使用此服务，不允许自行 `json.loads`。

---

## 20. Citation 构建服务

`app/services/citation_sources.py` 从检索结果统一构建引用：

- 输入：`list[SearchResult]`
- 输出：`list[dict]`（filename, chunk_text, score 等去重后字段）
- 去重逻辑：按 filename 去重，保留最高分
- 域层只需 `build_citation_sources(results)`

---

## 21. 引用处理服务

`app/services/image_processor.py` 提供：

- 异步下载图片 → 降分辨率 → 转 base64
- 配置化最大像素、最小边长、超时
- 处理失败统一抛 `AppError`（AI_4001 等）

---

## 22. 修改 vs 新建规则

| 场景 | 操作 |
|------|------|
| 修改 not_started 工单，改动 ≤ 30% | 修改原工单 |
| 修改 not_started 工单，改动 > 30% | 关闭原工单，新开工单 |
| 修改 active 工单 | 直接修改原工单 |
| 修改 passing 功能的代码 | **禁止**，必须走变更流程（见 `docs/00-meta/CHANGE_WORKFLOW.md`） |
| 需求变更影响 passing 功能 | 新建变更单 |
| 新增计划外功能 | 新开工单，编号递增 |

新业务必须先在 docs/ 下补齐事实文档，再写工单。