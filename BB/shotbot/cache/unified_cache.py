"""Unified TTL-based cache for any data type (replaces shot_cache + threede_cache).

This module provides a generic TTL (Time To Live) cache implementation that
can handle any data type, eliminating the duplication between ShotCache and
ThreeDECache. It uses TypeVar for type safety while providing a single
implementation for all TTL caching needs.
"""

from __future__ import annotations

from collections.abc import Sequence

# Standard library imports
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Generic, TypeVar, Union

# Local application imports
from config import Config
from logging_mixin import LoggingMixin

from .storage_backend import StorageBackend

if TYPE_CHECKING:
    # Standard library imports
    from pathlib import Path

    # Local application imports
    from type_definitions import CacheDataDict, CacheInfoDict
    from base_shot_model import Shot
    from threede_scene_model import ThreeDEScene

# Type variable for cached data
T = TypeVar("T")

# Type alias for data that can be cached
CacheableData = Union[dict[str, Any], "Shot", "ThreeDEScene"]


class UnifiedCache(LoggingMixin, Generic[T]):
    """Generic TTL-based cache for any data type.

    This class unifies the functionality of ShotCache and ThreeDECache by
    providing a generic implementation that works with any data type. It
    supports automatic TTL expiration, metadata storage, and conversion
    between objects and dictionaries.

    Type Examples:
        UnifiedCache[Shot] - for caching Shot objects
        UnifiedCache[ThreeDEScene] - for caching ThreeDEScene objects
        UnifiedCache[dict] - for caching dictionary data
    """

    def __init__(
        self,
        cache_file: Path,
        data_key: str,
        storage_backend: StorageBackend | None = None,
        expiry_minutes: int | None = None,
        item_count_key: str | None = None,
    ) -> None:
        """Initialize unified cache.

        Args:
            cache_file: Path to the cache file
            data_key: Key name for data in cache (e.g., "shots", "scenes")
            storage_backend: Storage backend for file operations. If None, creates new one.
            expiry_minutes: Cache expiry time in minutes. If None, uses config default.
            item_count_key: Key name for count in metadata (e.g., "shot_count", "scene_count")
        """
        super().__init__()
        self._cache_file = cache_file
        self._data_key = data_key
        self._storage = storage_backend or StorageBackend()
        self._expiry_minutes = expiry_minutes or Config.CACHE_EXPIRY_MINUTES
        self._item_count_key = (
            item_count_key or f"{data_key[:-1]}_count"
        )  # shots -> shot_count

        self.logger.debug(
            f"UnifiedCache[{self._data_key}] initialized with {self._expiry_minutes}min TTL"
        )

    def set_expiry_minutes(self, expiry_minutes: int) -> None:
        """Set cache expiry time in minutes.

        Args:
            expiry_minutes: Cache expiry time in minutes
        """
        self._expiry_minutes = expiry_minutes
        self.logger.debug(
            f"UnifiedCache[{self._data_key}] TTL updated to {expiry_minutes} minutes"
        )

    def get_cached_data(self) -> list[dict[str, Any]] | None:
        """Get cached data if valid and not expired.

        Returns:
            List of data dictionaries if cache is valid, None if expired or invalid
        """
        if not self._cache_file.exists():
            self.logger.debug(f"Cache file does not exist: {self._cache_file}")
            return None

        # Read cache data
        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return None

        # Validate cache structure
        if not self._validate_cache_structure(cache_data):
            return None

        # Check expiry
        if self._is_expired(cache_data):
            return None

        cached_items = cache_data.get(self._data_key, [])
        if not isinstance(cached_items, list):
            self.logger.warning(
                f"Invalid cache structure - {self._data_key} is not a list"
            )
            return None

        self.logger.debug(f"Loaded {len(cached_items)} items from cache")
        return cached_items

    def cache_data(
        self,
        items: Sequence[T] | Sequence[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Cache data to persistent storage.

        Args:
            items: List of objects or dictionaries to cache
            metadata: Optional metadata about the cached data

        Returns:
            True if caching succeeded, False otherwise
        """
        if items is None:
            self.logger.warning(f"Attempted to cache None {self._data_key}")
            return False

        try:
            # Convert to list of dictionaries
            item_dicts = self._convert_items_to_dicts(items)

            # Create default metadata if not provided
            if metadata is None:
                metadata = {
                    self._item_count_key: len(item_dicts),
                    "cached_at": datetime.now().isoformat(),
                    "expiry_minutes": self._expiry_minutes,
                }
            else:
                # Ensure count and timestamp are included
                metadata.update(
                    {
                        self._item_count_key: len(item_dicts),
                        "cached_at": datetime.now().isoformat(),
                    }
                )

            # Create cache data structure
            cache_data: CacheDataDict = {
                "timestamp": datetime.now().isoformat(),
                self._data_key: item_dicts,
                "metadata": metadata,
            }

            # Write to cache
            if self._storage.write_json(self._cache_file, cache_data):
                self.logger.debug(
                    f"Cached {len(item_dicts)} {self._data_key} to {self._cache_file}"
                )
                return True
            else:
                self.logger.error(f"Failed to write cache to {self._cache_file}")
                return False

        except Exception as e:
            self.logger.exception(f"Unexpected error caching {self._data_key}: {e}")
            return False

    def has_valid_cache(self) -> bool:
        """Check if we have a valid cache (including valid empty results).

        This method checks cache validity without loading the full data,
        which is important for determining if a refresh is needed.

        Returns:
            True if cache exists and is not expired (even if empty), False otherwise
        """
        if not self._cache_file.exists():
            self.logger.debug(f"Cache file not found: {self._cache_file}")
            return False

        # Read just the timestamp for validation
        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return False

        # Check if cache is expired
        if self._is_expired(cache_data):
            return False

        # Cache is valid (even if data list is empty)
        item_count = len(cache_data.get(self._data_key, []))
        age = self.get_cache_age()
        age_minutes = age.total_seconds() / 60 if age else 0

        self.logger.debug(
            f"Cache is valid (age: {age_minutes:.1f}min, items: {item_count})"
        )
        return True

    def is_expired(self) -> bool:
        """Check if the cache is expired without loading data.

        Returns:
            True if cache is expired or doesn't exist, False if valid
        """
        if not self._cache_file.exists():
            return True

        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return True

        return self._is_expired(cache_data)

    def get_cache_age(self) -> timedelta | None:
        """Get the age of the cached data.

        Returns:
            Age of cache as timedelta, or None if no valid cache
        """
        if not self._cache_file.exists():
            return None

        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return None

        try:
            cache_time = datetime.fromisoformat(
                cache_data.get("timestamp", "1970-01-01")
            )
            return datetime.now() - cache_time
        except (ValueError, TypeError):
            return None

    def get_cached_count(self) -> int:
        """Get number of cached items without loading full data.

        Returns:
            Number of cached items, or 0 if no valid cache
        """
        if not self._cache_file.exists():
            return 0

        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return 0

        items = cache_data.get(self._data_key, [])
        return len(items) if isinstance(items, list) else 0

    def get_cache_metadata(self) -> dict[str, Any] | None:
        """Get cache metadata without loading item data.

        Returns:
            Metadata dictionary, or None if no valid cache
        """
        if not self._cache_file.exists():
            return None

        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return None

        return cache_data.get("metadata", {})

    def clear_cache(self) -> bool:
        """Clear the cache.

        Returns:
            True if cache was cleared successfully
        """
        return self._storage.delete_file(self._cache_file)

    def get_cache_info(self) -> CacheInfoDict:
        """Get detailed cache information for debugging.

        Returns:
            Dictionary with cache status and metadata
        """
        if not self._cache_file.exists():
            return {
                "exists": False,
                "valid": False,
                "expired": True,
                self._item_count_key: 0,
                "age_seconds": None,
                "metadata": {},
            }

        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return {
                "exists": True,
                "valid": False,
                "expired": True,
                self._item_count_key: 0,
                "age_seconds": None,
                "metadata": {},
            }

        age = self.get_cache_age()
        is_valid = self._validate_cache_structure(cache_data)
        is_expired = self._is_expired(cache_data)

        return {
            "exists": True,
            "valid": is_valid,
            "expired": is_expired,
            self._item_count_key: self.get_cached_count(),
            "age_seconds": age.total_seconds() if age else None,
            "expiry_minutes": self._expiry_minutes,
            "timestamp": cache_data.get("timestamp"),
            "metadata": cache_data.get("metadata", {}),
        }

    def force_refresh_needed(self, max_age_minutes: int | None = None) -> bool:
        """Check if cache should be force refreshed based on age.

        Args:
            max_age_minutes: Maximum age before forcing refresh. If None, uses half of expiry time.

        Returns:
            True if cache should be refreshed even if not expired
        """
        age = self.get_cache_age()
        if age is None:
            return True  # No cache, needs refresh

        # Handle max_age_minutes=0 case (immediate refresh needed)
        if max_age_minutes is not None:
            max_age = max_age_minutes
        else:
            max_age = self._expiry_minutes // 2

        return age > timedelta(minutes=max_age)

    def _validate_cache_structure(self, cache_data: CacheDataDict) -> bool:
        """Validate the structure of cached data.

        Args:
            cache_data: Cache data to validate

        Returns:
            True if structure is valid
        """
        if not isinstance(cache_data, dict):
            self.logger.warning("Cache data is not a dictionary")
            return False

        if "timestamp" not in cache_data:
            self.logger.warning("Invalid cache structure - missing timestamp")
            return False

        if self._data_key not in cache_data:
            self.logger.warning(f"Invalid cache structure - missing {self._data_key}")
            return False

        return True

    def _is_expired(self, cache_data: CacheDataDict) -> bool:
        """Check if cached data is expired.

        Args:
            cache_data: Cache data to check

        Returns:
            True if expired, False if still valid
        """
        # If expiry_minutes is 0, never expire (manual refresh only)
        if self._expiry_minutes == 0:
            self.logger.debug("Cache: manual refresh mode, never expires")
            return False

        try:
            cache_time = datetime.fromisoformat(cache_data["timestamp"])
        except (ValueError, TypeError, KeyError) as e:
            self.logger.warning(f"Invalid timestamp in cache: {e}")
            return True

        age = datetime.now() - cache_time
        max_age = timedelta(minutes=self._expiry_minutes)

        is_expired = age > max_age
        if is_expired:
            self.logger.debug(f"Cache expired (age: {age})")

        return is_expired

    def _convert_items_to_dicts(
        self, items: Sequence[T] | Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert items to list of dictionaries.

        Args:
            items: List of objects or dictionaries

        Returns:
            List of dictionaries

        Raises:
            ValueError: If conversion fails
        """
        if not items:
            return []

        # Check first item to determine type
        first_item = items[0]

        if isinstance(first_item, dict):
            # Already dictionaries
            return list(items)  # type: ignore[return-value]
        else:
            # Convert objects to dictionaries
            try:
                return [item.to_dict() for item in items]  # type: ignore[attr-defined]
            except AttributeError as e:
                raise ValueError(f"Objects missing to_dict() method: {e}")

    def __repr__(self) -> str:
        """String representation of unified cache."""
        info = self.get_cache_info()
        return (
            f"UnifiedCache[{self._data_key}](file={self._cache_file.name}, "
            f"valid={info['valid']}, "
            f"expired={info['expired']}, "
            f"items={info.get(self._item_count_key, 0)})"
        )


# ============= Factory functions for backward compatibility =============


def create_shot_cache(
    cache_file: Path,
    storage_backend: StorageBackend | None = None,
    expiry_minutes: int | None = None,
) -> UnifiedCache[Any]:
    """Factory function to create a shot cache using unified implementation.

    This provides backward compatibility with the original ShotCache interface.
    """
    return UnifiedCache(
        cache_file=cache_file,
        data_key="shots",
        storage_backend=storage_backend,
        expiry_minutes=expiry_minutes,
        item_count_key="shot_count",
    )


def create_threede_cache(
    cache_file: Path,
    storage_backend: StorageBackend | None = None,
    expiry_minutes: int | None = None,
) -> UnifiedCache[Any]:
    """Factory function to create a 3DE scene cache using unified implementation.

    This provides backward compatibility with the original ThreeDECache interface.
    """
    return UnifiedCache(
        cache_file=cache_file,
        data_key="scenes",
        storage_backend=storage_backend,
        expiry_minutes=expiry_minutes,
        item_count_key="scene_count",
    )
