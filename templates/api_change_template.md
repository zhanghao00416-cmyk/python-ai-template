# 接口变更工单

> 类型：api-change | 改路径/字段/错误码/SSE 事件 | **必须先改 docs 再改代码**

## 变更描述

**动机**（业务语言）：

**期望接口变更**：

**resume_feature_id**：（从 progress.md 复制）
**resume_ticket**：（从 progress.md 复制）

## 阶段 0：人类意图（仅填动机）

## 阶段 1：Agent 定位（只读，禁止写代码）

**涉及文件**：

**契约 diff**：

**验证命令**：

等待人类回复「阶段1通过」后才可进入阶段 2。

## 阶段 2：实现（docs 先于代码）

### 2.1 更新 docs（必须先完成）

- [ ] `docs/01-architecture/API_CONTRACT.md` 已更新
- [ ] `docs/01-architecture/ERROR_CODE.md` 已更新（若涉及）
- [ ] `docs/00-meta/FACT_REGISTRY.md` 已更新（若涉及枚举/常量）

### 2.2 更新代码

- [ ] `app/schemas/` 请求/响应模型已对齐
- [ ] `app/api/` 路由已更新
- [ ] `app/domain/` 编排逻辑已更新

## 阶段 3：自审验证

- [ ] `init.sh` 通过
- [ ] 变更验证命令通过
- [ ] `evaluator-rubric.md` 非 Block
- [ ] `docs/00-meta/API_CHANGE_CHECKLIST.md` 已勾选
- [ ] `progress.md` 已恢复主线（`task_mode` → `linear`）
- [ ] `session-handoff.md` 含下一会话开场白