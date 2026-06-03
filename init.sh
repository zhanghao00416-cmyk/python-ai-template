#!/bin/bash
set -e

echo "=== AI Platform Init Check ==="

# Resolve Python (Git Bash / WSL / Linux / Windows py launcher)
PYTHON=""
if command -v python3 >/dev/null 2>&1 && python3 -c "import sys" 2>/dev/null; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1 && python -c "import sys" 2>/dev/null; then
  PYTHON=python
elif command -v py >/dev/null 2>&1 && py -3 -c "import sys" 2>/dev/null; then
  PYTHON="py -3"
fi
if [ -z "$PYTHON" ]; then
  echo "  ERROR: No Python found (tried python3, python, py -3)"
  echo "  Windows tip: run ./init.ps1 from PowerShell instead"
  exit 1
fi

echo ""
echo "[1/6] Checking Python environment..."
$PYTHON -c "import app; print('  OK: app module importable')" 2>/dev/null \
  || echo "  WARN: app module not importable (may need: pip install -e \".[dev]\")"

echo ""
echo "[2/6] Checking configuration..."
$PYTHON -c "
import yaml
from pathlib import Path
config_path = Path('configs/default.yaml')
if config_path.exists():
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    print(f'  OK: config loaded (server port: {cfg.get(\"server\", {}).get(\"port\", \"unknown\")})')
else:
    print('  WARN: configs/default.yaml not found')
" 2>/dev/null || echo "  WARN: Could not load config (install pyyaml)"

echo ""
echo "[3/6] Checking feature list..."
$PYTHON -c "
import json
from pathlib import Path
fl_path = Path('feature_list.json')
if fl_path.exists():
    with open(fl_path, encoding='utf-8') as f:
        fl = json.load(f)
    features = fl['features']
    passing = sum(1 for f in features if f['state'] == 'passing')
    in_progress = sum(1 for f in features if f['state'] == 'in_progress')
    total = len(features)
    print(f'  OK: {passing}/{total} passing, {in_progress} in_progress')
else:
    print('  WARN: feature_list.json not found')
"

echo ""
echo "[4/6] Running tests..."
if [ -d "tests" ]; then
    $PYTHON -m pytest tests/ -q --tb=no 2>/dev/null && echo "  OK: All tests passing" || echo "  WARN: Some tests failing (expected before implementation)"
else
    echo "  INFO: No tests directory yet (will be created with F01)"
fi

echo ""
echo "[5/6] Checking FACT_REGISTRY consistency..."
$PYTHON scripts/check_fact_registry.py 2>/dev/null || echo "  WARN: Could not check FACT_REGISTRY consistency"

echo ""
echo "[6/6] Generating system-state.json..."
$PYTHON scripts/update_system_state.py

echo ""
echo "=== Init Complete (6 steps) ==="
echo "Next step: Read AGENTS.md + feature_list.json + session-handoff.md"
echo "Then: Open the work order file pointed by session-handoff.md Next pointer"
