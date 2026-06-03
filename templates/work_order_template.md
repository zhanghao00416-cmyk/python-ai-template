# 工单模板

> 由 `scripts/generate_orders.py` 从 `configs_work_orders/work_orders.yaml` 生成。
> 可在 YAML 中为工单配置 `phase2_checklist`（路径级清单）与 `phase3_doc_sync`（docs 回填项）。

## 元数据
- **id**: FNN
- **state**: not_started
- **dependencies**: [FXX, ...]

## 功能三元组
- **行为**：
- **验证**：
- **状态**：not_started → active → passing

## 验收标准
- [ ] 验证命令通过
- [ ] `scripts/check-architecture.sh` 通过
- [ ] pytest 通过
- [ ] `feature_list.json` + evidence

## 关键约束
- `ARCHITECTURE.md` 分层
- `ERROR_CODE.md`：REST 整数 code；SSE `AI_%04d`
- `API_CONTRACT.md` 决策表（业务域）
- `[TBD: filled by Fxx]` 见 `AGENTS.md` §0.3

---

## 阶段 1：只读不写

1. `DEPENDENCY_MAP.md` 本工单行 + 前序代码 read_file
2. 工单 docs 全量阅读
3. 交付物：差异、错误码、文件清单、不做范围

---

## 阶段 2：实现

### 2.2 实现清单

（YAML `phase2_checklist` 或生成器默认表）

---

## 阶段 3：自审与交接

- `evaluator-rubric.md`
- docs 同步（YAML `phase3_doc_sync`）
- 更新 `feature_list.json` / `progress.md` / `session-handoff.md`
