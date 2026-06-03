#!/usr/bin/env python3
"""Write system-state.json from feature_list.json (used by init.sh / init.ps1)."""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURE_LIST = ROOT / "feature_list.json"
STATE_PATH = ROOT / "system-state.json"


def main() -> None:
    state = {
        "last_check": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checks": {
            "database": {"status": "not_checked", "migrations": 0, "latest": None},
            "redis": {"status": "not_checked", "ping_ms": None},
            "qdrant": {"status": "not_checked", "collections": []},
            "llm_gateway": {"status": "not_checked", "providers": {}},
            "task_queue": {"status": "not_checked"},
            "apis": {"health": "not_checked"},
        },
        "feature_summary": {},
    }

    if FEATURE_LIST.exists():
        fl = json.loads(FEATURE_LIST.read_text(encoding="utf-8"))
        features = fl.get("features", [])
        state["feature_summary"] = {
            "passing": sum(1 for f in features if f["state"] == "passing"),
            "in_progress": sum(1 for f in features if f["state"] == "in_progress"),
            "active": sum(1 for f in features if f["state"] in ("active", "in_progress")),
            "not_started": sum(1 for f in features if f["state"] == "not_started"),
            "blocked": sum(1 for f in features if f["state"] == "blocked"),
        }
        if any(f["id"] == "F01" and f["state"] == "passing" for f in features):
            state["checks"]["apis"]["health"] = "passing_via_tests"

    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("  OK: system-state.json updated")


if __name__ == "__main__":
    main()
