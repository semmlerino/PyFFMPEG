"""Shot data caching with TTL expiration."""

from __future__ import annotations

# Standard library imports
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

# Local application imports
from config import Config

from .storage_backend import StorageBackend

if TYPE_CHECKING:
    # Standard library imports
    from collections.abc import Sequence
    from pathlib import Path

    # Local application imports
    from shot_model import Shot
    from type_definitions import CacheDataDict, CacheInfoDict, ShotDict


logger = logging.getLogger(__name__)


class ShotCache:
    """Manages caching of shot data with TTL expiration.

    This class handles persistent caching of shot list data with automatic
    expiry checking and validation. It supports both Shot objects and
    dictionary representations for flexibility.
    """

    def __init__(
        self,
        cache_file: Path,
        storage_backend: StorageBackend | None = None,
        expiry_minutes: int | None = None,
    ) -> None:
        """Initialize shot cache.

        Args:
            cache_file: Path to the cache file
            storage_backend: Storage backend for file operations. If None, creates new one.
            expiry_minutes: Cache expiry time in minutes. If None, uses config default.
        """
        self._cache_file = cache_file
        self._storage = storage_backend or StorageBackend()
        self._expiry_minutes = expiry_minutes or Config.CACHE_EXPIRY_MINUTES

        logger.debug(f"ShotCache initialized with {self._expiry_minutes}min TTL")

    def set_expiry_minutes(self, expiry_minutes: int) -> None:
        """Set cache expiry time in minutes.

        Args:
            expiry_minutes: Cache expiry time in minutes
        """
        self._expiry_minutes = expiry_minutes
        logger.debug(f"ShotCache TTL updated to {expiry_minutes} minutes")

    def get_cached_shots(self) -> list[ShotDict] | None:
        """Get cached shot list if valid and not expired.

        Returns:
            List of shot dictionaries if cache is valid, None if expired or invalid
        """
        if not self._cache_file.exists():
            logger.debug("Shot cache file does not exist")
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

        shots_data = cache_data.get("shots", [])
        if not isinstance(shots_data, list):
            logger.warning("Invalid shot cache structure - shots is not a list")
            return None

        logger.debug(f"Loaded {len(shots_data)} shots from cache")
        return shots_data

    def cache_shots(self, shots: Sequence[Shot] | Sequence[ShotDict]) -> bool:
        """Cache shot list to persistent storage.

        Args:
            shots: List of Shot objects or dictionaries to cache

        Returns:
            True if caching succeeded, False otherwise
        """
        if shots is None:
            logger.warning("Attempted to cache None shots")
            return False

        try:
            # Convert to list of dictionaries
            shot_dicts = self._convert_shots_to_dicts(shots)

            # Create cache data structure
            cache_data: CacheDataDict = {
                "timestamp": datetime.now().isoformat(),
                "shots": shot_dicts,
                "metadata": {
                    "shot_count": len(shot_dicts),
                    "cached_at": datetime.now().isoformat(),
                    "expiry_minutes": self._expiry_minutes,
                },
            }

            # Write to cache
            if self._storage.write_json(self._cache_file, cache_data):
                logger.debug(f"Cached {len(shot_dicts)} shots to {self._cache_file}")
                return True
            else:
                logger.error(f"Failed to write shot cache to {self._cache_file}")
                return False

        except Exception as e:
            logger.exception(f"Unexpected error caching shots: {e}")
            return False

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
        """Get number of cached shots without loading full data.

        Returns:
            Number of cached shots, or 0 if no valid cache
        """
        if not self._cache_file.exists():
            return 0

        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return 0

        shots = cache_data.get("shots", [])
        return len(shots) if isinstance(shots, list) else 0

    def clear_cache(self) -> bool:
        """Clear the shot cache.

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
                "shot_count": 0,
                "age_seconds": None,
            }

        cache_data = self._storage.read_json(self._cache_file)
        if cache_data is None:
            return {
                "exists": True,
                "valid": False,
                "expired": True,
                "shot_count": 0,
                "age_seconds": None,
            }

        age = self.get_cache_age()
        is_valid = self._validate_cache_structure(cache_data)
        is_expired = self._is_expired(cache_data)

        return {
            "exists": True,
            "valid": is_valid,
            "expired": is_expired,
            "shot_count": self.get_cached_count(),
            "age_seconds": age.total_seconds() if age else None,
            "expiry_minutes": self._expiry_minutes,
            "timestamp": cache_data.get("timestamp"),
            "metadata": cache_data.get("metadata", {}),
        }

    def _validate_cache_structure(self, cache_data: CacheDataDict) -> bool:
        """Validate the structure of cached data.

        Args:
            cache_data: Cache data to validate

        Returns:
            True if structure is valid
        """
        if not isinstance(cache_data, dict):
            logger.warning("Cache data is not a dictionary")
            return False

        if "timestamp" not in cache_data:
            logger.warning("Invalid shot cache structure - missing timestamp")
            return False

        if "shots" not in cache_data:
            logger.warning("Invalid shot cache structure - missing shots")
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
            logger.debug("Shot cache: manual refresh mode, never expires")
            return False

        try:
            cache_time = datetime.fromisoformat(cache_data["timestamp"])
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Invalid timestamp in shot cache: {e}")
            return True

        age = datetime.now() - cache_time
        max_age = timedelta(minutes=self._expiry_minutes)

        is_expired = age > max_age
        if is_expired:
            logger.debug(f"Shot cache expired (age: {age})")

        return is_expired

    def _convert_shots_to_dicts(
        self, shots: Sequence[Shot] | Sequence[ShotDict]
    ) -> list[ShotDict]:
        """Convert shots to list of dictionaries.

        Args:
            shots: List of Shot objects or dictionaries

        Returns:
            List of shot dictionaries

        Raises:
            ValueError: If conversion fails
        """
        if not shots:
            return []

        if isinstance(shots[0], dict):
            # Already dictionaries
            return list(shots)  # type: ignore[return-value]
        else:
            # Convert Shot objects to dictionaries
            try:
                return [shot.to_dict() for shot in shots]  # type: ignore[attr-defined]
            except AttributeError as e:
                raise ValueError(f"Shot objects missing to_dict() method: {e}")

    def __repr__(self) -> str:
        """String representation of shot cache."""
        info = self.get_cache_info()
        return (
            f"ShotCache(file={self._cache_file.name}, "
            f"valid={info['valid']}, "
            f"expired={info['expired']}, "
            f"shots={info['shot_count']})"
        )
