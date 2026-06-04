# Harness health check (Windows PowerShell)
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

Write-Host "=== AI Platform Init Check (PowerShell) ==="

function Resolve-Python {
    foreach ($pair in @(
            @{ Exe = "python"; Args = @("-c", "import sys") },
            @{ Exe = "py"; Args = @("-3", "-c", "import sys") }
        )) {
        try {
            & $pair.Exe @($pair.Args) 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                if ($pair.Exe -eq "py") { return "py -3" }
                return "python"
            }
        } catch { }
    }
    return $null
}

$python = Resolve-Python
if (-not $python) {
    Write-Host "  ERROR: Python not found (install Python 3.11+)"
    exit 1
}

Write-Host ""
Write-Host "[1/7] Checking Python environment..."
Invoke-Expression "$python -c `"import app; print('  OK: app module importable')`"" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  WARN: app module not importable (may need: pip install -e `".[dev]`")"
}

Write-Host ""
Write-Host "[2/7] Checking configuration..."
Invoke-Expression "$python -c `"import yaml; from pathlib import Path; p=Path('configs/default.yaml'); cfg=yaml.safe_load(p.read_text(encoding='utf-8')) if p.exists() else {}; print('  OK: config loaded (server port:', cfg.get('server',{}).get('port','unknown'), ')')`"" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "  WARN: Could not load config" }

Write-Host ""
Write-Host "[3/7] Checking feature list..."
Invoke-Expression "$python -c `"import json; fl=json.load(open('feature_list.json',encoding='utf-8')); fs=fl['features']; print('  OK:', sum(1 for f in fs if f['state']=='passing'), '/', len(fs), 'passing,', sum(1 for f in fs if f['state']=='in_progress'), 'in_progress')`"" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "  WARN: feature_list.json not found or invalid" }

Write-Host ""
Write-Host "[4/7] Running tests..."
if (Test-Path "tests") {
    Invoke-Expression "$python -m pytest tests/ -q --tb=no" 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "  OK: All tests passing" }
    else { Write-Host "  FAIL: Some tests failing — fix before proceeding"; exit 1 }
} else {
    Write-Host "  INFO: No tests directory yet"
}

Write-Host ""
Write-Host "[5/7] Checking FACT_REGISTRY consistency..."
Invoke-Expression "$python scripts/check_fact_registry.py"
if ($LASTEXITCODE -ne 0) { Write-Host "  WARN: FACT_REGISTRY consistency issues found (see above)" }

Write-Host ""
Write-Host "[6/7] Generating system-state.json..."
Invoke-Expression "$python scripts/update_system_state.py"

Write-Host ""
Write-Host "[7/7] Checking architecture dependencies..."
& "$PSScriptRoot\scripts\check-architecture.ps1"
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "=== Init Complete (7 steps) ==="
Write-Host "Next: Read AGENTS.md + feature_list.json + session-handoff.md"
