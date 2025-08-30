"""Accessibility manager for ShotBot application.

Provides centralized accessibility support including screen reader compatibility,
keyboard navigation, and tooltip management.
"""

from __future__ import annotations

from typing import Any, Protocol, cast, runtime_checkable

from PySide6.QtWidgets import QListView, QPushButton, QSlider, QTabWidget, QWidget


@runtime_checkable
class GridWidget(Protocol):
    """Protocol for grid widgets that may have accessibility features."""

    def setAccessibleName(self, name: str) -> None: ...
    def setAccessibleDescription(self, description: str) -> None: ...

    # attributes - checked with hasattr at runtime
    size_slider: QSlider | None
    list_view: QListView | None


class AccessibilityManager:
    """Manages accessibility features across the application."""

    @staticmethod
    def setup_main_window_accessibility(window: QWidget) -> None:
        """Set up accessibility for the main window.

        Args:
            window: The main application window
        """
        window.setAccessibleName("ShotBot VFX Launcher")
        window.setAccessibleDescription(
            "Browse and launch VFX applications for shots. Use Tab to navigate, Arrow keys to select shots, Enter to launch applications."
        )

    @staticmethod
    def setup_shot_grid_accessibility(
        grid_widget: QWidget, grid_type: str = "shots"
    ) -> None:
        """Set up accessibility for shot grid widgets.

        Args:
            grid_widget: The grid widget to configure
            grid_type: Type of grid ("shots", "3de", "previous")
        """
        descriptions = {
            "shots": "Grid of assigned shots with thumbnails. Navigate with arrow keys, press Enter to select.",
            "3de": "Grid of 3DE scene files. Navigate with arrow keys, double-click to open.",
            "previous": "Grid of previously completed shots. Browse your shot history.",
        }

        names = {
            "shots": "My Shots Grid",
            "3de": "3DE Scenes Grid",
            "previous": "Previous Shots Grid",
        }

        grid_widget.setAccessibleName(names.get(grid_type, "Shot Grid"))
        grid_widget.setAccessibleDescription(
            descriptions.get(grid_type, "Grid of shots")
        )

        # Set up for child widgets if they exist
        if hasattr(grid_widget, "size_slider"):
            # Cast to GridWidget protocol to access size_slider attribute safely
            grid = cast(GridWidget, grid_widget)
            if grid.size_slider is not None:
                AccessibilityManager.setup_slider_accessibility(
                    grid.size_slider,
                    "Thumbnail Size",
                    "Adjust thumbnail size from 100 to 400 pixels. Use arrow keys or Ctrl+Mouse Wheel.",
                )

        if hasattr(grid_widget, "list_view"):
            # Cast to GridWidget protocol to access list_view attribute safely
            grid = cast(GridWidget, grid_widget)
            if grid.list_view is not None:
                grid.list_view.setAccessibleName(f"{grid_type.title()} List")
                grid.list_view.setAccessibleDescription(
                    f"List of {grid_type} items. Use arrow keys to navigate, Enter to select."
                )

    @staticmethod
    def setup_button_accessibility(
        button: QPushButton, name: str, description: str, shortcut: str | None = None
    ) -> None:
        """Set up accessibility for a button.

        Args:
            button: The button to configure
            name: Accessible name for the button
            description: Accessible description
            shortcut: keyboard shortcut
        """
        button.setAccessibleName(name)

        full_description = description
        if shortcut:
            full_description += f" Keyboard shortcut: {shortcut}"
            button.setToolTip(f"{name} ({shortcut})")
        else:
            button.setToolTip(name)

        button.setAccessibleDescription(full_description)

    @staticmethod
    def setup_launcher_buttons_accessibility(
        app_buttons: dict[str, QPushButton],
    ) -> None:
        """Set up accessibility for application launcher buttons.

        Args:
            app_buttons: Dictionary of app name to button
        """
        shortcuts = {"3de": "3", "nuke": "N", "maya": "M", "rv": "R", "publish": "P"}

        for app_name, button in app_buttons.items():
            AccessibilityManager.setup_button_accessibility(
                button,
                f"Launch {app_name.upper()}",
                f"Launch {app_name.upper()} for the selected shot",
                shortcuts.get(app_name),
            )

    @staticmethod
    def setup_slider_accessibility(
        slider: QSlider, name: str, description: str
    ) -> None:
        """Set up accessibility for a slider.

        Args:
            slider: The slider to configure
            name: Accessible name
            description: Accessible description
        """
        slider.setAccessibleName(name)
        slider.setAccessibleDescription(description)
        slider.setToolTip(description)

    @staticmethod
    def setup_tab_widget_accessibility(tab_widget: QTabWidget) -> None:
        """Set up accessibility for tab widget.

        Args:
            tab_widget: The tab widget to configure
        """
        tab_widget.setAccessibleName("Shot View Tabs")
        tab_widget.setAccessibleDescription(
            "Switch between different shot views. Use Ctrl+Tab to cycle through tabs."
        )

        # Set up individual tabs
        tab_descriptions = [
            ("My Shots", "View shots assigned to you"),
            ("Other 3DE Scenes", "Browse 3DE scene files from other users"),
            ("Previous Shots", "View your previously completed shots"),
            ("Command History", "View history of launched commands"),
        ]

        for i, (name, description) in enumerate(tab_descriptions):
            if i < tab_widget.count():
                tab_widget.setTabToolTip(i, description)
                # Note: Tab text is already set, just adding tooltip

    @staticmethod
    def setup_comprehensive_tooltips(window: Any) -> None:
        """Add comprehensive tooltips to all UI elements.

        Args:
            window: Main window with UI elements
        """
        # File menu tooltips
        if hasattr(window, "refresh_action"):
            window.refresh_action.setToolTip(
                "Refresh shot list from workspace (Ctrl+R)"
            )

        if hasattr(window, "settings_action"):
            window.settings_action.setToolTip("Open application settings dialog")

        if hasattr(window, "exit_action"):
            window.exit_action.setToolTip("Exit ShotBot application")

        # View menu tooltips
        if hasattr(window, "increase_size_action"):
            window.increase_size_action.setToolTip("Increase thumbnail size (Ctrl++)")

        if hasattr(window, "decrease_size_action"):
            window.decrease_size_action.setToolTip("Decrease thumbnail size (Ctrl+-)")

        if hasattr(window, "reset_layout_action"):
            window.reset_layout_action.setToolTip(
                "Reset window layout to default configuration"
            )

        # Help menu tooltips
        if hasattr(window, "shortcuts_action"):
            window.shortcuts_action.setToolTip("Show keyboard shortcuts reference")

        if hasattr(window, "about_action"):
            window.about_action.setToolTip("About ShotBot application")

        # Status bar tooltip
        if hasattr(window, "status_bar"):
            window.status_bar.setToolTip("Application status and messages")

    @staticmethod
    def setup_keyboard_navigation(window: Any) -> None:
        """Set up proper tab order for keyboard navigation.

        Args:
            window: Main window to configure
        """
        # Define logical tab order
        if all(
            hasattr(window, attr) for attr in ["tab_widget", "shot_grid", "app_buttons"]
        ):
            # Start with tab widget
            window.setTabOrder(window.tab_widget, window.shot_grid.size_slider)

            # Then shot grid controls
            if hasattr(window.shot_grid, "list_view"):
                window.setTabOrder(
                    window.shot_grid.size_slider, window.shot_grid.list_view
                )

            # Then launcher buttons in order
            prev_widget = (
                window.shot_grid.list_view
                if hasattr(window.shot_grid, "list_view")
                else window.shot_grid
            )
            for app_name in ["3de", "nuke", "maya", "rv", "publish"]:
                if app_name in window.app_buttons:
                    window.setTabOrder(prev_widget, window.app_buttons[app_name])
                    prev_widget = window.app_buttons[app_name]

    @staticmethod
    def add_focus_indicators_stylesheet() -> str:
        """Return stylesheet for visible focus indicators.

        Returns:
            CSS stylesheet string for focus indicators
        """
        return """
        /* Focus indicators for keyboard navigation */
        QWidget:focus {
            outline: 2px solid #14ffec;
            outline-offset: 2px;
        }
        
        QPushButton:focus {
            border: 2px solid #14ffec;
            background-color: rgba(20, 255, 236, 0.1);
        }
        
        QListWidget::item:focus {
            border: 2px solid #14ffec;
            background-color: rgba(20, 255, 236, 0.1);
        }
        
        QTabBar::tab:focus {
            border: 2px solid #14ffec;
        }
        
        QSlider::handle:focus {
            border: 2px solid #14ffec;
            background-color: #14ffec;
        }
        """

    @staticmethod
    def announce_to_screen_reader(message: str) -> None:
        """Announce a message to screen readers.

        Args:
            message: Message to announce
        """
        # Qt doesn't have a direct screen reader announcement API,
        # but we can use QAccessible events in more complex scenarios
        # For now, this is a placeholder for future enhancement
        pass

    @staticmethod
    def setup_validation_feedback_accessibility(
        widget: QWidget, is_valid: bool, message: str
    ) -> None:
        """Set up accessible validation feedback.

        Args:
            widget: Widget being validated
            is_valid: Whether validation passed
            message: Validation message
        """
        if is_valid:
            widget.setAccessibleDescription(f"Valid: {message}")
            widget.setStyleSheet("border: 2px solid #4caf50;")  # Green
        else:
            widget.setAccessibleDescription(f"Error: {message}")
            widget.setStyleSheet("border: 2px solid #f44336;")  # Red

        # Also set tooltip for visual users
        widget.setToolTip(message)
