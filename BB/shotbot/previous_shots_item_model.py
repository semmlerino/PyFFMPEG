"""Qt Model/View item model for previous shots display.

This model provides a QAbstractListModel implementation for displaying
approved/completed shots in a view, enabling efficient virtualization
and lazy loading of thumbnails.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from shot_item_model import ShotRole  # Reuse the same roles

if TYPE_CHECKING:
    from cache_manager import CacheManager
    from previous_shots_model import PreviousShotsModel
    from shot_model import Shot

logger = logging.getLogger(__name__)


class PreviousShotsItemModel(QAbstractListModel):
    """Qt item model for previous/approved shots.
    
    This model wraps PreviousShotsModel and provides the Qt Model/View
    interface for efficient display in views. It handles:
    - Data provision for views
    - Thumbnail loading coordination
    - Selection state management
    """

    # Signals
    shots_updated = Signal()
    selection_changed = Signal(object)  # Shot or None

    def __init__(
        self,
        previous_shots_model: PreviousShotsModel,
        cache_manager: CacheManager | None = None,
        parent=None,
    ):
        """Initialize the item model.

        Args:
            previous_shots_model: The underlying previous shots model
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent object
        """
        super().__init__(parent)
        
        self._model = previous_shots_model
        self._cache_manager = cache_manager
        self._shots: list[Shot] = []
        self._thumbnail_cache: dict[str, Any] = {}
        self._visible_start = 0
        self._visible_end = 0
        self._selected_shot: Shot | None = None

        # Connect to underlying model signals
        self._model.shots_updated.connect(self._on_shots_updated)
        
        # Initialize with current shots
        self._update_shots()
        
        logger.info(
            f"PreviousShotsItemModel initialized with {len(self._shots)} shots"
        )

    @property
    def shots(self) -> list[Shot]:
        """Get the current list of shots.

        Returns:
            List of Shot objects
        """
        return self._shots

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        """Return the number of rows (shots) in the model.

        Args:
            parent: Parent index (unused in list model)

        Returns:
            Number of shots
        """
        if parent.isValid():
            return 0
        return len(self._shots)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return data for the given index and role.

        Args:
            index: Model index
            role: Data role

        Returns:
            Requested data or None
        """
        if not index.isValid() or index.row() >= len(self._shots):
            return None

        shot = self._shots[index.row()]

        # Reuse ShotRole enum for consistency
        if role == Qt.ItemDataRole.DisplayRole:
            return shot.full_name
        elif role == ShotRole.FullNameRole:
            return shot.full_name
        elif role == ShotRole.ShowRole:
            return shot.show
        elif role == ShotRole.SequenceRole:
            return shot.sequence
        elif role == ShotRole.ShotNameRole:
            return shot.shot
        elif role == ShotRole.ShotObjectRole:
            return shot
        elif role == ShotRole.ThumbnailPathRole:
            return shot.get_thumbnail_path()
        elif role == ShotRole.ThumbnailPixmapRole:
            # Return cached pixmap if available
            return self._thumbnail_cache.get(shot.full_name)
        elif role == ShotRole.LoadingStateRole:
            # Could track loading state per shot
            return "idle"
        elif role == ShotRole.IsSelectedRole:
            return shot == self._selected_shot

        return None

    def setData(
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        """Set data for the given index and role.

        Args:
            index: Model index
            value: Value to set
            role: Data role

        Returns:
            True if successful
        """
        if not index.isValid() or index.row() >= len(self._shots):
            return False

        if role == ShotRole.ThumbnailPixmapRole:
            # Cache thumbnail pixmap
            shot = self._shots[index.row()]
            self._thumbnail_cache[shot.full_name] = value
            self.dataChanged.emit(index, index, [role])
            return True
        elif role == ShotRole.IsSelectedRole:
            # Update selection
            shot = self._shots[index.row()]
            if value:
                self._selected_shot = shot
                self.selection_changed.emit(shot)
            elif shot == self._selected_shot:
                self._selected_shot = None
                self.selection_changed.emit(None)
            self.dataChanged.emit(index, index, [role])
            return True

        return False

    def set_visible_range(self, start: int, end: int) -> None:
        """Set the visible range for lazy loading.

        Args:
            start: First visible row
            end: Last visible row (exclusive)
        """
        self._visible_start = max(0, start)
        self._visible_end = min(end, len(self._shots))
        
        # Trigger thumbnail loading for visible items
        if self._cache_manager:
            for i in range(self._visible_start, self._visible_end):
                if i < len(self._shots):
                    shot = self._shots[i]
                    if shot.full_name not in self._thumbnail_cache:
                        # Request thumbnail loading
                        self._load_thumbnail(shot, i)

    def _load_thumbnail(self, shot: Shot, row: int) -> None:
        """Load thumbnail for a shot asynchronously.

        Args:
            shot: Shot object
            row: Row index
        """
        thumbnail_path = shot.get_thumbnail_path()
        if not thumbnail_path:
            return

        # Use cache manager to load thumbnail
        if self._cache_manager:
            # This would trigger async loading
            # For now, just mark as loading
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])

    @Slot()
    def _on_shots_updated(self) -> None:
        """Handle shots update from underlying model."""
        self._update_shots()

    def _update_shots(self) -> None:
        """Update the shot list from the underlying model."""
        self.beginResetModel()
        
        # Get shots from PreviousShotsModel
        self._shots = self._model.get_shots()
        
        # Clear thumbnail cache for removed shots
        current_names = {shot.full_name for shot in self._shots}
        self._thumbnail_cache = {
            name: pixmap
            for name, pixmap in self._thumbnail_cache.items()
            if name in current_names
        }
        
        # Clear selection if shot was removed
        if self._selected_shot and self._selected_shot not in self._shots:
            self._selected_shot = None
            self.selection_changed.emit(None)
        
        self.endResetModel()
        self.shots_updated.emit()
        
        logger.debug(f"Updated model with {len(self._shots)} previous shots")

    def get_selected_shot(self) -> Shot | None:
        """Get the currently selected shot.

        Returns:
            Selected shot or None
        """
        return self._selected_shot

    def clear_selection(self) -> None:
        """Clear the current selection."""
        if self._selected_shot:
            # Find and update the index
            for i, shot in enumerate(self._shots):
                if shot == self._selected_shot:
                    index = self.index(i, 0)
                    self.setData(index, False, ShotRole.IsSelectedRole)
                    break

    def refresh(self) -> None:
        """Trigger a refresh of the underlying model."""
        self._model.refresh_shots()