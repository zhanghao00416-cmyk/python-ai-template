# Python AI Template

通用 Python AI 平台模板（14 项可复用能力）：FastAPI、LLM Gateway、RAG 知识库、Agent/Workflow、SSE 流式等。采用 **Harness 工单驱动 + docs-first** 开发。

| 文档 | 读者 | 内容 |
|------|------|------|
| **[使用手册.md](./使用手册.md)** | 人类 + 新同事 | 安装、配置、启动、工单流程、Agent 协作（**建议先读**） |
| [AGENTS.md](./AGENTS.md) | AI Agent | 会话协议、分层规则、禁止行为 |
| [CLAUDE.md](./CLAUDE.md) | AI Agent | AGENTS 速查 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 架构 | 分层、依赖方向、能力地图 |
| [progress.md](./progress.md) | 全员 | 当前阶段、活跃工单 |
| [session-handoff.md](./session-handoff.md) | 全员 | 下一会话开场白（**复制即用**） |

## 快速开始

```powershell
cd python-ai-template
pip install -e ".[dev]"
copy .env.example .env   # 若尚无 .env，编辑密钥与连接串
docker compose up -d postgres redis
.\init.ps1
uvicorn app.main:app --host 0.0.0.0 --port 6006 --reload
```

健康检查：<http://localhost:6006/api/v1/health>

## 当前进度

- **阶段**：`implement`（见 `progress.md`）
- **已完成**：F01 项目骨架（13/13 测试）
- **进行中**：F02 数据库 + Redis + Alembic

## 仓库结构（简图）

```
python-ai-template/
├── app/                 # 应用代码（按 ARCHITECTURE 分层）
├── configs/             # default.yaml、models.yaml（非密钥）
├── .env                 # 环境变量（本仓纳入 Git）
├── secrets/             # Docker 密钥文件 → /run/secrets
├── docs/                # 契约与规范（事实来源）
├── 工单/                # F01–F21 实现工单
├── tests/               # 按 feature 编号
└── 使用手册.md          # 人类使用说明
```

## License

按你方项目策略填写；模板课程用途请参阅上级 `learn-harness-engineering` 仓库说明。
