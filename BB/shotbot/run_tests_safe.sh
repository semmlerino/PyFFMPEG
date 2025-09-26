#!/bin/bash
# Run all tests serially - safest option for debugging crashes

echo "Running all tests serially (safest mode)..."
echo "This will take longer but avoids parallelization issues"

# Activate virtual environment if it exists
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi

# Set Qt to offscreen mode
export QT_QPA_PLATFORM=offscreen
export QT_LOGGING_RULES="*.debug=false"

# Run tests without parallelization
python -m pytest tests/ \
    -v \
    --tb=short \
    --strict-markers \
    --maxfail=10 \
    -ra \
    -n 0

echo "Test run complete!"