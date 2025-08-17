#!/usr/bin/env python3
"""Debug where the app hangs."""

import logging
import os

# Enable all debug logging
os.environ["SHOTBOT_DEBUG"] = "1"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

print("=== Debugging Hang ===")

# Test just the ProcessPoolManager directly
from process_pool_manager import ProcessPoolManager

print("\n1. Creating ProcessPoolManager...")
pm = ProcessPoolManager.get_instance()
print("✓ ProcessPoolManager created")

print("\n2. Executing test command...")
try:
    result = pm.execute_workspace_command("echo 'hello'", timeout=3)
    print(f"✓ Command executed: {result[:50] if result else 'empty'}")
except Exception as e:
    print(f"✗ Command failed: {e}")
    import traceback

    traceback.print_exc()

print("\n3. Shutting down...")
pm.shutdown()
print("✓ Shutdown complete")

print("\nDone!")
