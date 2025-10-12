#!/bin/bash
# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"

# Type checking script for shotbot

# Run basedpyright with stats
echo "Running basedpyright type checking..."
uv run basedpyright --stats

# Exit with the same code as basedpyright
exit $?