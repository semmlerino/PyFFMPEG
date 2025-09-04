#!/bin/bash
# Script to run ShotBot with proper WSL/X11 settings

echo "Starting ShotBot with mock mode in WSL..."
echo "================================================"

# Kill any existing shotbot processes
echo "Cleaning up any existing processes..."
pkill -f shotbot.py 2>/dev/null
sleep 1

# Set up X11 display for WSL
export DISPLAY=${DISPLAY:-:0}
echo "Display set to: $DISPLAY"

# Set Qt platform explicitly
export QT_QPA_PLATFORM=xcb
echo "Qt platform: $QT_QPA_PLATFORM"

# Create runtime directory if needed
export XDG_RUNTIME_DIR=/tmp/runtime-$USER
mkdir -p $XDG_RUNTIME_DIR

# Disable Qt accessibility (can cause issues in WSL)
export QT_ACCESSIBILITY=0

# Run ShotBot with mock mode
echo ""
echo "Launching ShotBot..."
echo "================================================"
echo ""
echo "If you see the window but can't interact with it:"
echo "  1. Try Alt+Tab to switch to it"
echo "  2. Click on the window title bar"
echo "  3. Check if it's behind other windows"
echo ""
echo "The window should show:"
echo "  - 'My Shots' tab with 12 demo shots"
echo "  - 'Other 3DE scenes' tab"
echo ""
echo "Press Ctrl+C to stop"
echo "================================================"
echo ""

# Run in foreground so we can see any errors
./venv/bin/python shotbot.py --mock