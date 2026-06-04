# 热修复工单

> 类型：hotfix | Bug / 逻辑错误 / 单模块小改 | **不改**对外契约

## 变更描述

**动机**（业务语言）：
`configs/default.yaml` 的 `context` 段字段名（`history_max_rounds` / `max_context_tokens`）与 `ContextSettings` 的实际字段名（`redis_cache_ttl` / `default_max_tokens` / `default_strategy`）不匹配，导致 YAML 配置未生效，ContextManager 始终使用代码默认值。

**期望行为**：
`default.yaml` 的 context 段字段名与 `ContextSettings` 一致，YAML 值能正确覆盖默认值。

**涉及模块**：
- `configs/default.yaml`（context 段）

## 阶段 0：人类意图

| 字段 | 值 |
|------|-----|
| **变更类型** | hotfix |
| **resume_feature_id** | F10 |
| **resume_ticket** | 工单/F10_tools_registry.md |

## 阶段 1：Agent 文件清单（只读）

**代码文件**：
- `configs/default.yaml` — context 段字段名修复
- `app/core/config.py` — ContextSettings 字段名参照（不改）

**docs 文件**：无

**验证命令**：`pytest tests/test_09_context_manager.py -v`

## 阶段 2：实现

`configs/default.yaml` context 段：
- `history_max_rounds: 5` → 删除（ContextSettings 无此字段）
- `max_context_tokens: 4096` → `default_max_tokens: 4096`
- 新增 `redis_cache_ttl: 3600`
- 新增 `default_strategy: "recent_priority"`

## 阶段 3：自审验证

- [x] `pytest tests/` 通过（376 passed, 9 skipped）
- [x] 热修复验证命令通过（test_09 57 passed）
- [x] `evaluator-rubric.md` 非 Block
- [x] `progress.md` 已记录变更
- [x] 不影响 API 契约、错误码、分层
