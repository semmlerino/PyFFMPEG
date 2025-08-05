#!/bin/bash
# Quick diagnostic script for 3DE scene finding issues

# Activate virtual environment
source ../../venv/bin/activate

# Enable debug logging
export SHOTBOT_DEBUG=1

# Run diagnostic on a test workspace (replace with your actual shot path)
# Example: /shows/myshow/shots/seq001/shot010
WORKSPACE_PATH="$1"

if [ -z "$WORKSPACE_PATH" ]; then
    echo "Usage: ./run_diagnostic.sh /path/to/shot/workspace"
    echo "Example: ./run_diagnostic.sh /shows/myshow/shots/seq001/shot010"
    exit 1
fi

echo "Running 3DE diagnostic on: $WORKSPACE_PATH"
echo "======================================"
python threede_diagnostic.py "$WORKSPACE_PATH" --verbose

echo ""
echo "Now checking if 3DE scenes load in the application..."
echo "Starting shotbot with debug logging..."
python shotbot.py