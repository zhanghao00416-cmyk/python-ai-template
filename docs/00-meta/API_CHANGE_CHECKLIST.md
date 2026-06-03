# 接口/API 变更检查清单

> 仅当变更类型为 `api-change` 或变更单涉及对外契约时使用。
> 阶段 2 写代码前，Agent 必须逐项确认；阶段 3 输出勾选结果。

## A. 文档（代码之前）

- [ ] 已明确变更的 **HTTP 方法 + 路径**（或 SSE 事件类型）
- [ ] 已更新 `docs/01-architecture/API_CONTRACT.md` 对应 §
- [ ] 若新增/修改错误码：已更新 `ERROR_CODE.md`（REST 整数；SSE `AI_%04d`，见 Canonical Format）
- [ ] 若涉及枚举/默认值/SSE 子集：已更新 `FACT_REGISTRY.md`
- [ ] 若涉及数据模型：已更新 `DATA_MODEL.md`
- [ ] 若涉及域边界：已更新 `DOMAIN_MAP.md`
- [ ] docs 之间 **无字段名冲突**（以 API_CONTRACT 为准）

## B. 代码（按 ARCHITECTURE 分层）

- [ ] `app/schemas/` 请求/响应模型已对齐契约
- [ ] `app/api/` 路由与依赖注入已更新（无业务逻辑渗入）
- [ ] `app/domain/` 编排逻辑已更新
- [ ] `app/services/` 共用能力已更新（如 SSE 格式化）
- [ ] `app/infra/` 网关/客户端未 bypass
- [ ] 未硬编码 prompt；未破坏依赖方向

## C. 测试与验证

- [ ] 已添加或更新单测 / 集成测（路径写在变更单）
- [ ] `pytest` 通过（或变更单规定的子集）
- [ ] `init.sh` 通过

## D. 交接

- [ ] `feature_list.json` evidence 含验证命令输出摘要
- [ ] `progress.md` 已恢复主线或指向下一变更
- [ ] `session-handoff.md` 含下一会话开场白
- [ ] 若 Breaking Change：已在变更单标注需同步项

## 结论

- [ ] **Ready** — 可 Accept，恢复主线
- [ ] **Not Ready** — 列出阻塞项，保持 `in_progress`