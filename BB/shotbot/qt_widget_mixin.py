"""Qt Widget Mixin for common widget patterns.

This module provides mixins for common Qt widget functionality,
reducing code duplication across widget classes.

Part of Phase 2 refactoring to eliminate duplicate Qt patterns.
"""

from __future__ import annotations

# Standard library imports
from typing import TYPE_CHECKING, cast

# Third-party imports
from PySide6.QtCore import QPoint, QSettings, QSize, Qt, QTimer
from PySide6.QtWidgets import QMenu, QMessageBox, QWidget

# Local application imports
from logging_mixin import LoggingMixin

if TYPE_CHECKING:
    # Standard library imports
    from collections.abc import Callable

    # Third-party imports
    from PySide6.QtGui import (
        QCloseEvent,
        QDragEnterEvent,
        QDropEvent,
        QIcon,
        QKeyEvent,
    )


class QtWidgetMixin(LoggingMixin):
    """Mixin for common Qt widget functionality.

    Provides:
    - Window geometry save/restore
    - Common event handler patterns
    - Context menu creation helpers
    - Standard keyboard shortcuts
    - Window state management
    - Safe timer patterns
    - Common dialog helpers
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize QtWidgetMixin and continue MRO chain.

        This ensures proper multiple inheritance with Qt classes.
        """
        super().__init__(*args, **kwargs)

    def setup_window_geometry(
        self,
        settings_key: str,
        default_size: QSize | None = None,
        default_pos: QPoint | None = None,
    ) -> None:
        """Setup window geometry with save/restore.

        Args:
            settings_key: Settings key for storing geometry
            default_size: Default window size if no settings
            default_pos: Default window position if no settings
        """
        self._geometry_key = settings_key
        self._default_size = default_size or QSize(1200, 800)
        self._default_pos = default_pos

        # Restore geometry from settings
        settings = QSettings()
        if settings.contains(f"{self._geometry_key}/geometry"):
            geometry_bytes = settings.value(f"{self._geometry_key}/geometry")  # type: ignore[misc]  # QSettings.value() returns Any
            if hasattr(self, "restoreGeometry"):
                self.restoreGeometry(geometry_bytes)  # type: ignore[attr-defined]
        else:
            if hasattr(self, "resize"):
                self.resize(self._default_size)  # type: ignore[attr-defined]
            if self._default_pos and hasattr(self, "move"):
                self.move(self._default_pos)  # type: ignore[attr-defined]

    def save_window_geometry(self) -> None:
        """Save window geometry to settings."""
        if hasattr(self, "_geometry_key") and hasattr(self, "saveGeometry"):
            settings = QSettings()
            settings.setValue(f"{self._geometry_key}/geometry", self.saveGeometry())  # type: ignore[attr-defined]
            self.logger.debug(f"Saved window geometry for {self._geometry_key}")

    def setup_auto_save_timer(self, interval: int = 60000) -> None:
        """Setup timer for auto-saving settings.

        Args:
            interval: Save interval in milliseconds (default 60 seconds)
        """
        if not hasattr(self, "_auto_save_timer"):
            self._auto_save_timer = QTimer()
            self._auto_save_timer.timeout.connect(self._on_auto_save)
            self._auto_save_timer.start(interval)
            self.logger.debug(f"Auto-save timer started with {interval}ms interval")

    def _on_auto_save(self) -> None:
        """Auto-save callback."""
        self.save_window_geometry()
        # Subclasses can override to save additional state
        if hasattr(self, "save_state"):
            self.save_state()  # type: ignore[attr-defined]

    def create_context_menu(
        self,
        actions: list[tuple[str, Callable[[], None], str | None]],
        parent: QWidget | None = None,
    ) -> QMenu:
        """Create a context menu with standard actions.

        Args:
            actions: List of (text, callback, icon_name) tuples
            parent: Parent widget for the menu

        Returns:
            Configured QMenu
        """
        menu = QMenu(parent)

        for action_text, callback, icon_name in actions:
            if action_text == "-":
                menu.addSeparator()
            else:
                action = menu.addAction(action_text)
                action.triggered.connect(callback)

                if icon_name and hasattr(self, "style"):
                    # Use standard icons if available
                    # Third-party imports
                    from PySide6.QtWidgets import QStyle

                    icon_map: dict[str, QStyle.StandardPixmap] = {
                        "copy": QStyle.StandardPixmap.SP_FileDialogDetailedView,
                        "paste": QStyle.StandardPixmap.SP_DialogApplyButton,
                        "delete": QStyle.StandardPixmap.SP_TrashIcon,
                        "refresh": QStyle.StandardPixmap.SP_BrowserReload,
                        "open": QStyle.StandardPixmap.SP_DirOpenIcon,
                    }
                    if icon_name in icon_map:
                        # Cast needed due to mixin pattern - self.style() return type not inferred
                        icon: QIcon = cast("QIcon", self.style().standardIcon(icon_map[icon_name]))  # type: ignore[attr-defined]
                        action.setIcon(icon)

        return menu

    def setup_standard_shortcuts(self) -> None:
        """Setup standard keyboard shortcuts."""
        if not hasattr(self, "addAction"):
            return

        shortcuts = self._get_standard_shortcuts()
        for key_sequence, callback in shortcuts.items():
            # Third-party imports
            from PySide6.QtGui import QAction, QKeySequence

            action = QAction(self)  # type: ignore[arg-type]
            action.setShortcut(QKeySequence(key_sequence))
            action.triggered.connect(callback)
            self.addAction(action)  # type: ignore[attr-defined]

    def _get_standard_shortcuts(self) -> dict[str, Callable[[], None]]:
        """Get standard keyboard shortcuts.

        Subclasses can override to provide custom shortcuts.
        """
        shortcuts: dict[str, Callable[[], None]] = {}

        # Add standard shortcuts if methods exist
        if hasattr(self, "refresh"):
            shortcuts["F5"] = self.refresh  # type: ignore[attr-defined]
        if hasattr(self, "close"):
            shortcuts["Ctrl+W"] = self.close  # type: ignore[attr-defined]
        if hasattr(self, "copy"):
            shortcuts["Ctrl+C"] = self.copy  # type: ignore[attr-defined]
        if hasattr(self, "paste"):
            shortcuts["Ctrl+V"] = self.paste  # type: ignore[attr-defined]

        return shortcuts

    def safe_close(self) -> bool:
        """Safe close with confirmation if needed.

        Returns:
            True if close should proceed
        """
        # Check if there are unsaved changes
        if hasattr(self, "has_unsaved_changes") and self.has_unsaved_changes():  # type: ignore[attr-defined]
            # QMessageBox.question returns int (StandardButton enum value)
            # Cast needed due to incomplete PySide6 type stubs
            reply_int: int = cast(
                "int",
                QMessageBox.question(
                    self,  # type: ignore[arg-type][arg-type]
                    "Unsaved Changes",
                    "You have unsaved changes. Do you want to save before closing?",
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Save,
                ),
            )
            reply = QMessageBox.StandardButton(reply_int)

            if reply == QMessageBox.StandardButton.Save:
                if hasattr(self, "save"):
                    self.save()  # type: ignore[attr-defined]
                return True
            elif reply == QMessageBox.StandardButton.Discard:
                return True
            else:
                return False

        return True

    def cleanup_timers(self) -> None:
        """Cleanup all timers safely."""
        timer_attrs = [
            "_auto_save_timer",
            "_refresh_timer",
            "_update_timer",
            "_progress_timer",
        ]

        for attr in timer_attrs:
            if hasattr(self, attr):
                timer: QTimer | None = getattr(self, attr, None)
                if timer is not None and hasattr(timer, "stop"):
                    timer.stop()
                    self.logger.debug(f"Stopped timer: {attr}")

    def show_error(self, title: str, message: str, details: str | None = None) -> None:
        """Show error message dialog.

        Args:
            title: Dialog title
            message: Main error message
            details: Optional detailed error information
        """
        msg = QMessageBox(self)  # type: ignore[arg-type]
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(title)
        msg.setText(message)

        if details:
            msg.setDetailedText(details)

        msg.exec()
        self.logger.error(f"{title}: {message}")

    def show_info(self, title: str, message: str) -> None:
        """Show information message dialog.

        Args:
            title: Dialog title
            message: Information message
        """
        QMessageBox.information(self, title, message)  # type: ignore[arg-type]
        self.logger.info(f"{title}: {message}")

    def confirm_action(self, title: str, message: str) -> bool:
        """Show confirmation dialog.

        Args:
            title: Dialog title
            message: Confirmation message

        Returns:
            True if user confirmed
        """
        # QMessageBox.question returns int (StandardButton enum value)
        # Cast needed due to incomplete PySide6 type stubs
        reply_int: int = cast(
            "int",
            QMessageBox.question(
                self,  # type: ignore[arg-type]
                title,
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ),
        )
        reply = QMessageBox.StandardButton(reply_int)

        confirmed: bool = reply == QMessageBox.StandardButton.Yes
        self.logger.debug(f"Confirmation '{title}': {confirmed}")
        return confirmed

    # Common event handlers that can be overridden

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle close event with cleanup."""
        if self.safe_close():
            self.save_window_geometry()
            self.cleanup_timers()
            event.accept()
            self.logger.debug("Window closed successfully")
            # Call parent implementation to maintain MRO chain
            if hasattr(super(), "closeEvent"):
                super().closeEvent(event)  # type: ignore[misc]
        else:
            event.ignore()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press events with standard shortcuts."""
        # Handle Escape key
        if event.key() == Qt.Key.Key_Escape:
            if hasattr(self, "cancel") and callable(getattr(self, "cancel", None)):
                getattr(self, "cancel")()
            elif hasattr(self, "close"):
                self.close()  # type: ignore[attr-defined]

        # Let parent handle other keys
        if hasattr(super(), "keyPressEvent"):
            super().keyPressEvent(event)  # type: ignore[misc]


class QtDragDropMixin:
    """Mixin for drag and drop functionality."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize QtDragDropMixin and continue MRO chain."""
        super().__init__(*args, **kwargs)

    def setup_drag_drop(self, mime_types: list[str] | None = None) -> None:
        """Setup drag and drop support.

        Args:
            mime_types: List of accepted MIME types
        """
        if hasattr(self, "setAcceptDrops"):
            self.setAcceptDrops(True)  # type: ignore[attr-defined]

        self._accepted_mime_types = mime_types or [
            "text/plain",
            "text/uri-list",
            'application/x-qt-windows-mime;value="FileName"',
        ]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter event."""
        if event.mimeData().hasUrls() or any(
            event.mimeData().hasFormat(mime_type)
            for mime_type in self._accepted_mime_types
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop event."""
        mime_data = event.mimeData()

        if mime_data.hasUrls():
            urls = mime_data.urls()
            file_paths: list[str] = [url.toLocalFile() for url in urls]

            if hasattr(self, "handle_dropped_files"):
                self.handle_dropped_files(file_paths)  # type: ignore[attr-defined]
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()


class QtProgressMixin:
    """Mixin for progress indication in widgets."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize QtProgressMixin and continue MRO chain."""
        super().__init__(*args, **kwargs)

    def setup_progress_indicator(self, parent: QWidget | None = None) -> None:
        """Setup progress indication UI elements."""
        # Third-party imports
        from PySide6.QtWidgets import QProgressBar

        self._progress_bar = QProgressBar(parent or self)  # type: ignore[arg-type]
        self._progress_bar.setVisible(False)
        self._progress_text = ""

    def show_progress(self, value: int = 0, maximum: int = 100, text: str = "") -> None:
        """Show progress indicator.

        Args:
            value: Current progress value
            maximum: Maximum progress value
            text: Progress text
        """
        if hasattr(self, "_progress_bar"):
            self._progress_bar.setMaximum(maximum)
            self._progress_bar.setValue(value)
            self._progress_bar.setVisible(True)

            if text:
                self._progress_text = text
                if hasattr(self._progress_bar, "setFormat"):
                    self._progress_bar.setFormat(f"{text} %p%")

    def hide_progress(self) -> None:
        """Hide progress indicator."""
        if hasattr(self, "_progress_bar"):
            self._progress_bar.setVisible(False)
            self._progress_text = ""

    def set_indeterminate_progress(self, text: str = "Processing...") -> None:
        """Show indeterminate progress."""
        if hasattr(self, "_progress_bar"):
            self._progress_bar.setMaximum(0)  # Indeterminate
            self._progress_bar.setVisible(True)
            self._progress_text = text
