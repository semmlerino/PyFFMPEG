#!/usr/bin/env python3
"""Test script to verify process pool manager works after fcntl fix."""

import logging
import sys
from pathlib import Path

# Add the shotbot directory to path
sys.path.insert(0, str(Path(__file__).parent))

from process_pool_manager import ProcessPoolManager  # noqa: E402

# Set up logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def test_process_pool():
    """Test basic process pool functionality."""
    print("Testing ProcessPoolManager after fcntl fix...")

    try:
        # Initialize the manager
        manager = ProcessPoolManager.get_instance()
        print("✓ ProcessPoolManager initialized successfully")

        # Test a simple command
        result = manager.execute_workspace_command("echo 'test'", timeout=5)
        print(f"✓ Command execution successful: {result.strip()}")

        # Test batch execution
        commands = ["echo 'one'", "echo 'two'", "echo 'three'"]
        results = manager.batch_execute(commands, cache_ttl=5)
        print(f"✓ Batch execution successful: {len(results)} commands")

        # Get metrics
        metrics = manager.get_metrics()
        print(
            f"✓ Metrics retrieved: {metrics.get('subprocess_calls', 0)} subprocess calls"
        )

        # Shutdown cleanly
        manager.shutdown()
        print("✓ Manager shutdown successful")

        print("\n✅ All tests passed! The fix works correctly.")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_process_pool()
    sys.exit(0 if success else 1)
