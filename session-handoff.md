# 会话交接

> 每轮长会话结束前填写。新会话先读 `progress.md`，再读本文件。

## 当前已验证

- **明确可用**：
  - Harness 全套（AGENTS / progress / feature_list / FACT_REGISTRY / CHANGE_WORKFLOW / init）
  - 架构文档 25 个 `docs/**/*.md` + `ARCHITECTURE.md`
  - 工单系统 23 条（F15→F15a/b/c）+ 模板 + 生成脚本
  - configs（default.yaml + models.yaml + agents.yaml）
  - **F01-F21 全部 passing**（22/22）
  - F21 实现内容：
    - `Dockerfile`：多阶段构建（builder+runtime）、非 root 用户、HEALTHCHECK
    - `docker-compose.yml`：4 服务（postgres/redis/qdrant/app）+ app healthcheck + depends_on conditions + 只读 volumes
    - `app/services/health_service.py`：新增 `check_llm()` 返回熔断器状态
    - `app/api/v1/health.py`：响应含 `dependencies.llm.channels`
    - `tests/test_f21_deployment.py`：26 项测试
    - `docs/02-engineering/DEPLOYMENT_GUIDE.md`：8 处 TBD→filled
- **本轮跑过的验证**：
  - `pytest tests/` — 817 passed, 10 skipped
  - `ruff check app/` — 全通过
  - 架构合规测试通过
  - init.ps1 7/7

## 仍损坏或未验证

- **外部依赖**：PG/Redis/Qdrant 未实际运行（集成测试跳过，本地 `docker compose up` 后可验证）

## 下一步最佳动作

| 字段 | 值 |
|------|-----|
| **feature_id** | `—`（全部完成） |
| **active_ticket** | `—` |
| **从哪开始** | 项目进入 **maintain** 阶段 |
| **不要动** | 如需新增功能，走变更流程（`docs/00-meta/CHANGE_WORKFLOW.md`） |

## 下一会话开场白（上班复制这一条）

```text
按 AGENTS.md 0.1 启动，读取 progress.md 确认当前状态。
F01-F21 全部 passing，项目进入 maintain 阶段。
如需新增功能，请走变更流程（docs/00-meta/CHANGE_WORKFLOW.md）。
如需修复 bug，请走 hotfix 流程。
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
| F01-F21 | **passing** | 全部 22 项功能完成 |

## 项目里程碑

- **2026-06-02**：Harness 建立（AGENTS.md / progress.md / feature_list.json / 工单系统 / DEPENDENCY_MAP）
- **2026-06-04**：F01-F13 完成（骨架 → 数据库 → 错误体系 → LLM Gateway → 向量库 → SSE → 任务队列 → Prompt → 上下文 → Tools → Agent → 多 Agent → Workflow）
- **2026-06-05**：F14-F21 完成（Chat → 知识库文档管理 → RAG查询 → E2E联调 → 意图识别 → Prompt管理API → 可观测性 → 评估框架 → 认证限流 → Docker部署）
- **总计**：817 tests pass, 10 skipped; 架构合规 6/6; ruff check 全通过
