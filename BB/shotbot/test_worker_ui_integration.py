#!/usr/bin/env python3
"""Test worker thread integration with the UI to ensure non-blocking behavior."""

import logging
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from launcher_manager import LauncherManager, LauncherTerminal

# Set up logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TestWindow(QMainWindow):
    """Test window to demonstrate non-blocking launcher execution."""

    def __init__(self):
        super().__init__()
        self.launcher_manager = LauncherManager()
        self.test_launcher_id = None
        self.counter = 0
        self._setup_ui()
        self._create_test_launcher()

        # Timer to update UI counter (proves UI isn't blocked)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_counter)
        self.update_timer.start(100)  # Update every 100ms

    def _setup_ui(self):
        """Set up the test UI."""
        self.setWindowTitle("Worker Thread Test - UI Should Not Block")
        self.resize(600, 400)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layout
        layout = QVBoxLayout(central_widget)

        # Counter label (updates continuously to show UI isn't blocked)
        self.counter_label = QLabel("Counter: 0")
        self.counter_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: green;"
        )
        layout.addWidget(self.counter_label)

        # Status label
        self.status_label = QLabel("Ready to test worker threads")
        layout.addWidget(self.status_label)

        # Test button
        self.test_button = QPushButton("Execute Long-Running Command (Worker Thread)")
        self.test_button.clicked.connect(self._test_worker)
        layout.addWidget(self.test_button)

        # Test blocking button (for comparison)
        self.blocking_button = QPushButton("Execute Blocking Command (Direct)")
        self.blocking_button.clicked.connect(self._test_blocking)
        layout.addWidget(self.blocking_button)

        # Output text
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        layout.addWidget(self.output_text)

        # Connect launcher signals
        self.launcher_manager.execution_started.connect(self._on_execution_started)
        self.launcher_manager.execution_finished.connect(self._on_execution_finished)

    def _create_test_launcher(self):
        """Create a test launcher that runs for several seconds."""
        self.test_launcher_id = self.launcher_manager.create_launcher(
            name="Long Running Test",
            command="for i in {1..5}; do echo 'Working... step '$i; sleep 1; done; echo 'Done!'",
            description="Simulates a long-running command",
            category="test",
            terminal=LauncherTerminal(required=False),  # Non-terminal to use worker
        )

        if self.test_launcher_id:
            self.output_text.append("✓ Test launcher created successfully")
        else:
            self.output_text.append("✗ Failed to create test launcher")
            self.test_button.setEnabled(False)

    def _update_counter(self):
        """Update counter to show UI is responsive."""
        self.counter += 1
        self.counter_label.setText(f"Counter: {self.counter}")

        # Change color to make it more visible
        if self.counter % 10 == 0:
            color = "blue" if (self.counter // 10) % 2 == 0 else "green"
            self.counter_label.setStyleSheet(
                f"font-size: 20px; font-weight: bold; color: {color};"
            )

    def _test_worker(self):
        """Test worker thread execution."""
        if not self.test_launcher_id:
            self.output_text.append("No test launcher available")
            return

        self.output_text.append("\n--- Testing Worker Thread Execution ---")
        self.output_text.append("Executing long-running command...")
        self.output_text.append("UI should remain responsive (counter keeps updating)")

        # Execute using worker thread
        success = self.launcher_manager.execute_launcher(
            self.test_launcher_id, use_worker=True
        )

        if success:
            self.status_label.setText("Worker thread started - UI remains responsive!")
            self.test_button.setEnabled(False)
        else:
            self.output_text.append("Failed to start worker thread")

    def _test_blocking(self):
        """Test blocking execution for comparison."""
        self.output_text.append("\n--- Testing Blocking Execution ---")
        self.output_text.append("This will block the UI for 3 seconds...")
        self.output_text.append("Counter will freeze!")

        # Force UI update before blocking
        QApplication.processEvents()

        # Simulate blocking operation
        time.sleep(3)

        self.output_text.append("Blocking operation complete - UI was frozen")
        self.status_label.setText("Blocking test complete")

    def _on_execution_started(self, launcher_id):
        """Handle execution started signal."""
        self.output_text.append(f"→ Execution started: {launcher_id}")

    def _on_execution_finished(self, launcher_id, success):
        """Handle execution finished signal."""
        status = "successfully" if success else "with error"
        self.output_text.append(f"← Execution finished {status}: {launcher_id}")
        self.status_label.setText(f"Worker thread completed {status}")
        self.test_button.setEnabled(True)

    def closeEvent(self, event):
        """Clean up on close."""
        self.update_timer.stop()

        # Delete test launcher
        if self.test_launcher_id:
            self.launcher_manager.delete_launcher(self.test_launcher_id)

        # Shutdown launcher manager
        self.launcher_manager.shutdown()

        event.accept()


def main():
    """Run the test application."""
    app = QApplication(sys.argv)

    window = TestWindow()
    window.show()

    logger.info("Test window opened - try both buttons to see the difference")
    logger.info(
        "The counter should keep updating with worker thread but freeze with blocking call"
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
