#!/bin/bash
# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"

# Run only quick tests in parallel

echo "Running quick tests only (parallel execution)..."

# Set Qt to offscreen mode
export QT_QPA_PLATFORM=offscreen
export QT_LOGGING_RULES="*.debug=false"

# Run only fast unit tests in parallel
uv run pytest tests/ \
    -m "unit and not slow and not qt_heavy" \
    -v \
    --tb=short \
    --strict-markers \
    --maxfail=5 \
    -ra \
    -n auto

echo "Quick test run complete!"