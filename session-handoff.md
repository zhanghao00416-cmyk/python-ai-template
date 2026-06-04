# 会话交接

> 每轮长会话结束前填写。新会话先读 `progress.md`，再读本文件。

## 当前已验证

- **明确可用**：
  - Harness 全套（AGENTS / progress / feature_list / FACT_REGISTRY / CHANGE_WORKFLOW / init）
  - 架构文档 25 个 `docs/**/*.md` + `ARCHITECTURE.md`
  - 工单系统 23 条（F15→F15a/b/c）+ 模板 + 生成脚本
  - configs（default.yaml + models.yaml + agents.yaml）
  - **F01 已 passing**：13/13 测试通过
  - **F02 已 passing**：42/42 测试通过（9 集成跳过需 PG/Redis）
  - **F03 已 passing**：49 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F04 已 passing**：51 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F05 已 passing**：52 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F06 已 passing**：32 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F07 已 passing**：47 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F08 已 passing**：46 单元测试通过；init.ps1 7/7；架构 6/6 pass
  - **F09 已 passing**：57 单元测试通过；init.ps1 7/7；架构 6/6 pass
- F09 实现内容：
  - `app/schemas/session.py`：SessionCreateRequest/SessionDetail/MessageCreateRequest/MessageDetail/ContextWindowResult
  - `app/domain/session/repo.py`：SessionRepo + MessageRepo (BaseRepo)
  - `app/domain/session/service.py`：SessionService — CRUD + message + expire
  - `app/services/context_manager.py`：ContextManager — token count + 3 strategies + Redis cache
  - `app/core/config.py`：ContextSettings (redis_cache_ttl/default_max_tokens/default_strategy)
  - `app/infra/redis_client.py`：新增 hdelete
  - `app/bootstrap.py`：ContextManager DI 注册
  - `tests/test_09_context_manager.py`：57 项测试
- **本轮跑过的验证**：
  - `pytest tests/` — 376 passed, 9 skipped
  - `scripts/check-architecture.ps1` — 6/6 pass
  - `init.ps1` — 7/7 pass

## 本轮改动（2026-06-04 F09）

- **F09 实现**：
  - 新建 `app/schemas/session.py`，`app/domain/session/__init__.py`，`app/domain/session/repo.py`，`app/domain/session/service.py`
  - 新建 `app/services/context_manager.py`
  - 新建 `tests/test_09_context_manager.py`（57 项测试）
  - 修改 `app/core/config.py`（新增 ContextSettings）
  - 修改 `app/infra/redis_client.py`（新增 hdelete）
  - 修改 `app/bootstrap.py`（新增 ContextManager DI 注册）
  - 修改 `docs/02-engineering/CONTEXT_MANAGEMENT_SPEC.md`（7 处 TBD→filled）
  - 修改 `docs/01-architecture/DATA_MODEL.md`（messages TBD→filled + Redis 结构补充）
  - 修改 `docs/01-architecture/DOMAIN_MAP.md`（新增 session 域注册 + ContextManager 服务路径）
  - 更新 `feature_list.json`（F09→passing, F10→in_progress）
  - 更新 `progress.md`（F09 完成，下一 F10）

## 仍损坏或未验证

- **外部依赖**：PG/Redis/Qdrant 未实际运行（集成测试跳过，本地 `docker compose up` 后可验证）
- F09 scope 外的功能均 not_started

## 下一步最佳动作

| 字段 | 值 |
|------|-----|
| **feature_id** | `F10` |
| **active_ticket** | `工单/F10_tools_registry.md` |
| **从哪开始** | 工单 F10 **阶段 1**（只读，禁止写代码） |
| **不要动** | 勿跳阶段；勿口头改功能（走变更单） |

## 下一会话开场白（上班复制这一条）

```text
按 AGENTS.md 0.1 启动，执行 progress.md 中的 active 任务（工单 F10 Tools 注册中心）。
先运行 init.ps1，再读 FACT_REGISTRY、ARCHITECTURE、TOOLS_MCP_SPEC、DEPENDENCY_MAP。
严格阶段 1 只读，首段约束摘要 ≥5 条，输出阶段 1 交付物（含差异表）。
```

## 若要新加/改接口（备忘）

复制 `templates/` 对应变更模板，阶段 0 只写动机；Chat 加一句「我不知道涉及哪些文件，请阶段1定位」。

## 命令速查

人类上手见 **`使用手册.md`**；仓库入口 **`README.md`**。

```bash
cd /path/to/python-ai-template
bash init.sh          # Git Bash / WSL / Linux
```

```powershell
cd C:\path\to\python-ai-template
.\init.ps1            # Windows PowerShell（推荐）
```

## 活跃工单

| 工单 | 阶段 | 备注 |
|------|------|------|
| F01 项目骨架 | **passing** | 13/13 测试通过 |
| F02 数据库模型+Redis | **passing** | 42/42 测试通过，9 集成跳过 |
| F03 错误体系+中间件 | **passing** | 49 单元测试通过，架构 6/6 |
| F04 LLM Gateway | **passing** | 51 单元测试通过，架构 6/6 |
| F05 向量库+Qdrant | **passing** | 52 单元测试通过，架构 6/6 |
| F06 SSE 流式服务 | **passing** | 32 单元测试通过，架构 6/6 |
| F07 异步任务队列 | **passing** | 47 单元测试通过，架构 6/6 |
| F08 Prompt 管理器 | **passing** | 46 单元测试通过，架构 6/6 |
| F09 上下文管理器 | **passing** | 57 单元测试通过，架构 6/6 |
| F10 Tools 注册中心 | **in_progress** | 下一 session 从阶段1开始 |