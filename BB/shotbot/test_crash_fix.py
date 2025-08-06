#!/usr/bin/env python3
"""Test script to verify the crash fix for relaunching apps."""

import logging
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QCoreApplication

from launcher_manager import LauncherManager
from shot_model import Shot

# Set up logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_app_relaunch():
    """Test launching, closing, and relaunching apps (all treated as GUI)."""
    logger.info("=" * 60)
    logger.info("Testing App Relaunch Fix (All Apps Treated as GUI)")
    logger.info("=" * 60)

    # Create Qt application
    QCoreApplication(sys.argv)

    # Create launcher manager
    manager = LauncherManager()

    # Create a test shot
    test_shot = Shot(
        show="TEST",
        sequence="001",
        shot="0010",
        workspace_path="/shows/TEST/shots/001/0010",
    )

    # Test 1: Create and launch a Nuke launcher
    logger.info("\n--- Test 1: Nuke Application ---")
    nuke_launcher_id = manager.create_launcher(
        name="Test Nuke Launcher",
        command="nuke",
        description="Test launcher for Nuke GUI app",
        category="test",
    )

    if nuke_launcher_id:
        logger.info(f"Created Nuke launcher with ID: {nuke_launcher_id}")

        # Launch Nuke
        logger.info("Launching Nuke...")
        success = manager.execute_in_shot_context(nuke_launcher_id, test_shot)

        if success:
            logger.info("✅ Nuke launched successfully")
            logger.info("Please close Nuke and wait...")
            time.sleep(5)  # Give user time to close the app

            # Relaunch Nuke
            logger.info("Relaunching Nuke...")
            success = manager.execute_in_shot_context(nuke_launcher_id, test_shot)

            if success:
                logger.info("✅ Nuke relaunched successfully - FIX WORKING!")
            else:
                logger.error("❌ Failed to relaunch Nuke")
        else:
            logger.error("❌ Failed to launch Nuke initially")

    # Test 2: Create and launch a Python script (also treated as GUI)
    logger.info("\n--- Test 2: Python Script ---")
    script_launcher_id = manager.create_launcher(
        name="Test Python Script",
        command="python -c 'print(\"Hello from Python\"); import time; time.sleep(2)'",
        description="Test launcher for CLI script",
        category="test",
    )

    if script_launcher_id:
        logger.info(f"Created script launcher with ID: {script_launcher_id}")

        # Launch script
        logger.info("Launching Python script...")
        success = manager.execute_launcher(script_launcher_id)

        if success:
            logger.info("✅ Script launched successfully")
            time.sleep(3)  # Wait for script to complete

            # Relaunch script
            logger.info("Relaunching Python script...")
            success = manager.execute_launcher(script_launcher_id)

            if success:
                logger.info("✅ Script relaunched successfully")
            else:
                logger.error("❌ Failed to relaunch script")
        else:
            logger.error("❌ Failed to launch script initially")

    # Test 3: Check active processes
    logger.info("\n--- Test 3: Process Management ---")
    active_count = manager.get_active_process_count()
    logger.info(f"Active processes: {active_count}")

    process_info = manager.get_active_process_info()
    for info in process_info:
        logger.info(f"  - {info['launcher_name']} (PID: {info['pid']})")

    # Cleanup
    logger.info("\n--- Cleanup ---")
    manager.delete_launcher(nuke_launcher_id)
    manager.delete_launcher(script_launcher_id)
    manager.shutdown()

    logger.info("\n" + "=" * 60)
    logger.info("Test completed!")
    logger.info("=" * 60)

    # Check if the crash issue is fixed
    logger.info("\n🎯 Summary:")
    logger.info("If you were able to:")
    logger.info("  1. Launch Nuke")
    logger.info("  2. Close Nuke")
    logger.info("  3. Relaunch Nuke without crashes")
    logger.info("Then the fix is working correctly! ✅")


if __name__ == "__main__":
    test_app_relaunch()
