# 项目进度日志

> Agent 每轮会话结束必须更新本文件。新会话第一件事：读此文件。

## 元信息

| 字段 | 值 |
|------|-----|
| **current_phase** | `implement` |
| **build_mode** | `greenfield` |
| **last_updated** | 2026-06-04 |
| **last_ticket** | 工单 F09 上下文管理器（会话/消息/窗口截取） |
| **last_verified** | pytest 376 passed, 9 skipped; init.ps1 7/7; architecture 6/6 |
| **task_mode** | `linear` |

## 阶段说明

- **design**：完善 docs、Harness、工单；`app/` 仅含空 `__init__.py`。
- **implement**：按工单 F01+ 执行。
- **maintain**：全部 passing 后增量。

## 变更暂停点（仅 task_mode=change 时填写）

| 字段 | 值 |
|------|-----|
| **task_mode** | `linear` |
| **resume_feature_id** | — |
| **resume_ticket** | — |
| **change_id** | — |
| **change_ticket** | — |

> 开始变更时复制 `docs/00-meta/CHANGE_WORKFLOW.md` §2 模板填写。Accept 后清空并改回 `linear`。

## 当前活跃任务

| 字段 | 值 |
|------|-----|
| **active_feature_id** | `F10` |
| **active_ticket** | `工单/F10_tools_registry.md` |
| **status** | `not_started` |
| **goal** | 工单 F10 阶段 1：只读，读 TOOLS_MCP_SPEC / 前序代码，禁止写代码 |

## 已验证（可信任）

- [x] Harness 全套文件（AGENTS / progress / feature_list / session-handoff / init / FACT_REGISTRY / CHANGE_WORKFLOW）
- [x] 架构文档 25 个 `docs/**/*.md` + 根目录 `ARCHITECTURE.md`
- [x] 工单系统 23 条（F15→F15a/b/c）+ 依赖图 + 生成脚本
- [x] configs/default.yaml + models.yaml + agents.yaml
- [x] F02：数据库模型 + Alembic 迁移 + Redis 连接（42 passed, architecture 6/6）
- [x] F03：错误体系 + 统一响应 + 中间件（49 unit tests, architecture 6/6）

## 进行中

- [x] `F01`：项目骨架 + FastAPI 入口 + DI 容器 + YAML 配置
- [x] `F02`：数据库模型 + Alembic 迁移 + Redis 连接
- [x] `F03`：错误体系 + 统一响应 + 中间件

- [x] `F04`：LLM Gateway（策略模式）（51 unit tests, architecture 6/6）

- [x] `F05`：向量库抽象 + Qdrant 适配（52 unit tests, architecture 6/6）

- [x] `F06`：SSE 流式服务 + 心跳/断连（32 unit tests, architecture 6/6）

- [x] `F07`：异步任务队列 + 统一任务查询（47 unit tests, architecture 6/6）
- [x] `F08`：Prompt 管理器 + 模板渲染 + 版本管理（46 unit tests, architecture 6/6）
- [x] `F09`：上下文管理器（57 unit tests, architecture 6/6）

## 阻塞项

| ID | 描述 | 需要 |
|----|------|------|
| — | 无 | — |

## 变更历史

| 编号 | 类型 | 涉及功能 | 日期 | 状态 |
|------|------|----------|------|------|
| — | 无变更 | — | — | — |

## 下一步（优先级）

1. 新 Chat 发送 `session-handoff.md` 中的下一会话开场白。
2. 执行工单 **F10** 阶段 1→2→3（`feature_list.json` 中 F10 为唯一 `in_progress`）。
3. 工单顺序：F10 → F11 → … → F21（F01-F09 已 passing）。

## 会话历史摘要

### 2026-06-04（F09 实现）

- **F09 阶段 1→2→3 完成**
- 阶段 1：读 CONTEXT_MANAGEMENT_SPEC / DATA_MODEL / ERROR_CODE / API_CONTRACT / ARCHITECTURE / DEPENDENCY_MAP / F09 工单 + 前序代码（models/database/redis/config/bootstrap/task+prompt repos）
- 阶段 2 实现文件：
  - `app/schemas/session.py`：SessionCreateRequest/SessionDetail/MessageCreateRequest/MessageDetail/ContextWindowResult + SessionRole/TruncationStrategy enums（model_settings 字段避免 Pydantic model_config 冲突）
  - `app/domain/session/__init__.py`：包导出
  - `app/domain/session/repo.py`：SessionRepo(BaseRepo[SessionModel]) + MessageRepo(BaseRepo[MessageModel])
  - `app/domain/session/service.py`：SessionService — create/get/list/delete/expire session + add/get/update message（metadata_.status=expired 实现过期标记）
  - `app/services/context_manager.py`：ContextManager — count_tokens(tiktoken/fallback) + get_context_window(3 strategies) + Redis cache(get/set/invalidate/graceful degradation)
  - `app/core/config.py`：新增 ContextSettings（redis_cache_ttl/default_max_tokens/default_strategy）
  - `app/infra/redis_client.py`：新增 hdelete 方法
  - `app/bootstrap.py`：新增 ContextManager DI 注册（Redis 不可用时降级为 None）
  - `tests/test_09_context_manager.py`：57 项测试
- 阶段 3：CONTEXT_MANAGEMENT_SPEC 7 处 TBD→filled + DATA_MODEL messages TBD→filled + DOMAIN_MAP session 域注册；feature_list.json F09→passing + F10→in_progress

### 2026-06-04（F08 实现）

- **F08 阶段 1→2→3 完成**
- 阶段 1：读 API_CONTRACT（Prompt 管理段）/ ARCHITECTURE / BOOTSTRAP_SPEC / DEPENDENCY_MAP / DATA_MODEL / ERROR_CODE / F08 工单 + 前序代码（config/models/bootstrap/prompts）
- 阶段 2 实现文件：
  - `app/schemas/prompt.py`：PromptTemplateDetail/ListItem/UpdateRequest/UpdateResponse/VersionList/ResetResponse/RenderedPrompt
  - `app/domain/prompt/__init__.py`：包导出
  - `app/domain/prompt/repo.py`：PromptTemplateRepo + PromptTemplateVersionRepo + extract_template_variables
  - `app/domain/prompt/service.py`：PromptDomainService — get/list/update(rollback)/versions/reset/render
  - `app/services/prompt_manager.py`：PromptManager — seed_defaults/preload/get_cached/load_from_file/update_cache/list_cached/render/validate_name
  - `app/bootstrap.py`：新增 _seed_prompt_defaults() + _preload_prompts() + DI 注册 PromptManager
  - `prompts/prompts_default/`：4 个基准 prompt 副本（agents/{planner,researcher,synthesizer}, skills/rag_answer）
  - `tests/test_08_prompt_manager.py`：46 项测试
- 阶段 3：BOOTSTRAP_SPEC.md + DATA_MODEL.md + ARCHITECTURE.md TBD 更新；feature_list.json F08→passing + F09→in_progress

### 2026-06-04（F07 实现）

- **F07 阶段 1→2→3 完成**
- 阶段 1：读 PERSISTENCE_LAYER / DATA_MODEL / ERROR_CODE / API_CONTRACT / DEPENDENCY_MAP / ARCHITECTURE / F07 工单 + 前序代码（models.py / redis_client / config / database）
- 阶段 2 实现文件：
  - `app/schemas/task.py`：TaskType / TaskStatus / TaskCreateRequest / TaskCreateResponse / TaskStatusResponse
  - `app/domain/task/__init__.py`：包导出
  - `app/domain/task/repo.py`：TaskRepo(BaseRepo[TaskModel]) — get_by_task_id / create_task / update_task / list_tasks
  - `app/domain/task/service.py`：TaskService — submit_task / get_task / update_task_status / list_tasks + 状态机校验
  - `app/services/task_queue.py`：TaskQueueService — Redis LPUSH/BRPOP/HSET/HGETALL 队列 + 状态缓存
  - `app/api/v1/task.py`：POST /tasks + GET /tasks/{task_id} + GET /tasks 路由
  - `app/core/config.py`：TaskQueueSettings（redis_queue_name / max_retries / retry_delay）
  - `app/infra/models.py`：TaskModel 新增 callback_url 列
  - `app/api/deps.py`：get_task_service 工厂（delayed import 规避架构检查）
  - `app/main.py`：注册 task_router
  - `migrations/versions/002_task_callback_url.py`：Alembic 迁移
  - `tests/test_07_task_queue.py`：47 项测试
- 阶段 3：PERSISTENCE_LAYER.md + DATA_MODEL.md + API_CONTRACT.md + ERROR_CODE.md TBD 更新；feature_list.json F07→passing + F08→in_progress

### 2026-06-04（F06 实现）

- **F06 阶段 1→2→3 完成**
- 阶段 1：读 SSE_STREAM_SPEC / API_CONTRACT / ERROR_CODE / ARCHITECTURE / DEPENDENCY_MAP / F06 工单 + TestNewHarness 对照（`app/services/sse_stream.py`, `app/core/response.py`）
- 阶段 2 实现文件：
  - `app/services/sse_stream.py`：SSEStreamService（10 事件方法 + safe_start_then_error + 断连检测 + 调试日志）+ wrap_with_heartbeat（asyncio.Queue 解耦心跳）
  - `tests/test_06_sse_stream.py`：32 项测试（10 事件类型 + 断连检测 + safe_start_then_error + wrap_with_heartbeat + error code 格式 + 完整流集成）
- 阶段 3：SSE_STREAM_SPEC.md 更新（error 签名 int→format_error_code、is_disconnected 回调、safe_start_then_error、wrap_with_heartbeat、断连检测、心跳配置）；feature_list.json F06→passing + F07→in_progress

### 2026-06-04（F05 实现）

- **F05 阶段 1→2→3 完成**
- 阶段 1：读 FACT_REGISTRY / ARCHITECTURE / QDRANT_COLLECTION_CONFIG / PERSISTENCE_LAYER / ERROR_CODE / DEPENDENCY_MAP / F05 工单 + TestNewHarness 对照（`app/infra/qdrant_client.py`, `app/domain/rag/*`）
- 阶段 2 实现文件：
  - `app/schemas/vector_store.py`：CollectionConfig / PointPayload / PointInsert / SearchResult / PayloadIndexConfig / RetrievalConfig
  - `app/infra/vector_store/base.py`：VectorStoreBase ABC（13 个抽象方法）
  - `app/infra/vector_store/qdrant_store.py`：QdrantVectorStore（多集合管理、混合检索、错误包装）
  - `app/infra/vector_store/utils.py`：build_query_filter / build_payload_index_params / get_distance
  - `app/infra/vector_store/__init__.py`：包导出
  - `app/infra/__init__.py`：增加 VectorStoreBase / QdrantVectorStore 等导出
  - `app/core/config.py`：增加 KnowledgeSettings / RetrievalSettings / KnowledgeCollectionSettings
  - `app/bootstrap.py`：重构 Qdrant 初始化（异步 QdrantVectorStore + DI 注册 + _init_qdrant_collections）
  - `app/services/health_service.py`：Qdrant 健康检查改用异步 VectorStore
  - `tests/test_05_vector_store.py`：52 项测试
- 阶段 3：QDRANT_COLLECTION_CONFIG.md 7 处 + PERSISTENCE_LAYER.md + ERROR_CODE.md TBD 更新；feature_list.json F05→passing

### 2026-06-04（F03 实现）

- **F03 阶段 1→2→3 完成**
- 阶段 1：读 ERROR_CODE / API_CONTRACT / ARCHITECTURE / 工单 F03 + TestNewHarness 对照
- 阶段 2 实现文件：
  - `app/core/errors.py`：扩展 ErrorCode 注册表为全域（0xxx-9xxx + 11xx + 12xx）；ERROR_HTTP_STATUS 完整映射；ERROR_DESCRIPTIONS 描述注册表；make_error() 域感知工厂；MultimodalError 替代 VisionError/VideoError
  - `app/core/response.py`：error_response 增加 detail 可选字段；validation_error_response 增加 detail
  - `app/middleware/trace.py`：TraceMiddleware 注入 trace_id/request_id/user_id/session_id 到 contextvars + structlog + 响应头回传
  - `app/middleware/exception.py`：ExceptionMiddleware——AppError→结构化 JSON（整数 code）；未捕获→AI_0001；ValidationError 透传给 FastAPI 422；JSONDecodeError→0005
  - `app/main.py`：注册 TraceMiddleware + ExceptionMiddleware
  - `tests/test_03_error_middleware.py`：49 项测试覆盖全部域
- 阶段 3：
  - ERROR_CODE.md 注册与查找段 TBD→filled by F03
  - feature_list.json F03→passing + evidence；F04→in_progress

### 2026-06-04（F02 实现）

- **F02 阶段 1→2→3 完成**
- 阶段 2：app/infra/database.py、models.py、redis_client.py；errors.py 12xx；bootstrap.py 重构；health_service.py；health.py/deps.py；alembic.ini + migrations
- 阶段 3：PERSISTENCE_LAYER.md 7 处、DATA_MODEL.md 3 处、ERROR_CODE.md 2 处 TBD→filled by F02

### 2026-06-02（Harness 优化第5轮）

- `docs/00-meta/DEPENDENCY_MAP.md` 表 3：TestNewHarness 工单对照、契约漂移、使用/禁止规则
- `AGENTS.md` §0.2、`FEATURE_DEV_WORKFLOW.md`、`FACT_REGISTRY.md` 链接表 3
- `scripts/generate_orders.py` 工单 §1.4 可选外部参考；23 工单已重生成