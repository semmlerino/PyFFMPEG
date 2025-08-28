#!/bin/bash
# Run fast tests only - suitable for CI/CD on every PR
# Excludes slow, performance, and stress tests
# Expected runtime: ~30-40 seconds

echo "🚀 Running fast test suite..."
echo "================================"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run tests excluding slow categories
python -m pytest tests/ \
    -m "not slow and not performance and not stress" \
    --tb=short \
    --maxfail=10 \
    --timeout=10 \
    -q

# Capture exit code
EXIT_CODE=$?

# Summary
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Fast tests passed!"
else
    echo "❌ Fast tests failed with exit code $EXIT_CODE"
fi

exit $EXIT_CODE