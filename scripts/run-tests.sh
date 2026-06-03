#!/bin/bash
# Run all tests with verbose output
set -e

echo "=== Running Tests ==="

# Determine test scope
SCOPE="${1:-all}"

case "$SCOPE" in
    unit)
        echo "Running unit tests only..."
        python -m pytest tests/ -v --tb=short -k "not integration"
        ;;
    integration)
        echo "Running integration tests only..."
        python -m pytest tests/ -v --tb=short -k "integration"
        ;;
    all)
        echo "Running all tests..."
        python -m pytest tests/ -v --tb=short
        ;;
    *)
        # Run specific test file
        echo "Running: $SCOPE"
        python -m pytest "$SCOPE" -v --tb=short
        ;;
esac

echo ""
echo "=== Tests Complete ==="