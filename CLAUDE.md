# CLAUDE.md — Quick Reference

## Project

Python AI Template — 通用的自包含 AI 平台模板，14 项可复用能力。

## Commands

```sh
# 安装依赖
pip install -e ".[dev]"

# 开发服务器
uvicorn app.main:app --host 0.0.0.0 --port 6006 --reload

# 测试
pytest tests/ -v
pytest tests/test_01_skeleton.py -v    # 单个工单测试

# 类型检查
ruff check app/
ruff format app/

# 生成工单（合并保留 feature_list 进度；仅改 YAML 文案时用 --orders-only）
python scripts/generate_orders.py
python scripts/generate_orders.py --orders-only

# Windows 健康检查
./init.ps1

# 架构依赖检查
bash scripts/check-architecture.sh

# 启动验证
bash init.sh
```

## Key Files

| File | Purpose |
|------|---------|
| AGENTS.md | Entry protocol, rules, constraints |
| ARCHITECTURE.md | Layer rules, dependency direction |
| feature_list.json | Feature progress authority |
| session-handoff.md | Cross-session handoff + Next pointer |
| system-state.json | Runtime health snapshot (auto-generated) |
| configs/default.yaml | Default configuration |
| configs/models.yaml | Model routing configuration |
| configs/agents.yaml | Agent role definitions |
| configs_work_orders/work_orders.yaml | Work order metadata (single source) |

## Architecture

```
api → domain → services → infra
domain ← agent/workflow (domain orchestrates)
agent/workflow → tools, services
core (shared), schemas (api/domain shared)
```

## Key Rules

- Never bypass model gateway for LLM calls
- Never put business logic in api layer
- Never hardcode prompt strings in Python
- Never let domain directly access provider SDKs
- Never modify passing feature code without a patch work order
- Read AGENTS.md + feature_list.json + session-handoff.md before coding
- Every feature must pass its verification command to be marked passing