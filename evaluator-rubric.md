# 评审评分表

在功能实现完成后、标记 passing 之前，用这张表做一次评审。

## 评分维度

| 维度 | 问题 | 分数 (0-2) | 备注 |
|------|------|-----------|------|
| **正确性** | 实现出来的行为是否符合目标功能？ |  |  |
| **验证** | 验证命令是否真的跑过并留下证据？ |  |  |
| **范围纪律** | 这一轮是否基本保持在选定功能范围内？是否扩大了范围？ |  |  |
| **可靠性** | 重启或重跑后，结果是否能继续工作？ |  |  |
| **可维护性** | 代码和文档是否清楚到足以交给下一轮会话？ |  |  |
| **交接准备度** | 新会话是否能只靠仓库内工件（不靠聊天记录）继续推进？ |  |  |
| **分层合规** | 依赖方向是否遵守 ARCHITECTURE.md？是否出现 api→infra 等违禁依赖？ |  |  |
| **错误处理** | 外部依赖失败是否被规范化？是否有原始堆栈到客户端？ |  |  |
| **变更合规** | 若涉及修改已有功能，是否走变更流程？是否同步 docs？ |  |  |

评分标准：
- 0 = 未完成或有明显问题
- 1 = 基本完成但有改进空间
- 2 = 完全满足要求

## 结论

- [ ] **Accept** — 全部维度 ≥ 1，且无维度 = 0
- [ ] **Revise** — 有维度 = 0，需要修补后再评
- [ ] **Block** — 2 个或以上维度 = 0，需要重新设计

## 后续动作

- 缺失的证据：
- 必须补的修复：
- 下次复审触发条件：

## Accept 后必须完成

1. 更新 `progress.md`（含 §7.1 下一任务指针）
2. 更新 `feature_list.json`（状态 + evidence；下一项 `in_progress`）
3. 填写 `session-handoff.md`（含下一会话开场白）
4. 跑 `clean-state-checklist.md` 逐项确认

## 评审记录

| 日期 | F编号 | 评审人 | 结论 | 关键问题 |
|------|-------|--------|------|---------|
| 2026-06-02 | F01 | Agent | Accept | 13/13 pytest；check-architecture.sh 通过 |
| 2026-06-04 | F11 | Agent | Accept | 64/64 pytest；全量 504 passed；架构合规测试通过 |
| 2026-06-04 | F12 | Agent | Accept | 49/49 pytest；全量 553 passed；架构合规 6/6；OrchestratorAgent plan/delegate/synthesize 完整；轨迹记录完整 |
| 2026-06-04 | F13 | Agent | Accept | 54/54 pytest；全量 607 passed, 9 skipped；架构合规 6/6；StateGraph DAG 执行+条件边路由+Kahn 拓扑排序；YAML 注册表；API 端点 2 个；ruff 全通过 |
| 2026-06-05 | F14 | Agent | Accept | 16/16 pytest；全量 623 passed, 9 skipped；架构合规 6/6；SSE 流完整（start→chunk→usage→done）；自动创建会话；同步/流式双模式；上下文窗口自动截取；消息持久化 |
| 2026-06-05 | F15a | Agent | Accept | 40/40 pytest；全量 663 passed, 9 skipped；架构合规 6/6；4 种分块策略 + 父子分块；3 元数据；异步上传返回 task_id；两步确认删除；6xxx 错误码；API 端点 6 个；deps.py delayed import 合规 |
| 2026-06-05 | F15b | Agent | Accept | 14/14 pytest；全量 677 passed, 9 skipped；架构合规 6/6；4 种召回策略（keyword/similarity/hybrid/rrf）；rerank 关键词 boost；父子上下文返回；SSE/同步双模式；citation 去重；3xxx 错误码；API 端点 /kb/query；prompts/rag 模板；RAG_PIPELINE_SPEC.md TBDs filled |
| 2026-06-05 | F16 | Agent | Accept | 28/28 pytest；全量 709 passed, 9 skipped；架构合规 6/6；三层意图漏斗（keyword/similarity/llm）短路生效；多意图检测+query重组；降级策略（chat fallback）；2xxx 错误码；API 端点 /api/v1/intent；prompts/intent/classify.md；INTENT_ROUTING_SPEC.md TBDs filled |
| 2026-06-05 | F17 | Agent | Accept | 14/14 pytest；全量 723 passed, 9 skipped；架构合规 6/6；Prompt 管理 API 4 端点（GET/PUT /api/v1/prompts, GET /api/v1/prompts/{name}/versions, POST /api/v1/prompts/{name}/reset）；列表分页过滤+精确匹配返回详情；修改/回滚互斥校验；版本历史；重置基准；9xxx 错误码；复用 F08 服务层（PromptDomainService+Repo+PromptManager）；API_CONTRACT.md TBD filled by F17 |
| 2026-06-05 | F18 | Agent | Accept | 11/11 pytest；全量 734 passed, 9 skipped；架构合规 6/6；10 项 Prometheus 指标全部暴露（LLM/HTTP/KB/Agent）；LLM gateway 自动记录 token+latency；HTTP middleware 记录请求计数+延迟；KB search 记录查询延迟+文档数；Agent ReAct 记录步数+延迟；/metrics 端点返回 Prometheus 文本；无 prometheus_client 时优雅降级；API_CONTRACT.md TBD filled by F18 |
| 2026-06-05 | F19 | Agent | Accept | 46/46 pytest；全量 780 passed, 9 skipped；架构合规 6/6；5 轨迹维度（state_transition_validity/tool_call_success_rate/loop_detection/step_efficiency/trajectory_completeness）+ 4 对话质量指标（relevance/conciseness/citation/turn_balance）；EvalRunner 批量评估；CJK 字符支持；tool failure 通过 OBSERVING 步骤检测；空数据优雅降级；无 REST API（纯内部服务）；未修改 passing 代码 |
| 2026-06-05 | F20 | Agent | Accept | 11/11 pytest (1 skipped)；架构合规 6/6；ruff check 通过；auth middleware (X-API-Key 校验/enable_auth=false 绕过/豁免路径/401 code 1001)；rate_limit middleware (Redis INCR+EXPIRE/端点覆盖/IP+Key 双标识/429 含 Retry-After/X-RateLimit-* 头/Redis 降级)；RedisClient.expire() 新增；RateLimitSettings 配置类；default.yaml rate_limit 段；ERROR_CODE.md + SECURITY_POLICY.md TBD→filled；未修改 passing 代码 |
| 2026-06-05 | F21 | Agent | Accept | 26/26 pytest；架构合规 6/6；ruff check 通过；Dockerfile 多阶段构建（builder+runtime）+ 非 root 用户 + HEALTHCHECK；docker-compose.yml 4 服务（postgres/redis/qdrant/app）+ app healthcheck + depends_on conditions + 只读 volumes；health_service.py 新增 check_llm() 返回熔断器状态；health.py 响应含 dependencies.llm.channels；DEPLOYMENT_GUIDE.md 8 处 TBD→filled；.env.example 完整；feature_list.json 全部 22/22 passing；init.ps1 7/7；817 total tests pass；项目进入 maintain 阶段 |

## 工单级检查项模板

每个工单在评审时，除通用维度外，还需检查以下工单特定项：

### 底盘类（F01-F03）

- [ ] 启动无报错（uvicorn / init.sh）
- [ ] 错误响应包含 code/message/request_id/trace_id

### 基础设施类（F04-F07）

- [ ] 外部依赖（LLM/Qdrant/Redis）失败时返回结构化错误码
- [ ] 熔断器/信号量配置生效

### 核心服务类（F08-F10）

- [ ] Prompt 变更有版本记录
- [ ] MCP tool 注册/调用成功
- [ ] Skill 遮蔽 Tool 互斥生效

### Agent/Workflow 类（F11-F13）

- [ ] Agent 轨迹记录完整
- [ ] max_steps 限制生效
- [ ] DAG 条件边路由正确

### 业务域类（F14-F17）

- [ ] SSE 流完整（start→chunk→usage→done）
- [ ] 分块策略参数可配
- [ ] 父子分块：子命中→返回父上下文
- [ ] 三层意图漏斗短路生效
- [ ] 多意图 query 重组正确

### 可观测/集成类（F18-F21）

- [ ] /metrics 暴露所有声明指标
- [ ] docker-compose up 全端点可调通