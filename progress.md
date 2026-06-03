# 项目进度日志

> Agent 每轮会话结束必须更新本文件。新会话第一件事：读此文件。

## 元信息

| 字段 | 值 |
|------|-----|
| **current_phase** | `implement` |
| **build_mode** | `greenfield` |
| **last_updated** | 2026-06-02 |
| **last_ticket** | Harness 优化第5轮（DEPENDENCY_MAP 表 3 TestNewHarness 参考索引） |
| **last_verified** | 表 3 + AGENTS/工单 §1.4；generate_orders --orders-only；pytest 12/12 |
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
| **active_feature_id** | `F02` |
| **active_ticket** | `工单/F02_database_models_redis.md` |
| **status** | `in_progress` |
| **goal** | 工单 F02 阶段 1：读 DATA_MODEL / PERSISTENCE_LAYER / ARCHITECTURE.md，禁止写代码 |

## 已验证（可信任）

- [x] Harness 全套文件（AGENTS / progress / feature_list / session-handoff / init / FACT_REGISTRY / CHANGE_WORKFLOW）
- [x] 架构文档 25 个 `docs/**/*.md` + 根目录 `ARCHITECTURE.md`
- [x] 工单系统 23 条（F15→F15a/b/c）+ 依赖图 + 生成脚本
- [x] configs/default.yaml + models.yaml + agents.yaml

## 进行中

- [x] `F01`：项目骨架 + FastAPI 入口 + DI 容器 + YAML 配置

- [ ] `F02`：数据库模型 + Alembic 迁移 + Redis 连接（Harness：`in_progress`，代码待阶段 2）

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
2. 执行工单 **F02** 阶段 1→2→3（`feature_list.json` 中 F02 为唯一 `in_progress`）。
3. 工单顺序：F02 → F03 → … → F15a → F15b → F15c → F16 → … → F21（F01 已 passing）。

## 会话历史摘要

### 2026-06-02（Harness 优化第5轮）

- `docs/00-meta/DEPENDENCY_MAP.md` 表 3：TestNewHarness 工单对照、契约漂移、使用/禁止规则
- `AGENTS.md` §0.2、`FEATURE_DEV_WORKFLOW.md`、`FACT_REGISTRY.md` 链接表 3
- `scripts/generate_orders.py` 工单 §1.4 可选外部参考；23 工单已重生成

### 2026-06-02（Harness 优化第4轮）

- 工单生成器：全量三段式（阶段1/2/3）+ DEPENDENCY_MAP 代码依赖 + YAML `phase2_checklist` / `phase3_doc_sync`
- F02/F03 YAML 路径级实现清单；23 条工单已 `--orders-only` 重生成
- `ERROR_CODE.md` Canonical Format（REST 整数 / SSE `AI_%04d`）；`app/core/errors.py` 增加 format/parse
- `API_CONTRACT.md` API 选型决策表 + 反模式
- `AGENTS.md` §0.3 TBD 约定；`FACT_REGISTRY.md` §0 Harness 约定

### 2026-06-02（Harness 优化第3轮）

- docs 剩余裸 `F15` TBD 改为 F15a/b/c（ERROR_CODE、QDRANT、DOMAIN_MAP、TOOLS_MCP、DI_CONTAINER）
- F15c 工单 slug：`knowledge_qa_domain_e2e`（原 deletion）
- `session-handoff.md` 命令速查补 `init.ps1`

### 2026-06-02（Harness 优化第2轮）

- F15 拆分为 F15a/F15b/F15c，工单重新生成（23条）
- DEPENDENCY_MAP.md F15→F15a/b/c（表1+表2）
- generate_orders.py ORDER_SLUGS 补 F15a/b/c，删 F15
- init.sh/init.ps1 步骤编号统一 [1/6]~[6/6]
- AGENTS.md §0.1 补 Windows `init.ps1` 说明
- 抽取 `scripts/check_fact_registry.py`，init.sh/init.ps1 共用（替代各自内联 Python）
- docs TBD 引用 F15→F15a/F15b（4文件17处）
- CHANGE_WORKFLOW.md 变更单编号统一为 CO-NNN + 补目录创建说明

### 2026-06-02（Harness 修补）

- `generate_orders.py` 状态合并、`--orders-only`、`init.ps1`、`ARCHITECTURE.md` 路径修正

### 2026-06-02（F01 + 设计）

- 全面对比 myprojects/st_ai 项目，借鉴 15 项改进：
  - 新增 CHANGE_WORKFLOW.md / FACT_REGISTRY.md / API_CHANGE_CHECKLIST.md
  - 新增 SSE_STREAM_SPEC.md / CIRCUIT_BREAKER_SPEC.md / BOOTSTRAP_SPEC.md
  - AGENTS.md 增加会话生命周期 / 变更流程 / progress.md 自动续接 / 快速导航
  - ARCHITECTURE.md 增加启动编排 / 熔断器降级 / 按任务分流 / SSE 服务 / JSON 修复 / Citation / Image Processor / 变更规则
  - 新增 progress.md 进度文件
  - configs 新增 circuit_breaker 段
  - F01 已 passing（12/12 测试）