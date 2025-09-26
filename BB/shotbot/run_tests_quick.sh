#!/bin/bash
# Run only quick tests in parallel

echo "Running quick tests only (parallel execution)..."

# Activate virtual environment if it exists
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi

# Set Qt to offscreen mode
export QT_QPA_PLATFORM=offscreen
export QT_LOGGING_RULES="*.debug=false"

# Run only fast unit tests in parallel
python -m pytest tests/ \
    -m "unit and not slow and not qt_heavy" \
    -v \
    --tb=short \
    --strict-markers \
    --maxfail=5 \
    -ra \
    -n auto

echo "Quick test run complete!"