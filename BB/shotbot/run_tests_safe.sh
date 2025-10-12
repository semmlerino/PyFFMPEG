#!/bin/bash
# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"

# Run all tests serially - safest option for debugging crashes

echo "Running all tests serially (safest mode)..."
echo "This will take longer but avoids parallelization issues"

# Set Qt to offscreen mode
export QT_QPA_PLATFORM=offscreen
export QT_LOGGING_RULES="*.debug=false"

# Run tests without parallelization
uv run pytest tests/ \
    -v \
    --tb=short \
    --strict-markers \
    --maxfail=10 \
    -ra \
    -n 0

echo "Test run complete!"