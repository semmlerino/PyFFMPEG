#!/bin/bash
# Run ShotBot with software rendering (no OpenGL) for WSL

echo "Starting ShotBot with SOFTWARE RENDERING (for WSL)"
echo "=================================================="
echo ""

# Kill any existing processes
pkill -f shotbot.py 2>/dev/null
sleep 1

# Use software rendering to avoid OpenGL issues
export QT_QPA_PLATFORM=offscreen
export QT_QPA_PLATFORM_PLUGIN_PATH=$(./venv/bin/python -c "import PySide6; import os; print(os.path.dirname(PySide6.__file__) + '/Qt/plugins')")

# Or try with minimal platform
# export QT_QPA_PLATFORM=minimal

# Disable OpenGL
export QT_OPENGL=software
export LIBGL_ALWAYS_SOFTWARE=1
export MESA_GL_VERSION_OVERRIDE=3.3
export MESA_GLSL_VERSION_OVERRIDE=330

# Set display
export DISPLAY=:0

# Enable mock mode
export SHOTBOT_MOCK=1

echo "Settings:"
echo "  - Platform: offscreen (no GUI window)"
echo "  - Mock mode: enabled"
echo "  - OpenGL: disabled/software"
echo ""
echo "This will run without displaying a window,"
echo "but will test if the app can start properly."
echo ""

# Run with timeout to see if it starts
timeout 5 ./venv/bin/python shotbot.py --mock 2>&1 | grep -E "(Mock|demo|loaded|ERROR|CRITICAL)" || true

echo ""
echo "=================================================="
echo "Test complete. Check above for any errors."
echo ""
echo "If you see 'Mock ProcessPoolManager injected',"
echo "then the mock mode is working correctly."