# 功能变更工单

> 类型：feature-change | 跨多模块 / 新行为 / 域逻辑大改

## 变更描述

**动机**（业务语言）：

**期望行为变更**：

**涉及范围**（Agent 阶段 1 填写）：

**resume_feature_id**：（从 progress.md 复制）
**resume_ticket**：（从 progress.md 复制）

## 阶段 0：人类意图（仅填动机）

## 阶段 1：Agent 定位（只读，禁止写代码）

**代码文件**：

**docs 文件**：

**验证命令**：

等待人类回复「阶段1通过」后才可进入阶段 2。

## 阶段 2：实现

（严格按变更范围，不改无关模块）

## 阶段 3：自审验证

- [ ] `init.sh` 通过
- [ ] 变更验证命令通过
- [ ] `evaluator-rubric.md` 非 Block
- [ ] 若涉及 API：`API_CHANGE_CHECKLIST.md` 已勾选
- [ ] `progress.md` 已恢复主线（`task_mode` → `linear`）
- [ ] `session-handoff.md` 含下一会话开场白