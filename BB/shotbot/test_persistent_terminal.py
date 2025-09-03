#!/usr/bin/env python3
"""Test script for the persistent terminal implementation."""

import logging
import sys
import time

from PySide6.QtCore import QCoreApplication

from config import Config
from persistent_terminal_manager import PersistentTerminalManager

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_persistent_terminal() -> int:
    """Test the persistent terminal functionality."""
    QCoreApplication(sys.argv)  # Need Qt app for signals/slots

    # Create terminal manager
    manager = PersistentTerminalManager()

    # Test commands
    test_commands = [
        "echo '=== Persistent Terminal Test Started ==='",
        "pwd",
        "echo 'Testing command 1'",
        "ls -la | head -5",
        "echo 'Testing command 2'",
        "echo 'All tests completed!'",
    ]

    # Send commands with small delays
    for cmd in test_commands:
        logger.info(f"Sending command: {cmd}")
        success = manager.send_command(cmd)
        if not success:
            logger.error(f"Failed to send command: {cmd}")
        time.sleep(1)  # Give time to see output

    # Test clear terminal
    time.sleep(2)
    logger.info("Clearing terminal...")
    manager.clear_terminal()

    time.sleep(1)
    manager.send_command("echo 'Terminal cleared and still working!'")

    # Test with GUI app (if available)
    if Config.APPS.get("nuke"):
        logger.info("Testing GUI app launch (will run in background)...")
        manager.send_command("nuke &")
        time.sleep(2)

    # Keep terminal open for inspection
    logger.info("Test complete. Terminal will remain open for 5 seconds...")
    time.sleep(5)

    # Cleanup
    if Config.KEEP_TERMINAL_ON_EXIT:
        logger.info("Keeping terminal open (KEEP_TERMINAL_ON_EXIT=True)")
        manager.cleanup_fifo_only()
    else:
        logger.info("Closing terminal...")
        manager.cleanup()

    return 0


if __name__ == "__main__":
    sys.exit(test_persistent_terminal())
