#!/usr/bin/env python3
"""Demo script for the ShotBot notification system.

This script demonstrates all the different types of notifications available
in the ShotBot application. Run this standalone to see the notification
system in action.

Usage:
    python notification_demo.py
"""

import sys
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

# Add the current directory to the path so we can import the notification system
sys.path.insert(0, str(Path(__file__).parent))

from notification_manager import NotificationManager, NotificationType


class NotificationDemoWindow(QMainWindow):
    """Demo window to showcase the notification system."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ShotBot Notification System Demo")
        self.resize(800, 600)

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Initialize notification manager
        NotificationManager.initialize(self, self.status_bar)

        # Create central widget with buttons
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # Add demo buttons
        self.add_button(layout, "Show Error Dialog", self.show_error)
        self.add_button(layout, "Show Warning Dialog", self.show_warning)
        self.add_button(layout, "Show Info Message", self.show_info)
        self.add_button(layout, "Show Success Message", self.show_success)
        self.add_button(layout, "Show Progress Dialog", self.show_progress)

        layout.addWidget(self.create_separator())

        self.add_button(layout, "Toast: Error", self.show_toast_error)
        self.add_button(layout, "Toast: Warning", self.show_toast_warning)
        self.add_button(layout, "Toast: Info", self.show_toast_info)
        self.add_button(layout, "Toast: Success", self.show_toast_success)

        layout.addWidget(self.create_separator())

        self.add_button(layout, "Multiple Toasts Demo", self.show_multiple_toasts)
        self.add_button(layout, "Clear All Toasts", self.clear_toasts)

        layout.addStretch()

        # Show welcome message
        NotificationManager.info("Notification demo loaded - try the buttons above!")

    def add_button(self, layout, text: str, callback):
        """Add a demo button to the layout."""
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def create_separator(self) -> QWidget:
        """Create a visual separator."""
        separator = QWidget()
        separator.setFixedHeight(20)
        separator.setStyleSheet("border-bottom: 1px solid #ccc; margin: 10px 0;")
        return separator

    def show_error(self):
        """Demo error notification."""
        NotificationManager.error(
            "Application Launch Failed",
            "The requested application could not be found in your system PATH.",
            "Make sure Nuke is installed and accessible from the command line.",
        )

    def show_warning(self):
        """Demo warning notification."""
        NotificationManager.warning(
            "No Shot Selected",
            "Please select a shot before launching applications.",
            "Use the shot grid to select a valid shot context.",
        )

    def show_info(self):
        """Demo info notification."""
        NotificationManager.info("Shot cache refreshed - 15 shots loaded", 4000)

    def show_success(self):
        """Demo success notification."""
        NotificationManager.success("3DE launched successfully!", 4000)

    def show_progress(self):
        """Demo progress dialog."""
        progress = NotificationManager.progress(
            "Scanning 3DE Scenes",
            "Searching for .3de files in user directories...",
            cancelable=True,
        )

        # Simulate progress updates
        def update_progress():
            import random

            value = random.randint(10, 90)
            progress.setValue(value)
            if value >= 90:
                NotificationManager.close_progress()
                NotificationManager.toast("Scan completed!", NotificationType.SUCCESS)

        timer = QTimer()
        timer.timeout.connect(update_progress)
        timer.start(500)

        # Stop timer when progress is canceled or finished
        progress.canceled.connect(timer.stop)
        progress.finished.connect(timer.stop)

    def show_toast_error(self):
        """Demo error toast."""
        NotificationManager.toast("Failed to load thumbnail", NotificationType.ERROR)

    def show_toast_warning(self):
        """Demo warning toast."""
        NotificationManager.toast(
            "Raw plate not found for this shot", NotificationType.WARNING
        )

    def show_toast_info(self):
        """Demo info toast."""
        NotificationManager.toast("Cache updated in background", NotificationType.INFO)

    def show_toast_success(self):
        """Demo success toast."""
        NotificationManager.toast(
            "Custom launcher created successfully", NotificationType.SUCCESS
        )

    def show_multiple_toasts(self):
        """Demo multiple stacked toasts."""
        messages = [
            ("Processing shot 001...", NotificationType.INFO),
            ("Processing shot 002...", NotificationType.INFO),
            ("Processing shot 003...", NotificationType.SUCCESS),
            ("Found issue with shot 004", NotificationType.WARNING),
            ("All shots processed!", NotificationType.SUCCESS),
        ]

        def show_next_toast(index=0):
            if index < len(messages):
                message, ntype = messages[index]
                NotificationManager.toast(message, ntype, duration=2000)
                QTimer.singleShot(300, lambda: show_next_toast(index + 1))

        show_next_toast()

    def clear_toasts(self):
        """Clear all active toasts."""
        NotificationManager.clear_all_toasts()
        NotificationManager.info("All toasts cleared")


def main():
    """Run the notification demo."""
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow {
            background-color: #2b2b2b;
            color: white;
        }
        QPushButton {
            background-color: #404040;
            color: white;
            border: 1px solid #555;
            padding: 8px 16px;
            margin: 2px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #505050;
        }
        QPushButton:pressed {
            background-color: #606060;
        }
        QStatusBar {
            background-color: #353535;
            color: white;
            border-top: 1px solid #555;
        }
    """)

    window = NotificationDemoWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
