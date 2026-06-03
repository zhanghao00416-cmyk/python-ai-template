#!/usr/bin/env python3
"""Check FACT_REGISTRY.md consistency against other docs and configs.

Used by init.sh and init.ps1 as step [5/6].
Exit 0 = OK, exit 1 = warnings found (non-fatal for init).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check() -> list[str]:
    errors: list[str] = []

    registry = ROOT / "docs" / "00-meta" / "FACT_REGISTRY.md"
    if not registry.exists():
        return ["FACT_REGISTRY.md not found"]

    text = registry.read_text(encoding="utf-8")

    api_contract = ROOT / "docs" / "01-architecture" / "API_CONTRACT.md"
    if api_contract.exists():
        contract_text = api_contract.read_text(encoding="utf-8")
        event_pattern = r'\|\s*`(\w+)`\s*\|'
        contract_events = set(re.findall(event_pattern, contract_text))
        if contract_events and "frame_summary" in text:
            errors.append("FACT_REGISTRY still contains frame_summary (removed)")

    models_yaml = ROOT / "configs" / "models.yaml"
    if models_yaml.exists():
        try:
            import yaml
            with open(models_yaml, encoding="utf-8") as f:
                models = yaml.safe_load(f)
            routing_keys = set(models.get("routing", {}).keys())
            if "vision_entity" in text or "vision_hazard" in text:
                errors.append("FACT_REGISTRY still contains vision_entity/vision_hazard (should be multimodal)")
            if "multimodal" not in text and "multimodal" in routing_keys:
                errors.append("FACT_REGISTRY missing multimodal routing key")
        except ImportError:
            pass

    if "entity/hazard/video_hazard" in text:
        errors.append("FACT_REGISTRY still contains old intent types (entity/hazard/video_hazard)")

    return errors


def main() -> None:
    errors = check()
    if errors:
        for e in errors:
            print(f"  WARN: {e}")
        sys.exit(1)
    else:
        print("  OK: FACT_REGISTRY consistent")
        sys.exit(0)


if __name__ == "__main__":
    main()
