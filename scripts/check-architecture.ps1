$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot\..

Write-Host "=== Architecture Dependency Check ==="

$APP_DIR = "app"
$VIOLATIONS = 0

function Check-Import {
    param(
        [string]$FromLayer,
        [string]$Forbidden,
        [string]$Description
    )

    $layerDir = Join-Path $APP_DIR $FromLayer
    if (-not (Test-Path $layerDir)) {
        return
    }

    $found = Get-ChildItem -Path $layerDir -Recurse -Include "*.py" -ErrorAction SilentlyContinue |
        Select-String -Pattern "from $($Forbidden -replace '\.','\.')" -SimpleMatch:$false |
        Select-Object -Property Path, LineNumber, Line

    if ($found) {
        Write-Host "VIOLATION: $Description"
        $found | ForEach-Object {
            Write-Host "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())"
        }
        Write-Host ""
        $script:VIOLATIONS += 1
    }
}

Write-Host "[1] Checking: api should not directly import from infra..."
Check-Import -FromLayer "api" -Forbidden "app.infra" -Description "api -> infra (must go through domain/services)"

Write-Host "[2] Checking: domain should not directly import LLM providers..."
Check-Import -FromLayer "domain" -Forbidden "litellm" -Description "domain -> litellm (must go through services/llm)"

Write-Host "[3] Checking: infra should not import domain..."
Check-Import -FromLayer "infra" -Forbidden "app.domain" -Description "infra -> domain (forbidden reverse dependency)"

Write-Host "[4] Checking: infra should not import api..."
Check-Import -FromLayer "infra" -Forbidden "app.api" -Description "infra -> api (forbidden reverse dependency)"

Write-Host "[5] Checking: services should not import api..."
Check-Import -FromLayer "services" -Forbidden "app.api" -Description "services -> api (forbidden reverse dependency)"

Write-Host "[6] Checking: middleware should not import domain..."
Check-Import -FromLayer "middleware" -Forbidden "app.domain" -Description "middleware -> domain (forbidden)"

Write-Host ""
if ($VIOLATIONS -eq 0) {
    Write-Host "[OK] All architecture dependency checks passed."
    exit 0
} else {
    Write-Host "[FAIL] Found $VIOLATIONS violation(s). See above for details."
    exit 1
}
