#!/bin/bash
# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"

# Final working launcher for ShotBot mock mode

echo "🚀 ShotBot Mock Mode Launcher"
echo "=============================="
echo ""
echo "Starting ShotBot with mock VFX data..."
echo "The app will show 12 demo shots from:"
echo "  - gator"
echo "  - jack_ryan"
echo "  - broken_eggs"
echo ""

# Kill any existing instances
pkill -f shotbot 2>/dev/null
sleep 1

# Run the mock version with early injection
echo "Launching window..."
uv run python shotbot_mock.py

echo ""
echo "ShotBot closed."