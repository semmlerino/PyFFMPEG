#!/bin/bash
# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"

# Run integration tests serially to avoid Qt crashes

echo "Running integration tests serially..."

# Set Qt to offscreen mode
export QT_QPA_PLATFORM=offscreen
export QT_LOGGING_RULES="*.debug=false"

# Run integration tests serially
uv run pytest tests/integration/ \
    -v \
    --tb=short \
    --strict-markers \
    --maxfail=10 \
    -ra \
    -n 0

echo "Integration test run complete!"