# 热修复工单

> 类型：hotfix | Bug / 逻辑错误 / 单模块小改 | **不改**对外契约

## 变更描述

**动机**（业务语言）：

**期望行为**：

**涉及模块**（Agent 阶段 1 填写）：

## 阶段 0：人类意图

| 字段 | 值 |
|------|-----|
| **变更类型** | hotfix |
| **resume_feature_id** | （从 progress.md 复制） |
| **resume_ticket** | （从 progress.md 复制） |

## 阶段 1：Agent 文件清单（只读）

**代码文件**：

**docs 文件**：

**验证命令**：

## 阶段 2：实现

（严格限定在本热修复范围，不改 API 契约）

## 阶段 3：自审验证

- [ ] `init.sh` 通过
- [ ] 热修复验证命令通过
- [ ] `evaluator-rubric.md` 非 Block
- [ ] `progress.md` 已恢复主线
- [ ] `session-handoff.md` 含下一会话开场白