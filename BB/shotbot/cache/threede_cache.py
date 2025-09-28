"""3DE scene data caching with metadata support."""

from __future__ import annotations

# Standard library imports
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

# Local application imports
from config import Config

from .storage_backend import StorageBackend

if TYPE_CHECKING:
    # Standard library imports
    from pathlib import Path

    # Local application imports
    from type_definitions import CacheDataDict, CacheInfoDict, ThreeDESceneDict

logger = logging.getLogger(__name__)


class ThreeDECache:
    """Manages caching of 3DE scene data with metadata and TTL expiration.

    This class handles persistent caching of 3DE scene discovery results
    with support for scan metadata, empty result caching, and automatic
    expiry checking. It properly handles valid empty caches to avoid
    redundant scanning.
    """

    def __init__(
        self,
        cache_file: Path,
        storage_backend: StorageBackend | None = None,
        expiry_minutes: int | None = None,
    ) -> None:
        """Initialize 3DE scene cache.

        Args:
            cache_file: Path to the cache file
            storage_backend: Storage backend for file operations. If None, creates new one.
            expiry_minutes: Cache expiry time in minutes. If None, uses config default.
        """
        self._cache_file = cache_file
        self._storage = storage_backend or StorageBackend()
        self._expiry_minutes = expiry_minutes or Config.CACHE_EXPIRY_MINUTES

        logger.debug(f"ThreeDECache initialized with {self._expiry_minutes}min TTL")

    def set_expiry_minutes(self, expiry_minutes: int) -> None:
        """Set cache expiry time in minutes.

        Args:
            expiry_minutes: Cache expiry time in minutes
        """
        self._expiry_minutes = expiry_minutes
        logger.debug(f"ThreeDECache TTL updated to {expiry_minutes} minutes")

    def get_cached_scenes(self) -> list[ThreeDESceneDict] | None:
        """Get cached 3DE scene list if valid and not expired.

        Returns:
            List of scene dictionaries if cache is valid, None if expired or invalid
        """
        if not self._cache_file.exists():
            logger.debug("3DE scene cache file does not exist")
            return None

        # Read cache data
        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return None

        # Check expiry
        if self._is_expired(cache_data):
            return None

        scenes = cache_data.get("scenes", [])
        if not isinstance(scenes, list):
            logger.warning("Invalid 3DE cache structure - scenes is not a list")
            return None

        logger.debug(f"Loaded {len(scenes)} 3DE scenes from cache")
        return scenes

    def cache_scenes(
        self,
        scenes: list[ThreeDESceneDict],
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Cache 3DE scene list with optional scan metadata.

        Args:
            scenes: List of scene dictionaries to cache
            metadata: metadata about the scan operation

        Returns:
            True if caching succeeded, False otherwise
        """
        try:
            # Create default metadata if not provided
            if metadata is None:
                metadata = {
                    "scan_type": "full" if scenes else "empty",
                    "scene_count": len(scenes),
                    "cached_at": datetime.now().isoformat(),
                }

            # Create cache data structure
            cache_data: CacheDataDict = {
                "timestamp": datetime.now().isoformat(),
                "scenes": scenes,
                "metadata": metadata,
            }

            # Write to cache
            if self._storage.write_json(self._cache_file, cache_data):
                logger.debug(f"Cached {len(scenes)} 3DE scenes with metadata")
                return True
            else:
                logger.error(f"Failed to write 3DE cache to {self._cache_file}")
                return False

        except Exception as e:
            logger.exception(f"Unexpected error caching 3DE scenes: {e}")
            return False

    def has_valid_cache(self) -> bool:
        """Check if we have a valid cache (including valid empty results).

        This method checks cache validity without loading the full data,
        which is important for determining if a scan is needed.

        Returns:
            True if cache exists and is not expired (even if empty), False otherwise
        """
        if not self._cache_file.exists():
            logger.debug("3DE scene cache file not found")
            return False

        # Read just the timestamp for validation
        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return False

        # Check if cache is expired
        if self._is_expired(cache_data):
            return False

        # Cache is valid (even if scenes list is empty)
        scene_count = len(cache_data.get("scenes", []))
        age = self.get_cache_age()
        age_minutes = age.total_seconds() / 60 if age else 0

        logger.debug(
            f"3DE cache is valid (age: {age_minutes:.1f}min, scenes: {scene_count})"
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
        """Get number of cached scenes without loading full data.

        Returns:
            Number of cached scenes, or 0 if no valid cache
        """
        if not self._cache_file.exists():
            return 0

        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return 0

        scenes = cache_data.get("scenes", [])
        return len(scenes) if isinstance(scenes, list) else 0

    def get_cache_metadata(self) -> dict[str, Any] | None:
        """Get cache metadata without loading scene data.

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
        """Clear the 3DE scene cache.

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
                "scene_count": 0,
                "age_seconds": None,
                "metadata": {},
            }

        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return {
                "exists": True,
                "valid": False,
                "expired": True,
                "scene_count": 0,
                "age_seconds": None,
                "metadata": {},
            }

        age = self.get_cache_age()
        is_expired = self._is_expired(cache_data)

        return {
            "exists": True,
            "valid": not is_expired,
            "expired": is_expired,
            "scene_count": self.get_cached_count(),
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

        max_age = max_age_minutes or (self._expiry_minutes // 2)
        return age > timedelta(minutes=max_age)

    def _is_expired(self, cache_data: CacheDataDict) -> bool:
        """Check if cached data is expired.

        Args:
            cache_data: Cache data to check

        Returns:
            True if expired, False if still valid
        """
        # If expiry_minutes is 0, never expire (manual refresh only)
        if self._expiry_minutes == 0:
            logger.debug("3DE cache: manual refresh mode, never expires")
            return False

        try:
            cache_time = datetime.fromisoformat(
                cache_data.get("timestamp", "1970-01-01")
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid timestamp in 3DE cache: {e}")
            return True

        age = datetime.now() - cache_time
        max_age = timedelta(minutes=self._expiry_minutes)

        is_expired = age > max_age
        if is_expired:
            logger.debug(f"3DE cache expired (age: {age})")

        return is_expired

    def __repr__(self) -> str:
        """String representation of 3DE cache."""
        info = self.get_cache_info()
        return (
            f"ThreeDECache(file={self._cache_file.name}, "
            f"valid={info['valid']}, "
            f"expired={info['expired']}, "
            f"scenes={info['scene_count']})"
        )
