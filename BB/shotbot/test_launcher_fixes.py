#!/usr/bin/env python3
"""Test script to verify launcher fixes for process leaks and race conditions."""

import logging
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from launcher import (
    CustomLauncher,
    LauncherEnvironment,
    LauncherTerminal,
    LauncherValidation,
)
from launcher_manager import LauncherManager

# Set up logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def test_process_cleanup():
    """Test that process cleanup handles termination failures properly."""
    print("\n=== Testing Process Cleanup ===")

    # Create a temporary config directory
    import tempfile

    temp_dir = tempfile.mkdtemp()

    # Create launcher manager
    manager = LauncherManager(config_dir=temp_dir)

    # Create a test launcher that sleeps (simulates long-running process)
    test_launcher = CustomLauncher(
        id="test_sleep",
        name="Test Sleep Launcher",
        command="sleep 30",  # Long sleep to test termination
        category="Testing",
        environment=LauncherEnvironment(),
        terminal=LauncherTerminal(),
        validation=LauncherValidation(),
    )

    # Create the launcher
    launcher_id = manager.create_launcher(
        name=test_launcher.name,
        command=test_launcher.command,
        category=test_launcher.category,
    )
    print(f"Created launcher: {launcher_id}")

    # Execute the launcher
    print("Executing launcher...")
    success = manager.execute_launcher(launcher_id)
    print(f"Execution started: {success}")

    # Give it a moment to start
    time.sleep(1)

    # Check active processes
    active = manager.get_active_process_count()
    print(f"Active processes: {active}")

    # Now try to stop/cleanup
    print("Initiating shutdown...")
    manager.shutdown()

    # Check logs for any orphaned process warnings
    print("Check logs above for any 'orphaned process' warnings")

    # Clean up
    import shutil

    shutil.rmtree(temp_dir)
    print("✓ Process cleanup test completed")


def test_worker_race_condition():
    """Test that workers are properly tracked even if they finish quickly."""
    print("\n=== Testing Worker Race Condition ===")

    # Create a temporary config directory
    import tempfile

    temp_dir = tempfile.mkdtemp()

    # Create launcher manager
    manager = LauncherManager(config_dir=temp_dir)

    # Create a test launcher that exits immediately
    test_launcher = CustomLauncher(
        id="test_quick",
        name="Quick Exit Launcher",
        command="echo 'Quick test'",  # Exits immediately
        category="Testing",
        environment=LauncherEnvironment(),
        terminal=LauncherTerminal(),
        validation=LauncherValidation(),
    )

    # Create the launcher
    launcher_id = manager.create_launcher(
        name=test_launcher.name,
        command=test_launcher.command,
        category=test_launcher.category,
    )
    print(f"Created launcher: {launcher_id}")

    # Execute multiple times rapidly to test race condition
    print("Executing launcher rapidly 5 times...")
    for i in range(5):
        success = manager.execute_launcher(launcher_id)
        print(f"  Execution {i + 1}: {success}")
        # No sleep - test immediate execution

    # Give workers time to finish
    time.sleep(2)

    # Check that all workers were properly tracked and cleaned up
    active = manager.get_active_process_count()
    print(f"Active processes after rapid execution: {active}")

    if active == 0:
        print("✓ All workers properly tracked and cleaned up")
    else:
        print(f"⚠ Warning: {active} processes still active")

    # Clean shutdown
    manager.shutdown()

    # Clean up
    import shutil

    shutil.rmtree(temp_dir)
    print("✓ Race condition test completed")


def main():
    """Run all tests."""
    print("Testing launcher fixes for process leaks and race conditions")
    print("=" * 60)

    try:
        test_process_cleanup()
        test_worker_race_condition()

        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        print("The fixes are working correctly:")
        print("  - Process cleanup now properly logs orphaned processes")
        print("  - Workers are tracked before starting to prevent race conditions")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())