#!/usr/bin/env python3
"""
File List Widget Module for PyMPEG
A custom QListWidget with drag & drop support for TS files
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar, cast, override

from PySide6.QtCore import (
    QFileInfo,
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor, QCursor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QWidget,
)

from pympeg.domain.status import FileStatus
from pympeg.file_queue import FileQueueModel, compute_display
from pympeg.metadata.probe import MetadataProbe
from pympeg.sizing.estimator import SizeEstimator

if TYPE_CHECKING:
    from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QMouseEvent

    from pympeg.metadata.probe import VideoMetadata


class MetadataSignals(QObject):
    """Signals for metadata loading worker"""

    metadata_loaded: ClassVar[Signal] = Signal(str, object)  # file_path, metadata_dict


class MetadataWorker(QRunnable):
    """Worker thread for loading video metadata without blocking UI"""

    def __init__(self, file_path: str, signals: MetadataSignals):
        super().__init__()
        self.file_path: str = file_path
        self.signals: MetadataSignals = signals

    @override
    def run(self):
        """Extract metadata and emit signal"""
        metadata = MetadataProbe.extract_video_metadata(self.file_path)
        self.signals.metadata_loaded.emit(self.file_path, metadata)


class FileListWidget(QListWidget):
    """Drag & drop .ts files, reorder, context menu, and track per-file items.
    Enhanced with progress display and status indicators.

    Domain state (status, progress, metadata) lives in a single ``FileQueueModel``
    rather than being smeared across per-item ``UserRole`` slots and a parallel
    cache. The widget keeps ``path_items`` purely as a path -> view-item map and
    renders each item from the model.
    """

    # Signal emitted when file order changes
    order_changed: ClassVar[Signal] = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # Single source of truth for domain state; path_items maps path -> view item.
        self.queue_model: FileQueueModel = FileQueueModel()
        self.path_items: dict[str, QListWidgetItem] = {}

        # Enhanced colors for different states with better contrast
        self.color_pending: QColor = QColor(64, 64, 64)  # Dark gray - neutral
        self.color_processing: QColor = QColor(0, 122, 204)  # Professional blue
        self.color_completed: QColor = QColor(34, 139, 34)  # Forest green - success
        self.color_failed: QColor = QColor(220, 53, 69)  # Bootstrap red - error
        self.color_skipped: QColor = QColor(
            255, 193, 7
        )  # Amber/yellow - skipped (output exists)

        # Set fixed height for items
        self.setIconSize(QSize(16, 16))
        self.setSpacing(2)

        # Metadata support
        self.thread_pool: QThreadPool = QThreadPool()
        self.metadata_signals: MetadataSignals = MetadataSignals()
        _ = self.metadata_signals.metadata_loaded.connect(self._on_metadata_loaded)

    def add_path(self, path: str):
        """Add a new file path to the list with pending status."""
        if path in self.queue_model:
            return
        fname = QFileInfo(path).fileName()

        # Create item; the path is stored on the item so Qt-side reordering can
        # be mapped back to model order. Status/progress/metadata live in the model.
        item = QListWidgetItem(f"{fname} • Loading...")
        item.setData(Qt.ItemDataRole.UserRole, path)

        # Set font for better readability
        font = item.font()
        font.setPointSize(font.pointSize() + 1)
        item.setFont(font)

        _ = self.addItem(item)
        self.path_items[path] = item
        _ = self.queue_model.add(path)

        # Render the initial (loading) state and start metadata loading.
        self._update_item_display(path)
        self._load_metadata_async(path)

    @override
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    # Supported video extensions (aligned with main_window file dialog)
    SUPPORTED_EXTENSIONS: tuple[str, ...] = (
        ".ts",
        ".mp4",
        ".m4v",
        ".mov",
        ".avi",
        ".mkv",
    )

    @override
    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            # External file drop - add new files
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith(self.SUPPORTED_EXTENSIONS) and os.path.isfile(
                    path
                ):
                    self.add_path(path)
            event.acceptProposedAction()
        else:
            # Internal move - handle reordering
            super().dropEvent(event)

            # Sync our path_items map and model order after the internal move
            self._rebuild_path_items_mapping()

            # Emit signal when order changed
            self.order_changed.emit()

    @override
    def contextMenuEvent(self, _event: object) -> None:
        menu = QMenu(self)
        selected_items = self.selectedItems()

        if selected_items:
            # Reordering options
            move_up_action = menu.addAction("Move Up")
            move_down_action = menu.addAction("Move Down")
            _ = menu.addSeparator()

            # File operations
            open_action = menu.addAction("Open Containing Folder")
            remove_action = menu.addAction("Remove Selected")

            # Enable/disable move actions based on selection position
            if selected_items:
                first_row = min(self.row(item) for item in selected_items)
                last_row = max(self.row(item) for item in selected_items)
                move_up_action.setEnabled(first_row > 0)
                move_down_action.setEnabled(last_row < self.count() - 1)
        else:
            # No selection - limited options
            open_action = None
            remove_action = None
            move_up_action = None
            move_down_action = None

        chosen = menu.exec(QCursor.pos())

        if chosen == move_up_action:
            self.move_selected_up()
        elif chosen == move_down_action:
            self.move_selected_down()
        elif chosen == open_action:
            for item in selected_items:
                folder: str = cast("str", item.data(Qt.ItemDataRole.UserRole))
                folder = os.path.dirname(folder)
                if os.path.isdir(folder):
                    self._open_folder(folder)
        elif chosen == remove_action:
            for item in selected_items:
                path: str = cast("str", item.data(Qt.ItemDataRole.UserRole))
                row = self.row(item)
                _ = self.takeItem(row)
                _ = self.path_items.pop(path, None)
                _ = self.queue_model.remove(path)

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        item = self.itemAt(event.pos())
        if item:
            path: str = cast("str", item.data(Qt.ItemDataRole.UserRole))
            folder: str = os.path.dirname(path)
            if os.path.isdir(folder):
                self._open_folder(folder)
        super().mouseDoubleClickEvent(event)

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts for reordering"""
        # Ctrl+Up - Move selected items up
        if (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_Up
        ):
            self.move_selected_up()
            event.accept()
            return
        # Ctrl+Down - Move selected items down
        if (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_Down
        ):
            self.move_selected_down()
            event.accept()
            return
        # Delete - Remove selected items
        if event.key() == Qt.Key.Key_Delete:
            _ = self.remove_selected()
            event.accept()
            return

        # Pass other events to parent
        super().keyPressEvent(event)

    def _open_folder(self, folder: str):
        """Open folder in file manager - cross-platform"""
        # Validate folder exists before attempting to open
        if not os.path.isdir(folder):
            return

        _ = QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _rebuild_path_items_mapping(self):
        """Rebuild the path_items map and the model order after a reorder."""
        self.path_items.clear()

        # Rebuild mapping and capture the new display order from the view
        order: list[str] = []
        for i in range(self.count()):
            item = self.item(i)
            if item:
                path: str = cast("str", item.data(Qt.ItemDataRole.UserRole))
                if path:
                    self.path_items[path] = item
                    order.append(path)

        # Keep the model's order in sync with the view
        self.queue_model.reorder(order)

    def update_progress(self, path: str, progress: int):
        """Update the progress percentage for a file.

        Args:
            path: The file path
            progress: Progress percentage (0-100)
        """
        entry = self.queue_model.get(path)
        item = self.path_items.get(path)
        if entry is None or item is None:
            return

        # Store the current progress
        entry.progress = progress

        # Update status if needed
        if progress > 0 and entry.status == FileStatus.PENDING:
            entry.status = FileStatus.PROCESSING
            item.setForeground(self.color_processing)

        # Update the displayed text using the unified method
        self._update_item_display(path)

    def set_status(self, path: str, status: str):
        """Set the status of a file item.

        Args:
            path: The file path
            status: One of 'pending', 'processing', 'completed', 'failed', 'skipped'
        """
        entry = self.queue_model.get(path)
        item = self.path_items.get(path)
        if entry is None or item is None:
            return

        # Store the status
        entry.status = FileStatus(status)

        # Set color based on status
        if entry.status == FileStatus.PENDING:
            item.setForeground(self.color_pending)
        elif entry.status == FileStatus.PROCESSING:
            item.setForeground(self.color_processing)
        elif entry.status == FileStatus.COMPLETED:
            item.setForeground(self.color_completed)
            # Make the text bold
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        elif entry.status == FileStatus.FAILED:
            item.setForeground(self.color_failed)
        elif entry.status == FileStatus.SKIPPED:
            item.setForeground(self.color_skipped)

        # Update the displayed text using the unified method
        self._update_item_display(path)

    def get_item_status(self, path: str) -> str:
        """Get the current status of an item.

        Args:
            path: The file path

        Returns:
            Status string or empty string if path not found
        """
        entry = self.queue_model.get(path)
        return entry.status.value if entry is not None else ""

    def add_files(self, file_paths: list[str]) -> None:
        """Add multiple files to the list"""
        for path in file_paths:
            self.add_path(path)

    @override
    def clear(self) -> None:
        """Clear all items and reset internal tracking state.

        Overrides QListWidget.clear() to also reset the model and path_items
        map, preventing memory leaks and ensuring files can be re-added after
        clearing.
        """
        self.path_items.clear()
        self.queue_model.clear()
        super().clear()

    def remove_selected(self) -> int:
        """Remove selected items and return count of removed items"""
        selected_items = self.selectedItems()
        removed_count = 0

        for item in selected_items:
            path: str = cast("str", item.data(Qt.ItemDataRole.UserRole))
            if path in self.queue_model:
                _ = self.queue_model.remove(path)
                _ = self.path_items.pop(path, None)
                _ = self.takeItem(self.row(item))
                removed_count += 1

        return removed_count

    def get_file_paths_in_order(self) -> list[str]:
        """Get all file paths in current display order"""
        paths: list[str] = []
        for i in range(self.count()):
            item = self.item(i)
            if item:
                path: str = cast("str", item.data(Qt.ItemDataRole.UserRole))
                if path:
                    paths.append(path)
        return paths

    def get_pending_files_in_order(self) -> list[str]:
        """Get only pending file paths in current display order"""
        paths: list[str] = []
        for i in range(self.count()):
            item = self.item(i)
            if item:
                path: str = cast("str", item.data(Qt.ItemDataRole.UserRole))
                entry = self.queue_model.get(path)
                if path and entry is not None and entry.status == FileStatus.PENDING:
                    paths.append(path)
        return paths

    def move_selected_up(self):
        """Move selected items up in the list"""
        selected_items = self.selectedItems()
        if not selected_items:
            return

        # Get row indices and sort them
        rows = [self.row(item) for item in selected_items]
        rows.sort()

        # Can't move up if first item is selected
        if rows[0] == 0:
            return

        # Move each item up
        for row in rows:
            item = self.takeItem(row)
            self.insertItem(row - 1, item)

        # Update selection
        self.clearSelection()
        for row in rows:
            self.item(row - 1).setSelected(True)

        # Rebuild mapping
        self._rebuild_path_items_mapping()

        # Emit order changed signal
        self.order_changed.emit()

    def move_selected_down(self):
        """Move selected items down in the list"""
        selected_items = self.selectedItems()
        if not selected_items:
            return

        # Get row indices and sort them in reverse
        rows = [self.row(item) for item in selected_items]
        rows.sort(reverse=True)

        # Can't move down if last item is selected
        if rows[0] == self.count() - 1:
            return

        # Move each item down
        for row in rows:
            item = self.takeItem(row)
            self.insertItem(row + 1, item)

        # Update selection
        self.clearSelection()
        for row in reversed(rows):
            self.item(row + 1).setSelected(True)

        # Rebuild mapping
        self._rebuild_path_items_mapping()

        # Emit order changed signal
        self.order_changed.emit()

    def get_file_paths(self) -> list[str]:
        """Get all file paths in the list"""
        return self.queue_model.paths_in_order()

    def get_file_count(self) -> int:
        """Get the number of files in the list"""
        return len(self.queue_model)

    def _load_metadata_async(self, path: str):
        """Load metadata for a file asynchronously"""
        entry = self.queue_model.get(path)
        if entry is None or entry.metadata_requested:
            # Unknown path or already loading/loaded
            return

        # Mark as requested so the worker starts at most once
        entry.metadata_requested = True

        # Create worker and submit to thread pool
        worker = MetadataWorker(path, self.metadata_signals)
        self.thread_pool.start(worker)

    def _on_metadata_loaded(self, file_path: str, metadata: object) -> None:
        """Handle metadata loading completion"""
        # Check if file was removed before metadata loaded (prevents memory leak)
        entry = self.queue_model.get(file_path)
        if entry is None:
            return

        # Validate and store metadata
        # The metadata comes from extract_video_metadata which returns VideoMetadata | None
        # We accept it as object from signal, then validate and cast
        if isinstance(metadata, dict):
            # Runtime validation - double cast through object to VideoMetadata
            # We trust that extract_video_metadata returns the correct structure
            entry.metadata = cast("VideoMetadata", cast("object", metadata))
        else:
            entry.metadata = None

        # Update the display for this file
        self._update_item_display(file_path)

    def _update_item_display(self, path: str):
        """Update the display text for a file item based on its current state"""
        entry = self.queue_model.get(path)
        item = self.path_items.get(path)
        if entry is None or item is None:
            return

        fname = QFileInfo(path).fileName()
        item.setText(compute_display(fname, entry))

        # Update tooltip with rich information
        metadata = entry.metadata
        tooltip_lines = [f"Path: {path}"]

        if metadata:
            if metadata.get("duration") != "Unknown":
                tooltip_lines.append(f"Duration: {metadata['duration']}")
            if metadata.get("width", 0) > 0 and metadata.get("height", 0) > 0:
                tooltip_lines.append(
                    f"Resolution: {metadata['width']}x{metadata['height']}"
                )
            if metadata.get("codec", "").upper() not in ["", "UNKNOWN"]:
                tooltip_lines.append(f"Codec: {metadata['codec']}")
            if metadata.get("bitrate", "") not in ["", "Unknown"]:
                tooltip_lines.append(f"Bitrate: {metadata['bitrate']}")
            if metadata.get("format_name", "") not in ["", "Unknown"]:
                tooltip_lines.append(f"Format: {metadata['format_name']}")

        tooltip_lines.append(f"Status: {entry.status.value.title()}")
        if entry.status == FileStatus.PROCESSING and entry.progress > 0:
            tooltip_lines.append(f"Progress: {entry.progress}%")

        item.setToolTip("\n".join(tooltip_lines))

    def get_file_metadata(self, path: str) -> VideoMetadata | None:
        """Get cached metadata for a file"""
        entry = self.queue_model.get(path)
        return entry.metadata if entry is not None else None

    def update_all_display_with_settings(self, codec_idx: int, crf_value: int):
        """Update all file displays with estimated output sizes"""
        for entry in self.queue_model.entries_in_order():
            metadata = entry.metadata
            if metadata:
                # Add estimated size to metadata display
                estimated_size = SizeEstimator.estimate_output_size(
                    metadata, codec_idx, crf_value
                )
                if estimated_size:
                    item = self.path_items.get(entry.path)
                    if item is None:
                        continue
                    current_text = item.text()
                    # Remove old size estimate if present
                    if " • Est:" in current_text:
                        current_text = current_text.split(" • Est:")[0]
                    item.setText(f"{current_text} • Est: {estimated_size}")

    def get_total_estimated_size(self, codec_idx: int, crf_value: int) -> str:
        """Calculate total estimated output size for all files"""
        total_bytes = 0
        count = 0

        for entry in self.queue_model.entries_in_order():
            metadata = entry.metadata
            if metadata and metadata.get("duration_seconds", 0) > 0:
                estimated_size = SizeEstimator.estimate_output_size(
                    metadata, codec_idx, crf_value
                )
                if estimated_size:
                    # Parse size back to bytes for summation
                    size_bytes = self._parse_size_to_bytes(estimated_size)
                    if size_bytes > 0:
                        total_bytes += size_bytes
                        count += 1

        if count == 0:
            return "Calculating..."

        return SizeEstimator.format_file_size(total_bytes)

    def _parse_size_to_bytes(self, size_str: str) -> float:
        """Parse a size string back to bytes"""
        size_str = size_str.strip()
        if size_str.endswith(" GB"):
            return float(size_str[:-3]) * 1024 * 1024 * 1024
        if size_str.endswith(" MB"):
            return float(size_str[:-3]) * 1024 * 1024
        if size_str.endswith(" KB"):
            return float(size_str[:-3]) * 1024
        if size_str.endswith(" B"):
            return float(size_str[:-2])
        return 0

    # Batch Operations
    def select_all_files(self):
        """Select all files in the list"""
        self.selectAll()

    def clear_completed_files(self) -> int:
        """Remove all completed files from the list"""
        completed_paths = self.queue_model.paths_with_status(FileStatus.COMPLETED)

        for path in completed_paths:
            item = self.path_items.get(path)
            if item is not None:
                _ = self.takeItem(self.row(item))
            _ = self.path_items.pop(path, None)
            _ = self.queue_model.remove(path)

        return len(completed_paths)

    def remove_failed_files(self) -> int:
        """Remove all failed files from the list"""
        failed_paths = self.queue_model.paths_with_status(FileStatus.FAILED)

        for path in failed_paths:
            item = self.path_items.get(path)
            if item is not None:
                _ = self.takeItem(self.row(item))
            _ = self.path_items.pop(path, None)
            _ = self.queue_model.remove(path)

        return len(failed_paths)

    def get_files_by_status(self, status: str) -> list[str]:
        """Get all file paths with the specified status"""
        return self.queue_model.paths_with_status(FileStatus(status))

    def get_status_counts(self) -> dict[str, int]:
        """Get count of files by status"""
        counts = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}

        for entry in self.queue_model.entries_in_order():
            key = entry.status.value
            if key in counts:
                counts[key] += 1

        return counts

    def refresh_drag_drop_state(self):
        """Refresh drag-and-drop functionality - useful after conversions complete"""
        # Ensure drag-and-drop settings are properly enabled
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        # Clear any potential focus issues that might interfere with drag-and-drop
        self.clearFocus()
        self.setFocus()

    def cleanup(self) -> None:
        """Clean up thread pool before destruction.

        Call this method before the widget is destroyed (e.g., in closeEvent)
        to ensure background metadata workers finish before the widget is gone.
        """
        _ = self.thread_pool.waitForDone(5000)  # Wait up to 5 seconds
