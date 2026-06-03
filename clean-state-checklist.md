# 干净状态检查清单

会话结束前逐项确认。全部勾选才可 commit / 结束。

## Harness 与状态

- [x] `progress.md` 已更新，且 **active 指向下一任务**（F02）；见 `AGENTS.md` §7.1
- [x] `feature_list.json` 状态与 evidence 真实反映验证结果；下一项 **唯一** `in_progress`（F02）
- [x] `session-handoff.md` 已含 **下一会话开场白**
- [x] 无未记录的「半成品」步骤（F01 已 closing）

## Handoff 校验（每次必查）

- [ ] `session-handoff.md` 包含下一会话开场白
- [ ] `session-handoff.md` 包含断点位置（阶段1/2/3）
- [ ] `session-handoff.md` 包含已完成的步骤清单
- [ ] 若断点续接：包含未完成的原因
- [ ] 包含下一工单编号

## 验证

- [x] `init.ps1` 或 `bash init.sh` 可跑（Windows 优先 `.\init.ps1`）
- [ ] 若执行了实现工单：`evaluator-rubric.md` 结论非 Block
- [ ] 若改 API/错误码：`API_CONTRACT.md` / `ERROR_CODE.md` 已同步

## 范围

- [ ] 本轮仅做一个 feature / 一张工单
- [ ] 未悄悄扩大 scope 或改弱验证规则

## 可恢复性

- [ ] 下一轮 Agent 仅读仓库文件即可继续，无需聊天补上下文
- [ ] `git status` 干净或变更已 commit（commit message 含 feature id / 工单号）

## 设计阶段附加

- [ ] `progress.md` 中 `current_phase` 仍为 `design` 时，未提交 `app/` 代码
- [ ] docs 变更与 `FACT_REGISTRY.md` 一致

## 变更流程附加（仅 task_mode=change 时）

- [ ] 变更单阶段 1 交付物已写入变更单
- [ ] 若 api-change：`API_CHANGE_CHECKLIST.md` 已勾选
- [ ] 变更 Accept 后：`progress.md` 的 `task_mode` 已改回 `linear`，`active_*` 已恢复 `resume_*`

## 构建

- [ ] `pip install -e ".[dev]"` 无错误
- [ ] `ruff check app/` 无错误
- [x] `pytest tests/ -v` 全部通过（当前仅 F01：12 passed）

## 架构

- [ ] 无 `app/api` 直接 import `app/infra`（应经 services/domain）
- [ ] 无 domain 直连 LLM provider（应经 services/llm/gateway）
- [ ] 无硬编码 prompt 字符串（应从 prompts/ 加载）
- [ ] 无循环依赖

## 安全

- [ ] 无 API key 或 secret 在提交文件中
- [ ] `.env` 在 `.gitignore`