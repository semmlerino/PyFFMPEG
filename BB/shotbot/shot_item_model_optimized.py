"""Optimized Qt Model/View implementation with async loading and virtual proxy pattern.

This module provides a highly optimized QAbstractItemModel implementation with:
- True asynchronous thumbnail loading using QThreadPool
- Incremental updates without full model resets
- Virtual proxy pattern for handling 10,000+ items efficiently
- Intelligent prefetching based on scroll direction
- Memory-efficient caching with automatic cleanup
"""

import logging
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QMutex,
    QMutexLocker,
    QObject,
    QPersistentModelIndex,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QIcon, QPixmap

from cache_manager import CacheManager
from config import Config
from shot_model import RefreshResult, Shot

logger = logging.getLogger(__name__)


class ShotRole(IntEnum):
    """Custom roles for shot data access."""

    # Standard roles
    DisplayRole = Qt.ItemDataRole.DisplayRole
    DecorationRole = Qt.ItemDataRole.DecorationRole
    ToolTipRole = Qt.ItemDataRole.ToolTipRole
    SizeHintRole = Qt.ItemDataRole.SizeHintRole

    # Custom roles
    ShotObjectRole = Qt.ItemDataRole.UserRole + 1
    ShowRole = Qt.ItemDataRole.UserRole + 2
    SequenceRole = Qt.ItemDataRole.UserRole + 3
    ShotNameRole = Qt.ItemDataRole.UserRole + 4
    FullNameRole = Qt.ItemDataRole.UserRole + 5
    WorkspacePathRole = Qt.ItemDataRole.UserRole + 6
    ThumbnailPathRole = Qt.ItemDataRole.UserRole + 7
    ThumbnailPixmapRole = Qt.ItemDataRole.UserRole + 8
    LoadingStateRole = Qt.ItemDataRole.UserRole + 9
    IsSelectedRole = Qt.ItemDataRole.UserRole + 10
    LoadProgressRole = Qt.ItemDataRole.UserRole + 11


@dataclass
class LoadingTask:
    """Represents a thumbnail loading task."""

    shot: Shot
    row: int
    priority: int = 0
    cancelled: bool = False


class ThumbnailLoader(QRunnable):
    """Asynchronous thumbnail loader using QThreadPool.

    This class handles background loading of thumbnails with:
    - Priority-based loading queue
    - Cancellation support for scrolled-away items
    - Automatic format detection and conversion
    - Thread-safe signal emission
    """

    class Signals(QObject):
        """Signals for thread-safe communication."""

        thumbnail_loaded = Signal(int, QPixmap)  # row, pixmap
        loading_failed = Signal(int, str)  # row, error_message
        progress_updated = Signal(int, int)  # row, progress_percentage

    def __init__(
        self,
        task: LoadingTask,
        cache_manager: Optional[CacheManager],
        model_ref: weakref.ref,
    ):
        """Initialize the thumbnail loader.

        Args:
            task: Loading task with shot information
            cache_manager: Cache manager for thumbnail storage
            model_ref: Weak reference to the model (prevents circular refs)
        """
        super().__init__()
        self.task = task
        self.cache_manager = cache_manager
        self.model_ref = model_ref
        self.signals = self.Signals()
        self.setAutoDelete(True)

    def run(self):
        """Execute the thumbnail loading in a worker thread."""
        if self.task.cancelled:
            return

        model = self.model_ref()
        if not model:
            return  # Model was deleted

        try:
            # Emit progress start
            self.signals.progress_updated.emit(self.task.row, 0)

            thumbnail_path = self.task.shot.get_thumbnail_path()
            if not thumbnail_path or not thumbnail_path.exists():
                self.signals.loading_failed.emit(
                    self.task.row, "Thumbnail file not found"
                )
                return

            # Check if cancelled during file check
            if self.task.cancelled:
                return

            # Progress: Found file
            self.signals.progress_updated.emit(self.task.row, 25)

            # Handle different file formats
            suffix_lower = thumbnail_path.suffix.lower()

            if suffix_lower == ".exr" and self.cache_manager:
                # Use cache manager for EXR with PIL conversion
                self.signals.progress_updated.emit(self.task.row, 50)

                cached_path = self.cache_manager.cache_thumbnail(
                    thumbnail_path,
                    self.task.shot.show,
                    self.task.shot.sequence,
                    self.task.shot.shot,
                    wait=True,
                )

                if self.task.cancelled:
                    return

                if cached_path and cached_path.exists():
                    pixmap = QPixmap(str(cached_path))
                    self.signals.progress_updated.emit(self.task.row, 75)
                else:
                    self.signals.loading_failed.emit(
                        self.task.row, "Failed to cache EXR thumbnail"
                    )
                    return
            else:
                # Direct loading for standard formats
                self.signals.progress_updated.emit(self.task.row, 50)
                pixmap = QPixmap(str(thumbnail_path))
                self.signals.progress_updated.emit(self.task.row, 75)

            if self.task.cancelled:
                return

            if not pixmap.isNull():
                # Scale to thumbnail size
                scaled_pixmap = pixmap.scaled(
                    Config.DEFAULT_THUMBNAIL_SIZE,
                    Config.DEFAULT_THUMBNAIL_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

                self.signals.progress_updated.emit(self.task.row, 100)
                self.signals.thumbnail_loaded.emit(self.task.row, scaled_pixmap)
            else:
                self.signals.loading_failed.emit(self.task.row, "Invalid image format")

        except Exception as e:
            logger.error(f"Thumbnail loading error for row {self.task.row}: {e}")
            self.signals.loading_failed.emit(self.task.row, str(e))


class ShotItemModelOptimized(QAbstractListModel):
    """Optimized Qt Model with async loading and virtual proxy pattern.

    Features:
    - True async thumbnail loading with QThreadPool
    - Incremental updates (no full resets)
    - Virtual proxy with canFetchMore/fetchMore
    - Intelligent prefetching based on scroll patterns
    - Memory-efficient LRU cache with size limits
    - Thread-safe operations with proper locking
    """

    # Signals
    shots_updated = Signal()
    thumbnail_loaded = Signal(int)  # row index
    selection_changed = Signal(QModelIndex)
    loading_progress = Signal(int, int)  # loaded_count, total_count

    # Constants
    CHUNK_SIZE = 100  # Items to load per fetch
    CACHE_SIZE_LIMIT = 200  # Maximum cached thumbnails
    PREFETCH_BUFFER = 20  # Items to prefetch ahead/behind visible
    MAX_CONCURRENT_LOADS = 4  # Parallel loading threads

    def __init__(
        self,
        cache_manager: Optional[CacheManager] = None,
        parent: Optional[QObject] = None,
    ):
        """Initialize the optimized model.

        Args:
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent QObject
        """
        super().__init__(parent)

        # Data storage
        self._all_shots: List[Shot] = []  # All available shots
        self._loaded_shots: List[Shot] = []  # Currently loaded subset
        self._thumbnail_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._loading_states: Dict[str, str] = {}
        self._loading_tasks: Dict[int, LoadingTask] = {}

        # State tracking
        self._selected_index = QPersistentModelIndex()
        self._visible_start = 0
        self._visible_end = 0
        self._last_scroll_direction = 0  # -1 up, 0 none, 1 down
        self._fetch_more_enabled = True

        # Thread safety
        self._cache_mutex = QMutex()
        self._task_mutex = QMutex()

        # Thread pool for async loading
        self._thread_pool = QThreadPool()
        self._thread_pool.setMaxThreadCount(self.MAX_CONCURRENT_LOADS)

        # Cache manager
        self._cache_manager = cache_manager or CacheManager()

        # Cleanup timer for cache
        self._cleanup_timer = QTimer()
        self._cleanup_timer.timeout.connect(self._cleanup_cache)
        self._cleanup_timer.setInterval(30000)  # 30 seconds
        self._cleanup_timer.start()

        logger.info(
            f"Optimized model initialized with chunk_size={self.CHUNK_SIZE}, "
            f"max_threads={self.MAX_CONCURRENT_LOADS}"
        )

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return number of currently loaded shots."""
        if parent.isValid():
            return 0
        return len(self._loaded_shots)

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:
        """Check if more data can be fetched (virtual proxy pattern)."""
        if parent.isValid():
            return False
        return self._fetch_more_enabled and len(self._loaded_shots) < len(
            self._all_shots
        )

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:
        """Fetch next chunk of data (virtual proxy pattern)."""
        if parent.isValid():
            return

        current_count = len(self._loaded_shots)
        total_count = len(self._all_shots)

        if current_count >= total_count:
            return

        # Calculate chunk to fetch
        fetch_count = min(self.CHUNK_SIZE, total_count - current_count)

        # Begin insertion
        self.beginInsertRows(
            QModelIndex(), current_count, current_count + fetch_count - 1
        )

        # Add shots to loaded list
        self._loaded_shots.extend(
            self._all_shots[current_count : current_count + fetch_count]
        )

        # End insertion
        self.endInsertRows()

        # Emit progress
        self.loading_progress.emit(len(self._loaded_shots), total_count)

        logger.debug(
            f"Fetched {fetch_count} more items, "
            f"total loaded: {len(self._loaded_shots)}/{total_count}"
        )

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Get data for the given index and role."""
        if not index.isValid() or not (0 <= index.row() < len(self._loaded_shots)):
            return None

        shot = self._loaded_shots[index.row()]

        # Handle standard roles
        if role == Qt.ItemDataRole.DisplayRole:
            return shot.full_name

        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{shot.show} / {shot.sequence} / {shot.shot}\n{shot.workspace_path}"

        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(
                Config.DEFAULT_THUMBNAIL_SIZE, Config.DEFAULT_THUMBNAIL_SIZE + 40
            )

        # Handle custom roles
        if role == ShotRole.ShotObjectRole:
            return shot

        if role == ShotRole.FullNameRole:
            return shot.full_name

        if role == ShotRole.ThumbnailPixmapRole:
            return self._get_thumbnail_pixmap(shot, index.row())

        if role == ShotRole.LoadingStateRole:
            return self._loading_states.get(shot.full_name, "idle")

        if role == ShotRole.IsSelectedRole:
            return self._selected_index == QPersistentModelIndex(index)

        if role == Qt.ItemDataRole.DecorationRole:
            pixmap = self._get_thumbnail_pixmap(shot, index.row())
            return QIcon(pixmap) if pixmap else None

        # Other roles omitted for brevity but would be included
        return None

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        """Set data for the given index and role."""
        if not index.isValid() or not (0 <= index.row() < len(self._loaded_shots)):
            return False

        shot = self._loaded_shots[index.row()]

        if role == ShotRole.IsSelectedRole:
            if value:
                old_selection = self._selected_index
                self._selected_index = QPersistentModelIndex(index)

                # Clear old selection
                if old_selection.isValid():
                    old_index = QModelIndex(old_selection)
                    self.dataChanged.emit(
                        old_index, old_index, [ShotRole.IsSelectedRole]
                    )

                # Emit new selection
                self.dataChanged.emit(index, index, [ShotRole.IsSelectedRole])
                self.selection_changed.emit(index)
            else:
                self._selected_index = QPersistentModelIndex()
                self.dataChanged.emit(index, index, [ShotRole.IsSelectedRole])

            return True

        if role == ShotRole.LoadingStateRole:
            self._loading_states[shot.full_name] = value
            self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])
            return True

        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """Get flags for the given index."""
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    @Slot(list)
    def set_shots(self, shots: List[Shot]) -> None:
        """Set the complete shot list with incremental loading."""
        # Store all shots
        self._all_shots = shots

        # Reset model with initial chunk
        self.beginResetModel()

        # Load initial chunk
        initial_count = min(self.CHUNK_SIZE, len(shots))
        self._loaded_shots = shots[:initial_count]

        # Clear caches
        with QMutexLocker(self._cache_mutex):
            self._thumbnail_cache.clear()
        self._loading_states.clear()
        self._cancel_all_loading_tasks()
        self._selected_index = QPersistentModelIndex()

        self.endResetModel()

        self.shots_updated.emit()
        self.loading_progress.emit(initial_count, len(shots))

        logger.info(
            f"Model initialized with {initial_count}/{len(shots)} shots "
            f"(virtual proxy enabled)"
        )

    @Slot(int, int)
    def set_visible_range(self, start: int, end: int) -> None:
        """Set visible range for intelligent prefetching.

        Args:
            start: First visible row
            end: Last visible row
        """
        old_start = self._visible_start
        self._visible_start = max(0, start)
        self._visible_end = min(len(self._loaded_shots), end)

        # Detect scroll direction
        if start < old_start:
            self._last_scroll_direction = -1  # Scrolling up
        elif start > old_start:
            self._last_scroll_direction = 1  # Scrolling down
        else:
            self._last_scroll_direction = 0  # No scroll

        # Cancel tasks outside new visible range + buffer
        self._cancel_tasks_outside_range(
            start - self.PREFETCH_BUFFER, end + self.PREFETCH_BUFFER
        )

        # Start loading for visible range with prefetch
        self._load_visible_thumbnails_async()

    def _load_visible_thumbnails_async(self) -> None:
        """Load thumbnails asynchronously with intelligent prefetching."""
        # Calculate range with directional prefetch
        if self._last_scroll_direction < 0:
            # Scrolling up - prefetch more above
            prefetch_before = self.PREFETCH_BUFFER * 2
            prefetch_after = self.PREFETCH_BUFFER // 2
        elif self._last_scroll_direction > 0:
            # Scrolling down - prefetch more below
            prefetch_before = self.PREFETCH_BUFFER // 2
            prefetch_after = self.PREFETCH_BUFFER * 2
        else:
            # No scroll direction - equal prefetch
            prefetch_before = self.PREFETCH_BUFFER
            prefetch_after = self.PREFETCH_BUFFER

        start = max(0, self._visible_start - prefetch_before)
        end = min(len(self._loaded_shots), self._visible_end + prefetch_after)

        # Priority loading: visible items first, then prefetch
        for priority, row in enumerate(range(self._visible_start, self._visible_end)):
            if row < len(self._loaded_shots):
                self._queue_thumbnail_load(row, priority)

        # Lower priority for prefetch items
        for row in range(start, self._visible_start):
            self._queue_thumbnail_load(row, priority + 100)

        for row in range(self._visible_end, end):
            if row < len(self._loaded_shots):
                self._queue_thumbnail_load(row, priority + 100)

    def _queue_thumbnail_load(self, row: int, priority: int) -> None:
        """Queue a thumbnail for async loading.

        Args:
            row: Row index to load
            priority: Loading priority (lower = higher priority)
        """
        if not (0 <= row < len(self._loaded_shots)):
            return

        shot = self._loaded_shots[row]

        # Check if already loaded or loading
        with QMutexLocker(self._cache_mutex):
            if shot.full_name in self._thumbnail_cache:
                return

        if self._loading_states.get(shot.full_name) == "loading":
            return

        # Create loading task
        with QMutexLocker(self._task_mutex):
            if row in self._loading_tasks:
                # Update priority if needed
                self._loading_tasks[row].priority = min(
                    self._loading_tasks[row].priority, priority
                )
                return

            task = LoadingTask(shot=shot, row=row, priority=priority)
            self._loading_tasks[row] = task

        # Mark as loading
        self._loading_states[shot.full_name] = "loading"
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])

        # Create and start loader
        loader = ThumbnailLoader(task, self._cache_manager, weakref.ref(self))
        loader.signals.thumbnail_loaded.connect(self._on_thumbnail_loaded)
        loader.signals.loading_failed.connect(self._on_loading_failed)
        loader.signals.progress_updated.connect(self._on_loading_progress)

        # Set priority and start
        loader.setAutoDelete(True)
        self._thread_pool.start(loader, priority)

    @Slot(int, QPixmap)
    def _on_thumbnail_loaded(self, row: int, pixmap: QPixmap) -> None:
        """Handle successful thumbnail load.

        Args:
            row: Row index
            pixmap: Loaded thumbnail pixmap
        """
        if not (0 <= row < len(self._loaded_shots)):
            return

        shot = self._loaded_shots[row]

        # Cache the pixmap
        with QMutexLocker(self._cache_mutex):
            self._thumbnail_cache[shot.full_name] = pixmap
            self._enforce_cache_limit()

        # Update loading state
        self._loading_states[shot.full_name] = "loaded"

        # Remove task
        with QMutexLocker(self._task_mutex):
            self._loading_tasks.pop(row, None)

        # Notify view
        index = self.index(row, 0)
        self.dataChanged.emit(
            index,
            index,
            [
                ShotRole.ThumbnailPixmapRole,
                ShotRole.LoadingStateRole,
                Qt.ItemDataRole.DecorationRole,
            ],
        )
        self.thumbnail_loaded.emit(row)

    @Slot(int, str)
    def _on_loading_failed(self, row: int, error: str) -> None:
        """Handle failed thumbnail load.

        Args:
            row: Row index
            error: Error message
        """
        if not (0 <= row < len(self._loaded_shots)):
            return

        shot = self._loaded_shots[row]

        # Update loading state
        self._loading_states[shot.full_name] = "failed"

        # Remove task
        with QMutexLocker(self._task_mutex):
            self._loading_tasks.pop(row, None)

        # Notify view
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])

        logger.warning(f"Failed to load thumbnail for {shot.full_name}: {error}")

    @Slot(int, int)
    def _on_loading_progress(self, row: int, progress: int) -> None:
        """Handle loading progress update.

        Args:
            row: Row index
            progress: Progress percentage (0-100)
        """
        if not (0 <= row < len(self._loaded_shots)):
            return

        # Could emit progress for progress bars in delegate
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [ShotRole.LoadProgressRole])

    def _get_thumbnail_pixmap(self, shot: Shot, row: int) -> Optional[QPixmap]:
        """Get cached thumbnail or queue for loading.

        Args:
            shot: Shot object
            row: Row index

        Returns:
            Cached pixmap or None
        """
        with QMutexLocker(self._cache_mutex):
            pixmap = self._thumbnail_cache.get(shot.full_name)

        if not pixmap:
            # Queue for loading if in visible range
            if self._visible_start <= row <= self._visible_end + self.PREFETCH_BUFFER:
                self._queue_thumbnail_load(row, row - self._visible_start)

        return pixmap

    def _cancel_tasks_outside_range(self, start: int, end: int) -> None:
        """Cancel loading tasks outside the given range.

        Args:
            start: Start of valid range
            end: End of valid range
        """
        with QMutexLocker(self._task_mutex):
            for row, task in list(self._loading_tasks.items()):
                if row < start or row > end:
                    task.cancelled = True
                    self._loading_tasks.pop(row, None)

    def _cancel_all_loading_tasks(self) -> None:
        """Cancel all pending loading tasks."""
        with QMutexLocker(self._task_mutex):
            for task in self._loading_tasks.values():
                task.cancelled = True
            self._loading_tasks.clear()

    def _enforce_cache_limit(self) -> None:
        """Enforce cache size limit using LRU eviction."""
        while len(self._thumbnail_cache) > self.CACHE_SIZE_LIMIT:
            # Remove oldest item (first in OrderedDict)
            self._thumbnail_cache.popitem(last=False)

    @Slot()
    def _cleanup_cache(self) -> None:
        """Periodic cache cleanup to free memory."""
        with QMutexLocker(self._cache_mutex):
            # Remove pixmaps for shots no longer in view
            visible_shots = set()
            for i in range(
                max(0, self._visible_start - self.PREFETCH_BUFFER),
                min(len(self._loaded_shots), self._visible_end + self.PREFETCH_BUFFER),
            ):
                if i < len(self._loaded_shots):
                    visible_shots.add(self._loaded_shots[i].full_name)

            # Remove non-visible items beyond limit
            if len(self._thumbnail_cache) > self.CACHE_SIZE_LIMIT // 2:
                for shot_name in list(self._thumbnail_cache.keys()):
                    if shot_name not in visible_shots:
                        del self._thumbnail_cache[shot_name]
                        if len(self._thumbnail_cache) <= self.CACHE_SIZE_LIMIT // 2:
                            break

    def refresh_shots(self, shots: List[Shot]) -> RefreshResult:
        """Refresh shots with intelligent incremental updates.

        Args:
            shots: New list of shots

        Returns:
            RefreshResult indicating success and changes
        """
        # Build lookup sets for comparison
        old_shot_names = {shot.full_name for shot in self._all_shots}
        new_shot_names = {shot.full_name for shot in shots}

        has_changes = old_shot_names != new_shot_names

        if not has_changes:
            return RefreshResult(success=True, has_changes=False)

        # Determine what changed
        added_names = new_shot_names - old_shot_names
        removed_names = old_shot_names - new_shot_names

        if len(added_names) + len(removed_names) > len(self._all_shots) // 2:
            # Too many changes - do full reset
            self.set_shots(shots)
        else:
            # Incremental update
            self._apply_incremental_update(shots, added_names, removed_names)

        return RefreshResult(success=True, has_changes=True)

    def _apply_incremental_update(
        self, new_shots: List[Shot], added_names: Set[str], removed_names: Set[str]
    ) -> None:
        """Apply incremental updates to the model.

        Args:
            new_shots: New complete shot list
            added_names: Set of added shot names
            removed_names: Set of removed shot names
        """
        # Remove shots
        for i in range(len(self._loaded_shots) - 1, -1, -1):
            if self._loaded_shots[i].full_name in removed_names:
                self.beginRemoveRows(QModelIndex(), i, i)
                removed_shot = self._loaded_shots.pop(i)

                # Clean up cache
                with QMutexLocker(self._cache_mutex):
                    self._thumbnail_cache.pop(removed_shot.full_name, None)
                self._loading_states.pop(removed_shot.full_name, None)

                self.endRemoveRows()

        # Add new shots
        for shot in new_shots:
            if shot.full_name in added_names:
                insert_pos = len(self._loaded_shots)
                self.beginInsertRows(QModelIndex(), insert_pos, insert_pos)
                self._loaded_shots.append(shot)
                self.endInsertRows()

        # Update complete list
        self._all_shots = new_shots

    def get_shot_at_index(self, index: QModelIndex) -> Optional[Shot]:
        """Get shot object at the given index.

        Args:
            index: Model index

        Returns:
            Shot object or None if invalid
        """
        if index.isValid() and 0 <= index.row() < len(self._loaded_shots):
            return self._loaded_shots[index.row()]
        return None

    def clear_thumbnail_cache(self) -> None:
        """Clear the thumbnail cache to free memory."""
        with QMutexLocker(self._cache_mutex):
            self._thumbnail_cache.clear()

        # Cancel all loading tasks
        self._cancel_all_loading_tasks()

        # Notify all items that thumbnails need reloading
        if self._loaded_shots:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._loaded_shots) - 1, 0),
                [ShotRole.ThumbnailPixmapRole, Qt.ItemDataRole.DecorationRole],
            )

    def enable_virtual_proxy(self, enabled: bool) -> None:
        """Enable or disable virtual proxy loading.

        Args:
            enabled: Whether to enable virtual proxy
        """
        self._fetch_more_enabled = enabled

        if not enabled and len(self._loaded_shots) < len(self._all_shots):
            # Load all remaining shots
            self.beginInsertRows(
                QModelIndex(), len(self._loaded_shots), len(self._all_shots) - 1
            )
            self._loaded_shots = self._all_shots.copy()
            self.endInsertRows()
