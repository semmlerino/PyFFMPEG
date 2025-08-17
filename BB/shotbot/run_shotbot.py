#!/usr/bin/env python3
"""Run Shotbot with monitoring."""

import signal
import sys
from pathlib import Path

# Add the shotbot directory to path
sys.path.insert(0, str(Path(__file__).parent))

print("Starting Shotbot...")
print("Press Ctrl+C to stop")

# Import shotbot main
from shotbot import main


# Set up a signal handler for clean shutdown
def signal_handler(sig, frame):
    print("\nShutting down Shotbot...")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

# Run main
try:
    main()
except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
