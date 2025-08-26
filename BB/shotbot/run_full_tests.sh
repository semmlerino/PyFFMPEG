#!/bin/bash
# Run full test suite - suitable for main branch and releases
# Includes all tests except performance benchmarks
# Expected runtime: ~2-3 minutes

echo "🔬 Running full test suite..."
echo "================================"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run unit tests first (most likely to fail fast)
echo "📦 Running unit tests..."
python -m pytest tests/unit/ \
    -m "not performance" \
    --tb=short \
    --maxfail=10 \
    --timeout=30 \
    -q

UNIT_EXIT=$?

if [ $UNIT_EXIT -ne 0 ]; then
    echo "❌ Unit tests failed!"
    exit $UNIT_EXIT
fi

# Run integration tests
echo "🔗 Running integration tests..."
python -m pytest tests/integration/ \
    --tb=short \
    --maxfail=10 \
    --timeout=30 \
    -q

INT_EXIT=$?

if [ $INT_EXIT -ne 0 ]; then
    echo "❌ Integration tests failed!"
    exit $INT_EXIT
fi

# Run slow tests
echo "🐢 Running slow tests..."
python -m pytest tests/ \
    -m "slow" \
    --tb=short \
    --maxfail=5 \
    --timeout=60 \
    -q

SLOW_EXIT=$?

# Summary
echo "================================"
echo "Test Results:"
echo "  Unit tests: $([ $UNIT_EXIT -eq 0 ] && echo '✅ PASS' || echo '❌ FAIL')"
echo "  Integration tests: $([ $INT_EXIT -eq 0 ] && echo '✅ PASS' || echo '❌ FAIL')"
echo "  Slow tests: $([ $SLOW_EXIT -eq 0 ] && echo '✅ PASS' || echo '❌ FAIL')"

# Return non-zero if any failed
if [ $UNIT_EXIT -ne 0 ] || [ $INT_EXIT -ne 0 ] || [ $SLOW_EXIT -ne 0 ]; then
    exit 1
fi

echo "✅ All tests passed!"
exit 0