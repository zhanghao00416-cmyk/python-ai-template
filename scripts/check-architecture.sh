#!/bin/bash
# Architecture dependency check script
# Verifies that layer dependencies follow ARCHITECTURE.md rules

set -e

echo "=== Architecture Dependency Check ==="

APP_DIR="app"
VIOLATIONS=0

check_import() {
    local from_layer="$1"
    local forbidden="$2"
    local description="$3"
    
    local found
    found=$(grep -r "from ${forbidden}" "${APP_DIR}/${from_layer}/" 2>/dev/null || true)
    
    if [ -n "$found" ]; then
        echo "VIOLATION: ${description}"
        echo "$found"
        echo ""
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
}

echo "[1] Checking: api should not directly import from infra..."
check_import "api" "app.infra" "api → infra (must go through domain/services)"

echo "[2] Checking: domain should not directly import LLM providers..."
check_import "domain" "litellm" "domain → litellm (must go through services/llm)"

echo "[3] Checking: infra should not import domain..."
check_import "infra" "app.domain" "infra → domain (forbidden reverse dependency)"

echo "[4] Checking: infra should not import api..."
check_import "infra" "app.api" "infra → api (forbidden reverse dependency)"

echo "[5] Checking: services should not import api..."
check_import "services" "app.api" "services → api (forbidden reverse dependency)"

echo "[6] Checking: middleware should not import domain..."
check_import "middleware" "app.domain" "middleware → domain (forbidden)"

echo ""
if [ $VIOLATIONS -eq 0 ]; then
    echo "✓ All architecture dependency checks passed."
    exit 0
else
    echo "✗ Found ${VIOLATIONS} violation(s). See above for details."
    exit 1
fi