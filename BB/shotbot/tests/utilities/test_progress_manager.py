#!/usr/bin/env python3
"""Test script for the ProgressManager implementation.

This script demonstrates and validates the ProgressManager functionality
including context managers, nested operations, cancellation, and integration
with the notification system.
"""

import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

# Add the shotbot directory to Python path
shotbot_dir = Path(__file__).parent
sys.path.insert(0, str(shotbot_dir))

from notification_manager import NotificationManager
from progress_manager import ProgressManager, ProgressType


class ProgressTestWindow(QMainWindow):
    """Test window for demonstrating progress operations."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Progress Manager Test")
        self.resize(600, 400)

        # Set up UI
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Initialize notification and progress managers
        NotificationManager.initialize(self, self.status_bar)
        ProgressManager.initialize(self.status_bar)

        # Test buttons
        self.add_test_button("Test Basic Progress", self.test_basic_progress)
        self.add_test_button(
            "Test Indeterminate Progress", self.test_indeterminate_progress
        )
        self.add_test_button(
            "Test Cancellable Progress", self.test_cancellable_progress
        )
        self.add_test_button("Test Nested Progress", self.test_nested_progress)
        self.add_test_button("Test Modal Progress", self.test_modal_progress)
        self.add_test_button("Test Progress with Error", self.test_progress_error)
        self.add_test_button("Test Manual Progress", self.test_manual_progress)

        self._layout = layout

    def add_test_button(self, text: str, callback):
        """Add a test button to the layout."""
        button = QPushButton(text)
        button.clicked.connect(callback)
        self._layout.addWidget(button)

    def test_basic_progress(self):
        """Test basic determinate progress with context manager."""

        def run_operation():
            with ProgressManager.operation("Loading files") as progress:
                progress.set_total(10)
                for i in range(10):
                    time.sleep(0.1)  # Simulate work
                    progress.update(i + 1, f"Processing file {i + 1}")

        # Run in timer to avoid blocking UI
        QTimer.singleShot(100, run_operation)

    def test_indeterminate_progress(self):
        """Test indeterminate progress (spinner)."""

        def run_operation():
            with ProgressManager.operation("Analyzing data") as progress:
                progress.set_indeterminate()
                for i in range(5):
                    time.sleep(0.2)  # Simulate work
                    progress.update(0, f"Processing step {i + 1}")

        QTimer.singleShot(100, run_operation)

    def test_cancellable_progress(self):
        """Test cancellable progress operation."""

        def cancel_callback():
            print("Operation cancelled by user!")

        def run_operation():
            with ProgressManager.operation(
                "Long operation", cancelable=True, cancel_callback=cancel_callback
            ) as progress:
                progress.set_total(20)
                for i in range(20):
                    if progress.is_cancelled():
                        print("Operation was cancelled!")
                        break
                    time.sleep(0.1)
                    progress.update(i + 1, f"Step {i + 1} of 20")

        QTimer.singleShot(100, run_operation)

    def test_nested_progress(self):
        """Test nested progress operations."""

        def run_operation():
            with ProgressManager.operation("Main operation") as main:
                main.set_total(3)

                # First sub-operation
                with ProgressManager.operation("Sub-operation 1") as sub:
                    sub.set_total(5)
                    for i in range(5):
                        time.sleep(0.1)
                        sub.update(i + 1, f"Sub-step {i + 1}")

                main.update(1, "Completed sub-operation 1")

                # Second sub-operation
                with ProgressManager.operation("Sub-operation 2") as sub:
                    sub.set_indeterminate()
                    for i in range(3):
                        time.sleep(0.1)
                        sub.update(0, f"Processing item {i + 1}")

                main.update(2, "Completed sub-operation 2")

                # Final step
                time.sleep(0.2)
                main.update(3, "All operations completed")

        QTimer.singleShot(100, run_operation)

    def test_modal_progress(self):
        """Test modal progress dialog."""

        def run_operation():
            with ProgressManager.operation(
                "Modal operation",
                progress_type=ProgressType.MODAL_DIALOG,
                cancelable=True,
            ) as progress:
                progress.set_total(8)
                for i in range(8):
                    if progress.is_cancelled():
                        break
                    time.sleep(0.3)  # Longer delay to see modal
                    progress.update(i + 1, f"Modal step {i + 1}")

        QTimer.singleShot(100, run_operation)

    def test_progress_error(self):
        """Test progress operation with error."""

        def run_operation():
            try:
                with ProgressManager.operation("Operation that fails") as progress:
                    progress.set_total(5)
                    for i in range(3):
                        time.sleep(0.1)
                        progress.update(i + 1, f"Step {i + 1}")

                    # Simulate an error
                    raise RuntimeError("Something went wrong!")

            except Exception as e:
                print(f"Caught error: {e}")

        QTimer.singleShot(100, run_operation)

    def test_manual_progress(self):
        """Test manual progress management (non-context manager)."""

        def run_operation():
            # Start operation manually
            operation = ProgressManager.start_operation("Manual operation")

            try:
                operation.set_total(6)
                for i in range(6):
                    time.sleep(0.1)
                    operation.update(i + 1, f"Manual step {i + 1}")

                # Finish successfully
                ProgressManager.finish_operation(success=True)

            except Exception as e:
                ProgressManager.finish_operation(success=False, error_message=str(e))

        QTimer.singleShot(100, run_operation)


def main():
    """Run the progress manager test application."""
    app = QApplication(sys.argv)

    window = ProgressTestWindow()
    window.show()

    print("Progress Manager Test Application")
    print("================================")
    print("Click the buttons to test different progress scenarios.")
    print("Watch the status bar and dialogs for progress indicators.")
    print()
    print("Available tests:")
    print("- Basic Progress: Simple determinate progress")
    print("- Indeterminate Progress: Spinner-style progress")
    print("- Cancellable Progress: Progress that can be cancelled")
    print("- Nested Progress: Multiple levels of progress")
    print("- Modal Progress: Blocking dialog progress")
    print("- Progress with Error: Error handling")
    print("- Manual Progress: Non-context manager usage")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
