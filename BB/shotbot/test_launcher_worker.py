#!/usr/bin/env python3
"""Test the launcher worker thread implementation."""

import logging
import sys

from PySide6.QtCore import QCoreApplication, QTimer

from launcher_manager import (
    LauncherManager,
    LauncherTerminal,
)

# Set up logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_worker_execution():
    """Test worker thread execution of a launcher."""
    app = QCoreApplication(sys.argv)

    # Create launcher manager
    manager = LauncherManager()

    # Create a test launcher that runs a simple command
    test_launcher_id = manager.create_launcher(
        name="Test Worker Launcher",
        command="echo 'Hello from worker thread!' && sleep 2 && echo 'Worker finished!'",
        description="Test launcher for worker thread execution",
        category="test",
        terminal=LauncherTerminal(required=False),  # Non-terminal so it uses worker
    )

    if not test_launcher_id:
        logger.error("Failed to create test launcher")
        return

    logger.info(f"Created test launcher with ID: {test_launcher_id}")

    # Connect signals to see what happens
    def on_execution_started(launcher_id):
        logger.info(f"Execution started for launcher: {launcher_id}")

    def on_execution_finished(launcher_id, success):
        logger.info(
            f"Execution finished for launcher: {launcher_id}, success: {success}"
        )
        # Give it a moment for cleanup then quit
        QTimer.singleShot(1000, app.quit)

    manager.execution_started.connect(on_execution_started)
    manager.execution_finished.connect(on_execution_finished)

    # Execute the launcher using worker thread
    logger.info("Executing launcher with worker thread...")
    success = manager.execute_launcher(test_launcher_id, use_worker=True)

    if success:
        logger.info("Launcher execution started successfully")
    else:
        logger.error("Failed to start launcher execution")
        app.quit()
        return

    # Run the event loop
    app.exec()

    # Cleanup
    logger.info(f"Active processes/workers: {manager.get_active_process_count()}")
    manager.delete_launcher(test_launcher_id)
    manager.shutdown()
    logger.info("Test completed")


def test_terminal_vs_worker():
    """Test that terminal commands don't use worker threads."""
    app = QCoreApplication(sys.argv)

    # Create launcher manager
    manager = LauncherManager()

    # Create a terminal launcher
    terminal_launcher_id = manager.create_launcher(
        name="Terminal Test Launcher",
        command="echo 'This should run in subprocess, not worker'",
        description="Test launcher requiring terminal",
        category="test",
        terminal=LauncherTerminal(required=True, persist=True),  # Terminal required
    )

    if not terminal_launcher_id:
        logger.error("Failed to create terminal launcher")
        return

    logger.info(f"Created terminal launcher with ID: {terminal_launcher_id}")

    # Execute the launcher - should use subprocess, not worker
    logger.info("Executing terminal launcher (should use subprocess)...")
    success = manager.execute_launcher(
        terminal_launcher_id, use_worker=True
    )  # Even with use_worker=True

    if success:
        logger.info("Terminal launcher execution started successfully")
    else:
        logger.error("Failed to start terminal launcher execution")

    # Quick cleanup
    QTimer.singleShot(2000, app.quit)
    app.exec()

    # Cleanup
    manager.delete_launcher(terminal_launcher_id)
    manager.shutdown()
    logger.info("Terminal test completed")


if __name__ == "__main__":
    logger.info("Testing launcher worker thread implementation...")

    # Test 1: Worker thread execution
    logger.info("\n=== Test 1: Worker Thread Execution ===")
    test_worker_execution()

    # Test 2: Terminal vs Worker
    logger.info("\n=== Test 2: Terminal vs Worker ===")
    test_terminal_vs_worker()

    logger.info("\nAll tests completed!")
