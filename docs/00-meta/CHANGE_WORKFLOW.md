# 变更工作流

> 新建功能用 `工单/`；**修改已有功能/接口**用本流程。
> 目标：把「改什么、改哪些文件、按什么顺序、如何验证、如何恢复主线」**固定下来**，避免漏步骤。

---

## 1. 三种变更类型（先选型）

| 类型 | 代号 | 适用 | 是否改 API_CONTRACT |
|------|------|------|---------------------|
| **热修复** | `hotfix` | Bug、逻辑错误、单模块小改；**不改**对外契约 | 否 |
| **接口变更** | `api-change` | 改路径/字段/错误码/SSE 事件 | **是（必须先于代码）** |
| **功能变更** | `feature-change` | 跨多模块、新行为、域逻辑大改 | 视情况 |

**选型不准时，按更严格的来：** 涉及 API 字段 → 至少走 `api-change`。

---

## 2. 人类操作清单（每次变更固定 5 步）

### 步骤 0：暂停主线

编辑 `progress.md`，填写**变更暂停点**：

```markdown
## 变更暂停点（task_mode=change 时填写）

| 字段 | 值 |
|------|-----|
| **task_mode** | `change` |
| **resume_feature_id** | （当前 active_feature_id） |
| **resume_ticket** | （当前 active_ticket） |
| **change_id** | `CO-NNN`（递增编号） |
| **change_ticket** | `变更工单/CO-NNN_描述.md` |
```

### 步骤 1：复制模板 → 新建变更单

从 `templates/` 复制对应模板到 `变更工单/`：

> `变更工单/` 目录在首张变更单创建时自动建立（`mkdir -p 变更工单` 或 `New-Item -ItemType Directory -Path 变更工单`）。

```text
变更工单/CO-NNN_描述.md
```

**阶段 0（人类只写意图）：**

- 动机、期望行为 / 接口意图
- `resume_ticket`：从 `progress.md` 的 **active_ticket** 复制
- **不必填**：具体代码路径、schemas 文件名、API_CONTRACT § 号 → 全部由 **Agent 阶段 1** 查完写入

### 步骤 2：Agent 阶段 1 → 人类审阅

Agent 查 docs + 代码，将文件清单、契约 diff、验证命令写入变更单「阶段 1 交付物」。

人类回复「阶段1通过」后才可进入阶段 2。

### 步骤 3：更新 `progress.md` + `feature_list.json`

| 文件 | 写什么 |
|------|--------|
| `progress.md` | `task_mode: change`；`active_ticket` → 变更单路径 |
| `feature_list.json` | 新增 `CO-NNN` 条目，**唯一** `in_progress` |

### 步骤 4：执行变更

Agent 严格按变更单阶段 1→2→3 执行。

### 步骤 5：变更 Accept 后恢复主线

Agent 阶段 3 **必须**：

- 将 `task_mode` 改回 `linear`
- `active_ticket` / `active_feature_id` 恢复为 `resume_*`
- 在 `session-handoff.md` 写恢复后的默认开场白

---

## 3. 变更单模板路径

| 类型 | 模板 |
|------|------|
| 热修复 | `templates/hotfix_template.md` |
| 接口变更 | `templates/api_change_template.md` |
| 功能变更 | `templates/feature_change_template.md` |

---

## 4. 接口变更额外强制清单

凡 `api-change` 类型，阶段 2 前必须完成 `docs/00-meta/API_CHANGE_CHECKLIST.md` 全部 applicable 项。

同步文件（按改动范围）：

1. `docs/01-architecture/API_CONTRACT.md`
2. `docs/01-architecture/ERROR_CODE.md`（若涉及）
3. `docs/00-meta/FACT_REGISTRY.md`（若涉及枚举/常量）
4. 对应 `docs/03-ai/*.md` 或 `docs/04-kb/*.md`
5. `docs/00-meta/DEPENDENCY_MAP.md`（若跨工单依赖变化）

---

## 5. 验证标准（所有变更类型）

阶段 3 结束前必须：

- [ ] `init.sh` 通过
- [ ] 变更单内列出的验证命令已跑并写入 evidence
- [ ] `evaluator-rubric.md` 非 Block
- [ ] 若 api-change：`API_CHANGE_CHECKLIST.md` 已勾选
- [ ] `progress.md` 已恢复主线或指向下一变更
- [ ] `session-handoff.md` 含下一会话开场白