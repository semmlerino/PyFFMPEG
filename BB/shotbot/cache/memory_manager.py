"""Memory management for cache operations with LRU eviction."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config import ThreadingConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages memory usage for cached items with LRU eviction.

    This class tracks memory usage of cached files and implements
    Least Recently Used (LRU) eviction when memory limits are exceeded.
    It maintains thread safety for concurrent access.
    """

    def __init__(self, max_memory_mb: int | None = None):
        """Initialize memory manager.

        Args:
            max_memory_mb: Maximum memory limit in MB. If None, uses config default.
        """
        self._lock = threading.RLock()

        # Memory tracking
        self._memory_usage_bytes = 0
        self._cached_items: dict[str, int] = {}  # path -> size in bytes

        # Memory limit
        max_mb = max_memory_mb or ThreadingConfig.CACHE_MAX_MEMORY_MB
        self._max_memory_bytes = max_mb * 1024 * 1024

        logger.debug(f"MemoryManager initialized with {max_mb}MB limit")

    def set_memory_limit(self, max_memory_mb: int) -> None:
        """Set maximum memory limit in megabytes.

        Args:
            max_memory_mb: Maximum memory limit in megabytes
        """
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        logger.debug(f"MemoryManager limit updated to {max_memory_mb}MB")

    def track_item(self, file_path: Path, size_bytes: int | None = None) -> bool:
        """Track a cached item's memory usage.

        Args:
            file_path: Path to the cached file
            size_bytes: File size in bytes. If None, will be determined from file.

        Returns:
            True if tracking succeeded, False otherwise
        """
        with self._lock:
            path_str = str(file_path)

            # Get file size if not provided
            if size_bytes is None:
                try:
                    size_bytes = file_path.stat().st_size
                except (OSError, IOError) as e:
                    logger.debug(f"Failed to get size for {file_path}: {e}")
                    return False

            # Update tracking
            old_size = self._cached_items.get(path_str, 0)
            self._cached_items[path_str] = size_bytes
            self._memory_usage_bytes += size_bytes - old_size

            logger.debug(
                f"Tracking item: {file_path.name} ({size_bytes / 1024:.1f}KB), "
                + f"total: {self._memory_usage_bytes / 1024 / 1024:.1f}MB"
            )

            return True

    def untrack_item(self, file_path: Path) -> bool:
        """Stop tracking a cached item's memory usage.

        Args:
            file_path: Path to the cached file to untrack

        Returns:
            True if item was untracked, False if not found
        """
        with self._lock:
            path_str = str(file_path)

            if path_str in self._cached_items:
                size = self._cached_items.pop(path_str)
                self._memory_usage_bytes = max(0, self._memory_usage_bytes - size)

                logger.debug(
                    f"Untracked item: {file_path.name} ({size / 1024:.1f}KB), "
                    + f"total: {self._memory_usage_bytes / 1024 / 1024:.1f}MB"
                )
                return True

            return False

    def is_item_tracked(self, file_path: Path) -> bool:
        """Check if a cached item is currently being tracked.

        Args:
            file_path: Path to the cached file to check

        Returns:
            True if item is tracked, False otherwise
        """
        with self._lock:
            return str(file_path) in self._cached_items

    def evict_if_needed(self, target_percent: float = 0.8) -> int:
        """Evict items if memory usage exceeds limit.

        Args:
            target_percent: Target memory usage as percent of limit (0.0-1.0)

        Returns:
            Number of items evicted
        """
        with self._lock:
            if self._memory_usage_bytes <= self._max_memory_bytes:
                return 0  # No eviction needed

            logger.info(
                f"Memory limit exceeded: {self._memory_usage_bytes / 1024 / 1024:.1f}MB "
                + f"/ {self._max_memory_bytes / 1024 / 1024:.1f}MB, starting eviction"
            )

            return self._evict_lru_items(target_percent)

    @property
    def memory_usage_bytes(self) -> int:
        """Get current memory usage in bytes."""
        with self._lock:
            return self._memory_usage_bytes

    @memory_usage_bytes.setter
    def memory_usage_bytes(self, value: int):
        """Set memory usage in bytes (for backward compatibility)."""
        with self._lock:
            self._memory_usage_bytes = value

    @property
    def max_memory_bytes(self) -> int:
        """Get maximum memory limit in bytes."""
        with self._lock:
            return self._max_memory_bytes

    @property
    def cached_items(self) -> dict[str, int]:
        """Get dictionary of cached items and their sizes."""
        with self._lock:
            return self._cached_items.copy()

    def get_usage_stats(self) -> dict[str, Any]:
        """Get current memory usage statistics.

        Returns:
            Dictionary with usage statistics
        """
        with self._lock:
            return {
                "total_bytes": self._memory_usage_bytes,
                "total_mb": self._memory_usage_bytes / 1024 / 1024,
                "max_mb": self._max_memory_bytes / 1024 / 1024,
                "usage_percent": (self._memory_usage_bytes / self._max_memory_bytes)
                * 100
                if self._max_memory_bytes > 0
                else 0,
                "tracked_items": len(self._cached_items),
                "average_item_kb": (
                    self._memory_usage_bytes / len(self._cached_items) / 1024
                )
                if self._cached_items
                else 0,
            }

    def is_over_limit(self) -> bool:
        """Check if memory usage is over the configured limit.

        Returns:
            True if over limit, False otherwise
        """
        with self._lock:
            return self._memory_usage_bytes > self._max_memory_bytes

    def clear_all_tracking(self) -> None:
        """Clear all memory tracking data.

        This resets the memory manager state but doesn't delete actual files.
        """
        with self._lock:
            count = len(self._cached_items)
            self._cached_items.clear()
            self._memory_usage_bytes = 0

            if count > 0:
                logger.info(f"Cleared tracking for {count} items")

    def validate_tracking(self) -> dict[str, Any]:
        """Validate tracking data against actual files.

        Returns:
            Dictionary with validation results
        """
        with self._lock:
            invalid_paths: list[str] = []
            size_mismatches: list[tuple[str, int, int]] = []
            total_actual_size = 0

            # Check each tracked item
            for path_str, tracked_size in list(self._cached_items.items()):
                path = Path(path_str)

                if not path.exists():
                    invalid_paths.append(path_str)
                else:
                    try:
                        actual_size = path.stat().st_size
                        total_actual_size += actual_size

                        if actual_size != tracked_size:
                            size_mismatches.append(
                                (path_str, actual_size, tracked_size)
                            )

                    except (OSError, IOError):
                        invalid_paths.append(path_str)

            # Remove invalid entries
            for path_str in invalid_paths:
                if path_str in self._cached_items:
                    size = self._cached_items.pop(path_str)
                    self._memory_usage_bytes = max(0, self._memory_usage_bytes - size)

            # Fix size mismatches
            for path_str, actual_size, tracked_size in size_mismatches:
                self._cached_items[path_str] = actual_size
                self._memory_usage_bytes += actual_size - tracked_size

            issues_fixed = len(invalid_paths) + len(size_mismatches)

            return {
                "valid": issues_fixed == 0,
                "issues_fixed": issues_fixed,
                "invalid_files": len(invalid_paths),
                "size_mismatches": len(size_mismatches),
                "tracked_usage_bytes": self._memory_usage_bytes,
                "actual_usage_bytes": total_actual_size,
                "tracked_items": len(self._cached_items),
            }

    def _evict_lru_items(self, target_percent: float) -> int:
        """Evict least recently used items until target usage is reached.

        Args:
            target_percent: Target memory usage as percent of limit

        Returns:
            Number of items evicted
        """
        target_bytes = int(self._max_memory_bytes * target_percent)
        evicted_count = 0

        # Get items sorted by modification time (oldest first)
        item_stats: list[tuple[str, int, float]] = []
        paths_to_remove: list[str] = []

        for path_str, size in list(self._cached_items.items()):
            try:
                path = Path(path_str)
                if path.exists():
                    mtime = path.stat().st_mtime
                    item_stats.append((path_str, size, mtime))
                else:
                    # File no longer exists, mark for removal
                    paths_to_remove.append(path_str)
            except (OSError, IOError):
                # Error accessing file, mark for removal
                paths_to_remove.append(path_str)

        # Remove non-existent files from tracking
        for path_str in paths_to_remove:
            if path_str in self._cached_items:
                size = self._cached_items.pop(path_str)
                self._memory_usage_bytes = max(0, self._memory_usage_bytes - size)
                evicted_count += 1

        # Sort by modification time (oldest first for LRU eviction)
        item_stats.sort(key=lambda x: x[2])

        # Evict oldest items until we reach target
        for path_str, size, _ in item_stats:
            if self._memory_usage_bytes <= target_bytes:
                break

            try:
                # Delete the actual file
                path = Path(path_str)
                path.unlink()

                # Remove from tracking
                if path_str in self._cached_items:
                    self._cached_items.pop(path_str)
                    self._memory_usage_bytes = max(0, self._memory_usage_bytes - size)
                    evicted_count += 1

                logger.debug(f"Evicted LRU item: {path.name} ({size / 1024:.1f}KB)")

            except (OSError, IOError) as e:
                logger.debug(f"Failed to evict item {path_str}: {e}")

        logger.info(
            f"Eviction complete: {evicted_count} items removed, "
            + f"usage: {self._memory_usage_bytes / 1024 / 1024:.1f}MB"
        )

        return evicted_count

    def __len__(self) -> int:
        """Return number of tracked items."""
        with self._lock:
            return len(self._cached_items)

    def __repr__(self) -> str:
        """String representation of memory manager."""
        stats = self.get_usage_stats()
        return (
            f"MemoryManager(items={stats['tracked_items']}, "
            f"usage={stats['total_mb']:.1f}MB, "
            f"limit={stats['max_mb']:.1f}MB)"
        )
