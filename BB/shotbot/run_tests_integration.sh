#!/bin/bash
# Run integration tests serially to avoid Qt crashes

echo "Running integration tests serially..."

# Activate virtual environment if it exists
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi

# Set Qt to offscreen mode
export QT_QPA_PLATFORM=offscreen
export QT_LOGGING_RULES="*.debug=false"

# Run integration tests serially
python -m pytest tests/integration/ \
    -v \
    --tb=short \
    --strict-markers \
    --maxfail=10 \
    -ra \
    -n 0

echo "Integration test run complete!"