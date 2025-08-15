#!/bin/bash
# Run Shotbot with verbose debug logging enabled
# This helps diagnose crashes, hangs, and other issues

echo "Starting Shotbot with verbose debug logging..."
echo "Log file: shotbot_debug_$(date +%Y%m%d_%H%M%S).log"
echo "=========================================="

# Enable verbose debug mode
export SHOTBOT_DEBUG_VERBOSE=1
export SHOTBOT_DEBUG=1

# Run with logging to both console and file
python3 shotbot.py 2>&1 | tee "shotbot_debug_$(date +%Y%m%d_%H%M%S).log"