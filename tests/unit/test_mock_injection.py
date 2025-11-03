#!/usr/bin/env python3
"""Test that mock injection works correctly without GUI."""

# Standard library imports
import os
import sys


# Enable mock mode
os.environ["SHOTBOT_MOCK"] = "1"

print("Testing mock injection...")
print("=" * 50)

# Local application imports
# Import test doubles first
from tests.test_doubles_library import TestProcessPool


# Create mock pool
mock_pool = TestProcessPool()
mock_pool.set_outputs(
    "workspace /shows/demo/shots/seq01/seq01_0010",
    "workspace /shows/demo/shots/seq01/seq01_0020",
)

# Local application imports
# Now inject it BEFORE importing ProcessPoolManager
import process_pool_manager


process_pool_manager.ProcessPoolManager._instance = mock_pool
print("✅ Mock pool injected")

# Local application imports
# Now test that it works
from process_pool_manager import ProcessPoolManager


pool = ProcessPoolManager.get_instance()

# This should use the mock, not try to run real ws command
try:
    result = pool.execute_workspace_command("ws -sg")
    print("✅ Mock ws -sg executed successfully")
    print(f"   Result: {result[:100]}...")
except Exception as e:
    print(f"❌ Failed: {e}")
    sys.exit(1)

# Local application imports
# Now test with ShotModel
from shot_model import ShotModel


model = ShotModel(load_cache=False)

try:
    success, has_changes = model.refresh_shots()
    if success:
        print(f"✅ ShotModel refreshed with {len(model.shots)} mock shots")
        for shot in model.shots[:3]:
            print(f"   - {shot.full_name}")
    else:
        print("❌ ShotModel refresh failed")
except Exception as e:
    print(f"❌ ShotModel error: {e}")

print("=" * 50)
print("Mock injection test completed successfully!")
