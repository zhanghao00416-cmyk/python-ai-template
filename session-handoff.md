# 会话交接

> 每轮长会话结束前填写。新会话先读 `progress.md`，再读本文件。

## 当前已验证

- **明确可用**：
  - Harness 全套（AGENTS / progress / feature_list / FACT_REGISTRY / CHANGE_WORKFLOW / init）
  - 架构文档 25 个 `docs/**/*.md` + `ARCHITECTURE.md`（含 SSE / CIRCUIT / BOOTSTRAP / WORKFLOW / TOOLS_MCP 等）
  - 工单系统 23 条（F15→F15a/b/c）+ 模板 + 生成脚本
  - configs（default.yaml + models.yaml + agents.yaml）
  - **F01 已 passing**：13/13 测试通过，health endpoint 200，DI 容器可用，YAML 配置加载正常
  - skills/ + workflows/ + prompts/agents/ + prompts/skills/ 声明式 YAML 示例
- **本轮跑过的验证**：
  - `pytest tests/test_01_skeleton.py` — 13/13 passed
  - `bash scripts/check-architecture.sh` — all checks passed
  - Health endpoint `GET /api/v1/health` — 200 OK

## Harness 优化第5轮（2026-06-02）

- `DEPENDENCY_MAP.md` 新增 **表 3：TestNewHarness 外部参考**（工单对照、契约漂移、禁止复制规则）
- `AGENTS.md` / `FEATURE_DEV_WORKFLOW.md` / `FACT_REGISTRY.md` 已链到表 3
- 工单已重生成，阶段 1 含 §1.4 可选对照说明

## Harness 优化第4轮（2026-06-02）

- 23 条工单含完整阶段 1→2→3；F02/F03 有 YAML 路径级 `phase2_checklist`
- 错误码：REST `code` 整数；SSE `error` 用 `AI_%04d`（见 ERROR_CODE.md）
- API 选型：见 API_CONTRACT「API 选型决策表」
- 重生成：`python scripts/generate_orders.py --orders-only`

## Harness 优化第3轮（2026-06-02）

- docs 裸 `F15` TBD 全部改为 F15a/b/c（5 文件 6 处）
- F15c 工单文件重命名为 `F15c_knowledge_qa_domain_e2e.md`
- 命令速查补充 Windows `init.ps1`

## Harness 优化第2轮（2026-06-02）

- F15 拆分为 F15a/F15b/F15c，工单重新生成（23条）
- DEPENDENCY_MAP.md F15→F15a/b/c（表1+表2）
- generate_orders.py ORDER_SLUGS 补 F15a/b/c，删 F15
- init.sh/init.ps1 步骤编号统一 [1/6]~[6/6]
- AGENTS.md §0.1 补 Windows `init.ps1` 说明
- 抽取 `scripts/check_fact_registry.py`，两个 init 共用
- docs TBD 引用 F15→F15a/F15b（4文件17处）
- CHANGE_WORKFLOW.md 变更单编号统一为 CO-NNN + 补目录创建说明

## Harness 修补（2026-06-02）

- `generate_orders.py` 合并保留 `feature_list.json` 进度；新增 `--orders-only`
- `ARCHITECTURE.md` 路径统一为仓库根目录（work_orders.yaml / 工单 / DEPENDENCY_MAP）
- `init.ps1` + `scripts/update_system_state.py`；`system-state.json` 已同步（1 passing / 1 in_progress）

## 本轮改动（2026-06-02 F01）

- **F01 实现**：
  - `app/core/config.py`：YAML+env 配置加载（pydantic-settings），支持 default.yaml/override.yaml 深度合并
  - `app/core/di.py`：轻量 DI 容器（register/resolve/override/reset/cleanup），支持 singleton/transient
  - `app/core/errors.py`：AppError 基类 + SystemError + ErrorCode 枚举
  - `app/core/response.py`：统一响应 envelope（ok_response/error_response/validation_error_response）
  - `app/core/context.py`：Context vars（trace_id/request_id/user_id/session_id）
  - `app/core/logging.py`：structlog JSON 格式 + contextvars 注入 + 敏感值脱敏
  - `app/core/constants.py`：APP_VERSION + API_PREFIX
  - `app/core/__init__.py`：核心模块导出
  - `app/bootstrap.py`：FastAPI lifespan startup/shutdown（logging→infra→health check）
  - `app/main.py`：FastAPI app 入口
  - `app/api/v1/health.py`：健康检查路由
  - `app/api/deps.py`：FastAPI Depends 桥接
  - `tests/test_01_skeleton.py`：13 项测试覆盖全部 core 模块
- **前轮设计文档更新**：
  - WORKFLOW_SPEC.md、API_CONTRACT.md（POST /run）、skills/workflows YAML 示例
  - progress.md build_mode 字段

## 仍损坏或未验证

- **外部依赖**：PG/Redis/Qdrant 未实际连接（health 返回 "not_checked"，F02 解决）
- **未跑** `uv sync`（用 pip install -e 代替）
- F01 scope 外的功能均 not_started

## 下一步最佳动作

| 字段 | 值 |
|------|-----|
| **feature_id** | `F02` |
| **active_ticket** | `工单/F02_database_models_redis.md` |
| **从哪开始** | 工单 F02 **阶段 1**（只读，禁止写代码） |
| **不要动** | 勿跳阶段；勿口头改功能（走变更单） |

## 下一会话开场白（上班复制这一条）

```text
按 AGENTS.md 0.1 启动，执行 progress.md 中的 active 任务（工单 F02 数据库模型+Redis）。
先运行 init.sh 或 init.ps1，再读 FACT_REGISTRY、ARCHITECTURE、DATA_MODEL、PERSISTENCE_LAYER。
可选对照 TestNewHarness：DEPENDENCY_MAP.md 表 3（F02 无老路径则跳过）；禁止整文件复制。
严格阶段 1 只读，首段约束摘要 ≥5 条，输出阶段 1 交付物（含差异表）。
```

阶段 1 通过后：

```text
阶段1通过，进入阶段2，严格按工单 F02 的 §2.1–2.3 与 §2.2 实现清单创建文件。
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
| F02 数据库模型+Redis | **in_progress** | 下一 session 从阶段1开始 |