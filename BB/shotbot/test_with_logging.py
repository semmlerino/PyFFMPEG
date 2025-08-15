#!/usr/bin/env python3
"""Test shotbot with detailed logging."""

import logging
import os
import sys

# Enable debug logging
os.environ['SHOTBOT_DEBUG'] = '1'
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

print("=== Starting Shotbot with Logging ===")

# Run shotbot main
from shotbot import main

try:
    print("Calling main()...")
    main()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)