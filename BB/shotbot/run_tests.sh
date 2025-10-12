#!/bin/bash
# Run tests properly in WSL environment

# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"

# Run pytest with uv
uv run pytest tests/ "$@"