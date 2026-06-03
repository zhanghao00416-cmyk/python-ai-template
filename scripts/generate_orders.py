#!/usr/bin/env python3
"""Generate work order markdown files and feature_list.json from work_orders.yaml.

WARNING: Default run updates feature_list.json but MERGES existing state/evidence by feature id.
         Use --orders-only when you only changed work_orders.yaml and must not touch progress.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
YAML_PATH = ROOT / "configs_work_orders" / "work_orders.yaml"
ORDERS_DIR = ROOT / "工单"
FEATURE_LIST_PATH = ROOT / "feature_list.json"

FEATURE_TO_ORDER_STATE = {
    "in_progress": "active",
    "active": "active",
    "passing": "passing",
    "not_started": "not_started",
    "blocked": "blocked",
}

# Table 1 from docs/00-meta/DEPENDENCY_MAP.md (code dependencies)
ORDER_CODE_DEPS: dict[str, list[str]] = {
    "F02": ["F01: `app/main.py`, `app/core/config.py`, `app/core/di.py`"],
    "F03": ["F01: `app/core/errors.py`, `app/core/response.py`, `app/core/context.py`"],
    "F04": ["F01: `app/core/config.py`", "F03: `app/core/errors.py`, `app/middleware/*`"],
    "F05": ["F02: `app/infra/database.py`, `app/infra/redis_client.py`"],
    "F06": ["F03: `app/core/response.py`, `app/core/constants.py`"],
    "F07": ["F02: `app/infra/redis_client.py`"],
    "F08": ["F01: `app/core/config.py`"],
    "F09": ["F02: `app/infra/database.py`, `app/domain/*/repo.py`"],
    "F10": ["F01: `app/core/di.py`"],
    "F11": ["F04: `app/services/llm/gateway.py`", "F10: `app/tools/registry.py`"],
    "F12": ["F11: `app/agent/base.py`, `app/agent/state.py`, `app/agent/react.py`"],
    "F13": ["F10: `app/tools/registry.py`"],
    "F14": [
        "F06: `app/services/sse_stream.py`",
        "F09: `app/services/context_manager.py`",
        "F04: `app/services/llm/gateway.py`",
    ],
    "F15a": ["F05: `app/infra/vector_store.py`", "F08: `app/services/prompt_manager.py`"],
    "F15b": ["F15a: `app/domain/knowledge/service.py`", "F06: `app/services/sse_stream.py`"],
    "F15c": ["F15b: `app/domain/knowledge/service.py`", "`app/api/v1/knowledge.py`"],
    "F16": ["F04: `app/services/llm/gateway.py`", "F08: `app/services/prompt_manager.py`"],
    "F17": ["F08: `app/services/prompt_manager.py`"],
    "F18": [
        "F03: `app/core/logging.py`, `app/core/tracing.py`",
        "F04: `app/services/llm/gateway.py`",
    ],
    "F19": ["F11: `app/agent/base.py`, `app/agent/state.py`"],
    "F20": ["F02: `app/infra/redis_client.py`", "F03: `app/middleware/exception.py`"],
    "F21": ["F01–F14, F15a, F15b, F15c, F16–F20 全部前序代码"],
}

DEFAULT_PHASE2_CHECKLIST = """| 路径 | 职责 |
|------|------|
| `app/schemas/` | 请求/响应模型（对齐 API_CONTRACT） |
| `app/domain/` | 领域 service + repo（如需持久化） |
| `app/services/` | 可复用服务（如需） |
| `app/infra/` | 外部依赖适配（如需） |
| `app/api/v1/` | 路由注册（无业务逻辑） |
| `tests/test_{fid_lower}_*.py` | 工单验证测试 |

> 工单 YAML 未配置 `phase2_checklist` 时使用上表；阶段 1 须根据 docs 细化路径。"""


def load_yaml() -> dict:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_existing_features() -> dict[str, dict]:
    if not FEATURE_LIST_PATH.exists():
        return {}
    try:
        data = json.loads(FEATURE_LIST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {f["id"]: f for f in data.get("features", []) if "id" in f}


def load_existing_meta() -> dict:
    if not FEATURE_LIST_PATH.exists():
        return {}
    try:
        data = json.loads(FEATURE_LIST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        "current_phase": data.get("current_phase", 1),
        "project": data.get("project"),
        "description": data.get("description"),
    }


ORDER_SLUGS = {
    "F01": "project_skeleton",
    "F02": "database_models_redis",
    "F03": "error_middleware",
    "F04": "llm_gateway",
    "F05": "vector_store_qdrant",
    "F06": "sse_stream",
    "F07": "task_queue_arq",
    "F08": "prompt_manager",
    "F09": "context_manager",
    "F10": "tools_mcp_registry",
    "F11": "agent_base_state_react",
    "F12": "multi_agent_orchestrator",
    "F13": "workflow_dag_engine",
    "F14": "chat_domain",
    "F15a": "knowledge_qa_domain_chunking_upload",
    "F15b": "knowledge_qa_domain_rag_query_rerank",
    "F15c": "knowledge_qa_domain_e2e",
    "F16": "intent_domain",
    "F17": "prompt_admin_api",
    "F18": "observability_tracing_metrics",
    "F19": "eval_framework",
    "F20": "auth_rate_limit",
    "F21": "integration_docker_production",
}


def slugify(order_id: str, name: str) -> str:
    if order_id in ORDER_SLUGS:
        return ORDER_SLUGS[order_id]
    slug = name.lower()
    for ch in " /()+(),（）":
        slug = slug.replace(ch, "_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def order_state_label(feature_state: str | None) -> str:
    if not feature_state:
        return "not_started"
    return FEATURE_TO_ORDER_STATE.get(feature_state, "not_started")


def _code_deps_block(fid: str) -> str:
    lines = ORDER_CODE_DEPS.get(fid)
    if not lines:
        return "- 无跨工单硬代码依赖（仍须读 DEPENDENCY_MAP 与本工单 docs）"
    return "\n".join(f"- {line}" for line in lines)


def _phase2_block(order: dict, fid: str) -> str:
    custom = order.get("phase2_checklist")
    if custom:
        return custom.strip()
    return DEFAULT_PHASE2_CHECKLIST.replace("{fid_lower}", fid.lower())


def _phase3_doc_sync_block(order: dict) -> str:
    items = order.get("phase3_doc_sync") or []
    if not items:
        return "- 本工单改动的 API/错误码/数据模型须同步对应 `docs/`（见 DEPENDENCY_MAP 表 2）\n- 将相关 `[TBD: filled by Fxx]` 改为 `[filled by Fxx]`"
    return "\n".join(f"- {item}" for item in items)


def generate_order(order: dict, phase_name: str, feature_state: str | None = None) -> str:
    fid = order["id"]
    name = order["name"]
    behavior = order.get("behavior", "")
    verification = order.get("verification", "")
    dependencies = order.get("dependencies", [])
    docs = order.get("docs", [])

    dep_str = ", ".join(dependencies) if dependencies else "无"
    docs_str = "\n".join(f"- `{d}`" for d in docs) if docs else "- 无"
    meta_state = order_state_label(feature_state)
    code_deps = _code_deps_block(fid)
    phase2 = _phase2_block(order, fid)
    phase3_sync = _phase3_doc_sync_block(order)
    test_glob = f"test_{fid.lower().replace('-', '_')}"

    return f"""# 工单 {fid}：{name}

## 元数据
- **id**: {fid}
- **state**: {meta_state}
- **dependencies**: [{dep_str}]
- **patches**: 无
- **supersedes**: 无
- **superseded-by**: 无

## 功能三元组
- **行为**：{behavior}
- **验证**：`{verification}`
- **状态**：not_started → active → passing

## 验收标准（全部通过才能标 passing）
- [ ] `{verification}` 通过
- [ ] 分层依赖检查通过（`scripts/check-architecture.sh` 或 Windows 等价流程）
- [ ] 相关测试通过（pytest）
- [ ] `feature_list.json` 状态 + evidence 已更新

## 关键约束
- 依赖方向严格遵守 `ARCHITECTURE.md`
- 错误码：`docs/01-architecture/ERROR_CODE.md`（REST 整数 code；SSE 用 `AI_%04d`）
- 主 API 选型：`API_CONTRACT.md`「API 选型决策表」（F14+ 业务域必读）
- Phase: {phase_name}
- `[TBD: filled by Fxx]` 见 `AGENTS.md` §0.3 — 不表示章节为空

## 不做（本工单范围外）
- 不做本功能三元组描述之外的事情
- 不修改已 passing 功能的代码（走 `docs/00-meta/CHANGE_WORKFLOW.md`）

---

## ━━━ 阶段 1：只读不写（禁止生成代码）━━━

### 1.1 前序代码依赖（必须 read_file）

{code_deps}

### 1.2 必读 docs（DEPENDENCY_MAP 表 2 + 工单列表）

{docs_str}
- `docs/00-meta/DEPENDENCY_MAP.md`（本工单 {fid} 行）
- `ARCHITECTURE.md`（分层规则）

### 1.3 阶段 1 交付物

1. 与现有实现/契约的差异清单
2. 错误码与边界条件（引用 ERROR_CODE 表号）
3. 预计新增/修改文件清单（可与 §2.2 对照，允许阶段 1 微调）
4. 明确「不做」范围确认
5. （可选）`TestNewHarness/` 对照差异表 — 见 `docs/00-meta/DEPENDENCY_MAP.md` 表 3

### 1.4 可选外部参考（TestNewHarness）

- 路径：`TestNewHarness/`（本仓库子目录，**非** Python 依赖）
- 索引：`docs/00-meta/DEPENDENCY_MAP.md` **表 3**（工单 → 老项目只读路径）
- **阶段 1**：只读；**阶段 2**：按差异表重写，**禁止**整文件复制

**阶段 1 通过后才可进入阶段 2。**

---

## ━━━ 阶段 2：正式生成代码 ━━━

### 2.1 契约对齐（填写或确认）

| 项 | 约定 |
|----|------|
| 路由 / 能力 | （从 API_CONTRACT 或工单行为填写） |
| 响应 | JSON envelope / SSE（见 SSE_STREAM_SPEC） |
| 错误 | REST 整数 `code`；SSE `error` 用 `AI_%04d` |

### 2.2 实现清单（路径级）

{phase2}

### 2.3 环境 / 命令

- 验证：`{verification}`
- 若依赖 PG/Redis/Qdrant：`docker compose up -d postgres redis`（按需）

---

## ━━━ 阶段 3：自审、验证、交接 ━━━

1. 对照 `evaluator-rubric.md` 自审（无 Block 项）
2. 契约与分层：`API_CONTRACT` / `ARCHITECTURE` / `check-architecture`
3. docs 同步：

{phase3_sync}

4. 更新 `feature_list.json`（passing + evidence）、`progress.md`（§7.1 下一任务）、`session-handoff.md`

---

## ━━━ 执行指令（复制给代码工具）━━━

```text
按 AGENTS.md §0.1 启动；执行工单 {fid}，严格阶段 1→2→3。
阶段 1：读 DEPENDENCY_MAP {fid} 行 + 上文 docs + 前序代码，首段约束摘要 ≥5 条，输出 §1.3 交付物，禁止写代码。
阶段 2：仅实现 §2.2 清单；验证：{verification}
阶段 3：自审 + 更新 feature_list / progress / session-handoff
```

## ━━━ 执行指令结束 ━━━
"""


def generate_feature_list(data: dict, existing: dict[str, dict], meta: dict) -> dict:
    features = []
    for phase in data["phases"]:
        for order in phase["orders"]:
            fid = order["id"]
            prior = existing.get(fid, {})
            features.append({
                "id": fid,
                "name": order["name"],
                "behavior": order.get("behavior", prior.get("behavior", "")),
                "verification": order.get("verification", prior.get("verification", "")),
                "state": prior.get("state", "not_started"),
                "evidence": prior.get("evidence", ""),
            })
    return {
        "project": meta.get("project") or data["project"],
        "description": meta.get("description") or data.get("description", ""),
        "current_phase": meta.get("current_phase", 1),
        "features": features,
    }


def generate_orders(data: dict, *, orders_only: bool = False) -> None:
    existing = load_existing_features()
    meta = load_existing_meta()
    ORDERS_DIR.mkdir(parents=True, exist_ok=True)

    for phase in data["phases"]:
        for order in phase["orders"]:
            fid = order["id"]
            name = order["name"]
            slug = slugify(fid, name)
            filename = f"{fid}_{slug}.md"
            filepath = ORDERS_DIR / filename
            prior = existing.get(fid, {})
            content = generate_order(order, phase["name"], prior.get("state"))
            filepath.write_text(content, encoding="utf-8")
            print(f"  Generated: 工单/{filename}")

    if orders_only:
        print("  Skipped: feature_list.json (--orders-only)")
        return

    feature_list = generate_feature_list(data, existing, meta)
    with open(FEATURE_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(feature_list, f, ensure_ascii=False, indent=2)
        f.write("\n")
    passing = sum(1 for x in feature_list["features"] if x["state"] == "passing")
    print(
        f"  Updated: feature_list.json ({len(feature_list['features'])} features, "
        f"{passing} passing — state/evidence preserved)"
    )


def generate_patch(order_id: str, patch_name: str, patches_id: str) -> str:
    next_num = max(
        int(f["id"][1:])
        for f in json.loads(FEATURE_LIST_PATH.read_text(encoding="utf-8"))["features"]
    ) + 1
    fid = f"F{next_num:02d}"
    slug = slugify(patch_name)
    filename = f"{fid}_{slug}_patch.md"

    content = f"""# 修补工单 {fid}：{patch_name}

## 元数据
- **id**: {fid}
- **state**: not_started
- **dependencies**: [{patches_id}]
- **patches**: {patches_id}

## 修补原因
（填写）

## 验收标准
- [ ] 原 {patches_id} 测试仍通过
- [ ] 修补验证通过

---

## ━━━ 执行指令 ━━━

执行修补工单 {fid}：{patch_name}；前置读原工单 `工单/{patches_id}_*.md`。

## ━━━ 执行指令结束 ━━━
"""
    filepath = ORDERS_DIR / filename
    filepath.write_text(content, encoding="utf-8")
    print(f"  Generated patch: 工单/{filename}")
    return filename


def validate_dependencies(data: dict) -> list[str]:
    errors = []
    all_ids = set()
    dep_map = {}

    for phase in data["phases"]:
        for order in phase["orders"]:
            fid = order["id"]
            deps = order.get("dependencies", [])
            all_ids.add(fid)
            dep_map[fid] = deps

    for fid, deps in dep_map.items():
        for dep in deps:
            if dep not in all_ids:
                errors.append(f"  {fid} depends on {dep}, but {dep} not found in work_orders.yaml")

    for fid, deps in dep_map.items():
        for dep in deps:
            if fid in dep_map.get(dep, []):
                errors.append(f"  Cycle detected: {fid} <-> {dep}")

    dep_map_path = ROOT / "docs" / "00-meta" / "DEPENDENCY_MAP.md"
    if dep_map_path.exists():
        text = dep_map_path.read_text(encoding="utf-8")
        for fid in all_ids:
            if fid not in text:
                errors.append(f"  {fid} not found in DEPENDENCY_MAP.md")

    return errors


def main():
    if not YAML_PATH.exists():
        print(f"Error: {YAML_PATH} not found", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Generate work orders from YAML")
    parser.add_argument(
        "--orders-only",
        action="store_true",
        help="Regenerate 工单/*.md only; do not write feature_list.json",
    )
    parser.add_argument(
        "--patch",
        nargs=2,
        metavar=("PATCHES_ID", "NAME"),
        help="Generate a patch order",
    )
    args = parser.parse_args()

    data = load_yaml()

    dep_errors = validate_dependencies(data)
    if dep_errors:
        print("\n=== Dependency Validation Warnings ===")
        for e in dep_errors:
            print(e)
        print()

    print("=== Generating work orders ===")
    generate_orders(data, orders_only=args.orders_only)

    if args.patch:
        print(f"\n=== Generating patch order for {args.patch[0]} ===")
        generate_patch("", args.patch[1], args.patch[0])

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
