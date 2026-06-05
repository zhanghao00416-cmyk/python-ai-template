# 项目进度日志

> Agent 每轮会话结束必须更新本文件。新会话第一件事：读此文件。

## 元信息

| 字段 | 值 |
|------|-----|
| **current_phase** | `implement` |
| **build_mode** | `greenfield` |
| **last_updated** | 2026-06-05 |
| **last_ticket** | 工单 F21 端到端联调+Docker+生产就绪 |
| **last_verified** | pytest tests/ 817 passed 10 skipped; F21 deployment implemented; Dockerfile multi-stage + non-root + HEALTHCHECK; docker-compose 4 services with healthchecks; init.ps1 7/7; architecture 6/6
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
| **active_feature_id** | `—` |
| **active_ticket** | `—` |
| **status** | `all_passing` |
| **goal** | F01-F21 全部 passing。项目进入 maintain 阶段。如需新增功能，请走变更流程。 |

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
- [x] `F10`：Tools 注册中心 + MCP 适配器 + Skills（64 unit tests, architecture 6/6）
- [x] `F11`：Agent 基类 + 状态机 + ReAct 循环（64 unit tests, architecture 6/6）
- [x] `F12`：多 Agent 协作 Orchestrator 模式（49 unit tests, 全量 553 passed, architecture 6/6）
- [x] `F13`：Workflow DAG 引擎（54 unit tests, 全量 607 passed, 9 skipped, architecture 6/6）
- [x] `F14`：Chat 对话域（16 测试通过，全量 623 passed, 9 skipped, architecture 6/6）
- [x] `F15a`：知识库集合+文档管理（40 测试通过，全量 663 passed, 9 skipped, architecture 6/6）
- [x] `F15b`：知识库RAG查询（14 测试通过，全量 677 passed, 9 skipped, architecture 6/6）
- [x] `F15c`：知识库端到端联调（4 测试通过，全量 681 passed, 9 skipped, architecture 6/6）
- [x] `F16`：意图识别域（28 测试通过，全量 709 passed, 9 skipped, architecture 6/6）
- [x] `F17`：Prompt 管理 API（14 测试通过，全量 723 passed, 9 skipped, architecture 6/6）
- [x] `F18`：可观测性体系（11 测试通过，全量 734 passed, 9 skipped, architecture 6/6）
- [x] `F19`：评估框架（46 测试通过，全量 780 passed, 9 skipped, architecture 6/6）
- [x] `F20`：认证+限流中间件（11 测试通过，1 skipped；架构合规 6/6；ruff check 通过）
- [x] `F21`：端到端联调+Docker+生产就绪（26 测试通过；多阶段 Dockerfile + compose 4 服务 + healthcheck 链 + LLM 状态；架构合规 6/6）

## 阻塞项

| ID | 描述 | 需要 |
|----|------|------|
| — | 无 | — |

## 变更历史

| 编号 | 类型 | 涉及功能 | 日期 | 状态 |
|------|------|----------|------|------|
| CO-001 | hotfix | F09 context YAML 配置字段名修复 | 2026-06-04 | done |

## 下一步（优先级）

1. F01-F21 全部 passing，项目进入 **maintain** 阶段。
2. 如需新增功能：走变更流程（`docs/00-meta/CHANGE_WORKFLOW.md`）。
3. 如需修复 bug：走 hotfix 流程。

## 会话历史摘要

### 2026-06-05（F21 实现）

- **F21 阶段 1→2→3 完成**
- 阶段 1：读 DEPLOYMENT_GUIDE / API_CONTRACT / ARCHITECTURE / DEPENDENCY_MAP / F21 工单 + 前序代码（F01-F20 全部）
- 阶段 1 交付物：差异清单（Dockerfile 需多阶段+非 root/compose 需 app healthcheck/health 需 LLM 状态/DEPLOYMENT_GUIDE 全篇 TBD）、错误码无新增、预计文件清单（5 修改 + 1 新增测试 + 1 文档回填）、不做范围确认（不改业务代码/不走变更单）
- 阶段 2 实现文件：
  - `Dockerfile`：多阶段构建（builder+runtime）、非 root 用户（appuser:appgroup）、HEALTHCHECK 指令（curl `/api/v1/health`）
  - `docker-compose.yml`：app 服务 healthcheck + depends_on conditions（service_healthy/service_started）+ 只读 volumes（configs/prompts/secrets:ro）+ qdrant 版本锁定 v1.8.0
  - `app/services/health_service.py`：新增 `check_llm()` 返回熔断器状态（qwen_cloud/vllm channels）
  - `app/api/v1/health.py`：响应包含 `dependencies.llm`（channels + status）
  - `tests/test_f21_deployment.py`：26 项测试（Dockerfile 5 项/compose 6 项/env 4 项/health 5 项/生产就绪 6 项）
  - `docs/02-engineering/DEPLOYMENT_GUIDE.md`：8 处 `[TBD: filled by F21]` → `[filled by F21]`
- 阶段 3：evaluator-rubric.md F21 Accept；feature_list.json F21→passing（全部 22/22 passing）；progress.md 更新（active→全部完成，进入 maintain）；session-handoff.md 更新；init.ps1 7/7 通过；817 total tests pass

### 2026-06-05（F20 实现）

- **F20 阶段 1→2→3 完成**
- 阶段 1：读 API_CONTRACT / ERROR_CODE / ARCHITECTURE / DEPENDENCY_MAP / SECURITY_POLICY / F20 工单 + 前序代码（F02 redis_client.py + F03 middleware）
- 阶段 1 交付物：差异清单（RedisClient 缺 expire/配置缺限流段/中间件顺序需调整/错误码已预定义但 docs 未同步/无 API surface 新增）、错误码与边界条件（1001/1004/0006）、预计文件清单（8 新增/修改）、不做范围确认、TestNewHarness 无对照素材
- 阶段 2 实现文件：
  - `app/infra/redis_client.py`：新增 `expire(key, seconds)` 方法
  - `app/core/config.py`：新增 `RateLimitSettings` + `RateLimitEndpointSettings` 类，挂入 `Settings`
  - `configs/default.yaml`：新增 `rate_limit` 配置段（enabled/default/endpoints/exempt_paths）
  - `app/middleware/auth.py`：API Key 认证中间件（X-API-Key 校验、enable_auth=false 绕过、豁免路径、request.state.user_id 设置、401 code 1001）
  - `app/middleware/rate_limit.py`：Redis 滑动窗口限流中间件（INCR+EXPIRE、端点覆盖、IP/Key 双标识、429 响应含 Retry-After/X-RateLimit-* 头、Redis 不可用降级）
  - `app/middleware/__init__.py`：导出 auth_middleware + rate_limit_middleware
  - `app/main.py`：调整中间件注册顺序（TraceMiddleware → auth → rate_limit → exception → metrics）
  - `tests/test_20_auth_ratelimit.py`：12 项测试（auth：缺失/无效/禁用/豁免；rate_limit：低于限制/超过限制/IP 标识/禁用/Redis 降级/豁免；E2E：health/metrics 豁免）
- 阶段 3：evaluator-rubric.md F20 Accept；ERROR_CODE.md + SECURITY_POLICY.md TBD→filled by F20；feature_list.json F20→passing + F21→in_progress；progress.md 更新（active→F21）；session-handoff.md 更新

### 2026-06-05（F19 实现）

- **F19 阶段 1→2→3 完成**
- 阶段 1：读 API_CONTRACT / ERROR_CODE / ARCHITECTURE / DEPENDENCY_MAP / F19 工单 + 前序代码（F11 base.py/state.py/trajectory.py/react.py/orchestrator.py, F13 workflow engine/registry, domain agent_orchestration service/repo, schemas agent/workflow）
- 阶段 2 实现文件：
  - `app/schemas/eval.py`：EvalDimension/EvalGrade/EvalScore/TrajectoryEvalResult/DialogueQualityResult/EvalReport
  - `app/eval/metrics.py`：对话质量指标（response_relevance/response_conciseness/citation_accuracy/dialogue_turn_balance）+ CJK 字符支持
  - `app/eval/trajectory_eval.py`：轨迹评测（state_transition_validity/tool_call_success_rate/loop_detection/step_efficiency/trajectory_completeness）+ tool failure 通过 OBSERVING 步骤查找
  - `app/eval/runner.py`：EvalRunner（run_trajectory_eval/run_dialogue_eval/run_batch）+ _to_grade 分级映射
  - `app/eval/__init__.py`：包导出 EvalRunner + 所有指标函数
  - `tests/test_19_eval.py`：46 项测试（对话质量 4 维度/轨迹 5 维度/runner 批量/边界条件）
- 阶段 3：evaluator-rubric.md F19 Accept；feature_list.json F19→passing + F20→in_progress；progress.md 更新（active→F20）；session-handoff.md 更新

### 2026-06-05（F18 实现）

- **F18 阶段 1→2→3 完成**
- 阶段 1：读 API_CONTRACT / ERROR_CODE / ARCHITECTURE / DEPENDENCY_MAP / F18 工单 + 前序代码（F03 logging/tracing + F04 gateway）
- 阶段 2 实现文件：
  - `app/core/metrics.py`：Prometheus Registry + 10 项指标定义（llm_request_total/llm_request_duration_seconds/llm_tokens_total/llm_circuit_breaker_state/http_request_total/http_request_duration_seconds/kb_document_count/kb_query_duration_seconds/agent_step_total/agent_step_duration_seconds）+ 6 个 record_* helper + get_metrics_response()
  - `app/middleware/metrics.py`：HTTP 指标中间件，记录请求计数 + 延迟
  - `app/api/v1/metrics.py`：GET /metrics 路由，返回 Prometheus 文本格式
  - `app/main.py`：注册 metrics_router 和 metrics_middleware
  - `app/services/llm/gateway.py`：generate/generate_stream 注入 llm_request_total/llm_request_duration_seconds/llm_tokens_total/llm_circuit_breaker_state 指标 + 结构化日志含 duration/token_usage
  - `app/infra/vector_store/qdrant_store.py`：search/hybrid_search/_sparse_search 注入 kb_query_duration_seconds；get_collection_info 注入 kb_document_count
  - `app/agent/base.py` + `app/agent/react.py`：ReAct 循环每步注入 agent_step_total + agent_step_duration_seconds
  - `tests/test_18_observability.py`：11 项测试（/metrics 端点/10 项指标存在性/HTTP 请求记录/LLM generate+stream+失败/KB 查询+文档数/Agent 步数/无 prometheus 降级）
- 阶段 3：feature_list.json F18→passing + F19→in_progress；progress.md 更新；session-handoff.md 更新；API_CONTRACT.md TBD→filled by F18

### 2026-06-05（F16 实现）

- **F16 阶段 1→2→3 完成**
- 阶段 1：读 API_CONTRACT / ERROR_CODE / ARCHITECTURE / DEPENDENCY_MAP / F16 工单 + 前序代码（F04 LLM Gateway + F08 PromptManager）
- 阶段 2 实现文件：
  - `app/schemas/intent.py`：IntentRequest/IntentResponse/IntentResultData/SubIntent/RoutingInfo
  - `app/domain/intent/service.py`：IntentDomainService（三层漏斗 L1 keyword → L2 similarity → L3 LLM）+ KeywordMatcher + SimilarityMatcher + LLMClassifier；多意图检测 + query 重组；降级策略（chat fallback）
  - `app/api/v1/intent.py`：POST /api/v1/intent 路由
  - `prompts/intent/classify.md`：LLM 分类 prompt 模板
  - `configs/default.yaml`：追加 intent 配置段（keyword rules / similarity representatives / llm / multi_intent）
  - `app/core/config.py`：Settings 新增 `intent: dict[str, Any]` 字段
  - `app/main.py`：注册 intent_router
  - `tests/test_16_intent.py`：28 项测试（L1/L2/L3/多意图/降级/边界/API）
- 阶段 3：INTENT_ROUTING_SPEC.md + API_CONTRACT.md TBD→filled；evaluator-rubric.md F16 Accept；feature_list.json F16→passing + F17→in_progress；progress.md 更新；session-handoff.md 更新

### 2026-06-05（F17 实现）

- **F17 阶段 1→2→3 完成**
- 阶段 1：读 API_CONTRACT / ERROR_CODE / ARCHITECTURE / DEPENDENCY_MAP / F17 工单 + 前序代码（F08 Prompt 管理器全部实现）
- 阶段 2 实现文件：
  - `app/api/v1/prompt.py`：Prompt 管理 API 路由（GET /api/v1/prompts 列表/详情, PUT /api/v1/prompts/{name} 修改/回滚, GET /api/v1/prompts/{name}/versions 版本历史, POST /api/v1/prompts/{name}/reset 重置基准）
  - `app/main.py`：注册 prompt_router
  - `tests/test_17_prompt_admin.py`：14 项测试（列表/详情/修改/回滚/版本历史/重置/错误/API 路由）
- 阶段 3：API_CONTRACT.md TBD→filled；evaluator-rubric.md F17 Accept；feature_list.json F17→passing + F18→in_progress；progress.md 更新；session-handoff.md 更新

### 2026-06-05（F15c 实现）

- **F15c 阶段 1→2→3 完成**
- 阶段 1：读 API_CONTRACT / ERROR_CODE / ARCHITECTURE / DEPENDENCY_MAP / F15c 工单 + 前序代码（F15a + F15b 全部实现）
- 阶段 2 实现文件：
  - `tests/test_15c_knowledge_e2e.py`：4 项 E2E 测试
    - `test_e2e_full_lifecycle_happy_path`：service 层全流程（create_collection→ingest_document→query_rag/sync+stream→list_documents→preview_delete→delete_documents→delete_collection）
    - `test_e2e_query_empty_collection`：空集合 RAG 查询返回无结果提示
    - `test_api_e2e_full_lifecycle`：API 层全流程（POST/GET/DELETE collections + POST/GET/DELETE documents + POST query sync+stream）
    - `test_api_e2e_query_error`：RAG_RETRIEVAL_FAILED 错误处理验证
- 阶段 3：feature_list.json F15c→passing + F16→in_progress；progress.md 更新；session-handoff.md 更新

### 2026-06-04（F13 实现）

- **F13 阶段 1→2→3 完成**
- 阶段 1：读 WORKFLOW_SPEC / API_CONTRACT / ERROR_CODE / ARCHITECTURE / DEPENDENCY_MAP / F13 工单 + 前序代码（config/bootstrap）
- 阶段 2 实现文件：
  - `app/workflow/engine.py`：StateGraph + Edge + ConditionalEdge + NodeExecutionResult + WorkflowEngine（Kahn 拓扑排序、条件分支路由、并行执行、循环检测）
  - `app/workflow/registry.py`：WorkflowRegistry（register/register_from_yaml/get/match/list_workflows）+ YAML 加载
  - `app/workflow/__init__.py`：包导出
  - `app/schemas/workflow.py`：WorkflowNodeStatus/WorkflowStatus StrEnum + WorkflowRunRequest/WorkflowNodeResult/WorkflowRunResponse/WorkflowStatusDetail
  - `app/core/config.py`：WorkflowSettings
  - `app/api/v1/workflow.py`：POST /api/v1/workflow/run + GET /api/v1/workflow/runs/{task_id}
  - `app/api/deps.py`：get_workflow_registry 工厂
  - `app/main.py`：注册 workflow_router
  - `app/bootstrap.py`：WorkflowRegistry DI 注册 + YAML 自动加载
  - `tests/test_13_workflow.py`：54 项测试
- 阶段 3：WORKFLOW_SPEC.md 3 处 TBD→filled；evaluator-rubric.md F13 Accept；feature_list.json F13→passing + F14→in_progress

### 2026-06-04（F12 实现）

- **F12 阶段 1→2→3 完成**
- 阶段 1：读 AGENT_SPEC / API_CONTRACT / ERROR_CODE / ARCHITECTURE / DEPENDENCY_MAP / F12 工单 + 前序代码（base.py/state.py/react.py/trajectory.py/service.py/agent.py/agents.yaml）
- 阶段 2 实现文件：
  - `app/agent/orchestrator.py`：OrchestratorAgent(BaseAgent) + SubTask/SubTaskResult dataclass + DebateStrategy/DebateRound/DebateResult
  - `app/agent/__init__.py`：导出 OrchestratorAgent + 5 个新符号
  - `app/domain/agent_orchestration/service.py`：_create_engine() 支持 orchestrator + _build_sub_agents() + _load_orchestrator_config()
  - `tests/test_12_multi_agent.py`：49 项测试
- 阶段 3：AGENT_SPEC.md 6 处 F12 TBD→filled + 6 处 F11 TBD→filled；feature_list.json F12→passing + F13→in_progress

### 2026-06-04（F11 实现）

- **F11 阶段 1→2→3 完成**
- 阶段 1：读 AGENT_SPEC / DATA_MODEL / ERROR_CODE / API_CONTRACT / ARCHITECTURE / DEPENDENCY_MAP / F11 工单 + 前序代码（gateway/registry/errors/prompts/react_template）
- 阶段 2 实现文件：
  - `app/agent/state.py`：AgentState 枚举（7 状态）+ 状态转换规则（含自循环）+ transition()
  - `app/agent/trajectory.py`：TokenUsage / ToolCall / TrajectoryEntry / AgentResult 数据模型
  - `app/agent/base.py`：BaseAgent ABC（run/think/act/observe/should_continue）
  - `app/agent/react.py`：ReactAgent ReAct 循环（注入 think_fn、max_iterations、token 累积）
  - `app/agent/__init__.py`：包导出
  - `app/schemas/agent.py`：AgentRunRequest/Response、TrajectoryStep/Detail、AgentConfig
  - `app/domain/agent_orchestration/__init__.py`：包导出
  - `app/domain/agent_orchestration/repo.py`：AgentTrajectoryRepo 持久化层
  - `app/domain/agent_orchestration/service.py`：AgentOrchestrationService 业务编排
  - `app/api/v1/agent.py`：POST /agent/run + GET /agent/trajectories + GET /agent/trajectories/{task_id}
  - `app/main.py`：注册 agent_router
  - `prompts/agents/react_template.md`：ReAct prompt 模板
  - `tests/test_11_agent.py`：64 项测试
- 阶段 3：evaluator-rubric.md 记录 Accept；feature_list.json F11→passing + F12→in_progress

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