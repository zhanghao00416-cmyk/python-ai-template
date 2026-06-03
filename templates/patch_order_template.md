# 修补工单模板

## 元数据
- **id**: FNN
- **state**: not_started
- **dependencies**: [FXX]（被修补的功能）
- **patches**: FXX（修补哪个功能）
- **supersedes**: 无
- **superseded-by**: 无

## 修补原因
（描述为什么需要对已 passing 的功能进行修补）

## 影响范围
- 修改的文件列表
- 不影响的原有功能

## 验收标准
- [ ] 修补后的功能正常工作
- [ ] 原 FXX 功能的所有测试仍然通过
- [ ] 新增的修补测试通过

## 实现指引

### 需要读的文件
- 原 FXX 工单文件
- `docs/01-architecture/XXX.md`

### 预计修改的文件
- `app/xxx/yyy.py` — 修改说明

### 关键约束
- 不修改原有接口签名（仅新增或修复）
- 保持向后兼容
- 修补范围最小化

## 不做
- 不重构原功能
- 不扩展原功能范围

---

## ━━━ 执行指令（复制下方内容给代码工具）━━━

执行修补工单 NN：修补描述

前置读取：
- AGENTS.md
- feature_list.json
- 工单/XX_original.md（原工单）
- docs/...

实现范围：
1. app/xxx/yyy.py — 修补说明

验证：
- pytest tests/test_XX_*.py（原功能测试仍通过）
- pytest tests/test_NN_patch.py（修补测试）

完成后：
1. 更新 feature_list.json：新增 FNN 修补条目，状态 passing
2. 更新 session-handoff.md

## ━━━ 执行指令结束 ━━━