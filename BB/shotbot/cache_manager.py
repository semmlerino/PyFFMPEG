"""Simplified cache manager for shot data and thumbnails.

This is a streamlined replacement for the complex cache architecture,
designed for a local VFX tool on a secure network.

Simplifications:
- No platform-specific file locking (basic QMutex only)
- No memory manager/LRU eviction
- No failure tracker with exponential backoff
- No storage backend abstraction
- Direct PIL/OpenEXR processing
- Simple atomic writes (temp file + os.replace)
- Fixed 30-minute TTL

Maintained features:
- All public API methods (backward compatible)
- Thumbnail caching (get_cached_thumbnail, cache_thumbnail)
- Shot/3DE/Previous shots data caching
- OpenEXR support (VFX requirement)
- Directory structure
- Thread safety (basic QMutex)
"""

from __future__ import annotations

# Standard library imports
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias, cast

# Third-party imports
from PIL import Image
from PySide6.QtCore import QMutex, QMutexLocker, QObject, Qt, Signal

# Local application imports
from exceptions import ThumbnailError
from logging_mixin import LoggingMixin

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PySide6.QtGui import QImage

    from shot_model import Shot
    from type_definitions import ShotDict, ThreeDESceneDict

# These are used at runtime in cast() with string literals, but also needed for type annotations
import contextlib

# Type alias for JSON data (used for runtime validation) - Python 3.11 compatible
JSONValue: TypeAlias = (
    dict[str, "JSONValue"] | list["JSONValue"] | str | int | float | bool | None
)

# Constants
DEFAULT_TTL_MINUTES = 30
THUMBNAIL_SIZE = 256
THUMBNAIL_QUALITY = 85


# Backward compatibility exports from old cache system
class ThumbnailCacheResult:
    """Stub for backward compatibility - no longer used in simplified implementation."""

    def __init__(self) -> None:
        super().__init__()
        self.future = None
        self.path = None
        self.is_complete = False


class ThumbnailCacheLoader:
    """Stub for backward compatibility - no longer used in simplified implementation."""


class CacheManager(LoggingMixin, QObject):
    """Simplified cache manager for local VFX tool.

    Provides same public API as CacheManager but with simpler implementation.
    """

    # Signals - maintain backward compatibility
    cache_updated = Signal()

    def __init__(
        self,
        cache_dir: Path | None = None,
        settings_manager: object | None = None,  # Ignored for simplicity
    ) -> None:
        """Initialize simplified cache manager.

        Args:
            cache_dir: Cache directory path. If None, uses mode-appropriate default
            settings_manager: Ignored in simplified implementation
        """
        super().__init__()

        # Thread safety
        self._lock = QMutex()

        # Setup cache directory
        if cache_dir is None:
            # Standard library imports
            import sys

            # Use default cache location based on mode
            # Detect pytest automatically (takes highest priority)
            is_pytest = "pytest" in sys.modules

            if is_pytest or os.getenv("SHOTBOT_MODE") == "test":
                cache_dir = Path.home() / ".shotbot" / "cache_test"
            elif os.getenv("SHOTBOT_MODE") == "mock":
                cache_dir = Path.home() / ".shotbot" / "cache" / "mock"
            else:
                cache_dir = Path.home() / ".shotbot" / "cache" / "production"
        self.cache_dir = Path(cache_dir)
        self.thumbnails_dir = self.cache_dir / "thumbnails"
        self.shots_cache_file = self.cache_dir / "shots.json"
        self.previous_shots_cache_file = self.cache_dir / "previous_shots.json"
        self.threede_cache_file = self.cache_dir / "threede_scenes.json"

        # TTL configuration
        self._cache_ttl = timedelta(minutes=DEFAULT_TTL_MINUTES)

        # Ensure directories exist
        self._ensure_cache_dirs()

        self.logger.info(f"SimpleCacheManager initialized: {self.cache_dir}")

    def _ensure_cache_dirs(self) -> None:
        """Ensure cache directories exist."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Ensured cache directory: {self.cache_dir}")
        except Exception as e:
            self.logger.error(f"Failed to create cache directories: {e}")

    def ensure_cache_directory(self) -> bool:
        """Ensure cache directory exists.

        Returns:
            True if successful
        """
        try:
            self._ensure_cache_dirs()
            return True
        except Exception:
            return False

    # ========================================================================
    # Thumbnail Caching Methods
    # ========================================================================

    def get_cached_thumbnail(self, show: str, sequence: str, shot: str) -> Path | None:
        """Get path to cached thumbnail if it exists and is valid.

        Args:
            show: Show name
            sequence: Sequence name
            shot: Shot name

        Returns:
            Path to thumbnail or None if not cached/expired
        """
        with QMutexLocker(self._lock):
            cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"

            if not cache_path.exists():
                return None

            # Check TTL
            try:
                age = datetime.now() - datetime.fromtimestamp(
                    cache_path.stat().st_mtime
                )
                if age > self._cache_ttl:
                    self.logger.debug(f"Thumbnail expired: {cache_path}")
                    return None
            except Exception as e:
                self.logger.warning(f"Failed to check thumbnail age: {e}")
                return None

            return cache_path

    def cache_thumbnail(
        self,
        source_path: str | Path,
        show: str,
        sequence: str,
        shot: str,
        wait: bool = True,
        timeout: float | None = None,
    ) -> Path | None:
        """Cache a thumbnail from source path.

        Args:
            source_path: Source image path
            show: Show name
            sequence: Sequence name
            shot: Shot name
            wait: Ignored in simplified implementation (always synchronous)
            timeout: Ignored in simplified implementation

        Returns:
            Path to cached thumbnail or None on error
        """
        source_path_obj = (
            Path(source_path) if isinstance(source_path, str) else source_path
        )

        # Validate parameters
        if not all([show, sequence, shot]):
            error_msg = "Missing required parameters for thumbnail caching"
            self.logger.error(error_msg)
            raise ThumbnailError(
                error_msg,
                details={
                    "source_path": str(source_path),
                    "show": show,
                    "sequence": sequence,
                    "shot": shot,
                },
            )

        if not source_path_obj.exists():
            self.logger.warning(f"Source path does not exist: {source_path_obj}")
            return None

        with QMutexLocker(self._lock):
            # Create output directory
            output_dir = self.thumbnails_dir / show / sequence
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError) as e:
                self.logger.error(f"Failed to create cache directories: {e}")
                return None
            output_path = output_dir / f"{shot}_thumb.jpg"

            # Already cached and valid?
            if output_path.exists():
                try:
                    age = datetime.now() - datetime.fromtimestamp(
                        output_path.stat().st_mtime
                    )
                    if age < self._cache_ttl:
                        self.logger.debug(f"Using existing thumbnail: {output_path}")
                        return output_path
                except Exception:
                    pass  # Regenerate if we can't check age

            # Detect file type and route to appropriate processor
            is_exr = source_path_obj.suffix.lower() in (".exr", ".EXR")

            try:
                if is_exr:
                    return self._process_exr_thumbnail(source_path_obj, output_path)
                return self._process_standard_thumbnail(source_path_obj, output_path)
            except Exception as e:
                self.logger.error(f"Failed to process thumbnail: {e}")
                return None

    def _process_standard_thumbnail(self, source: Path, output: Path) -> Path:
        """Process standard image formats to thumbnail.

        Args:
            source: Source image path
            output: Output thumbnail path

        Returns:
            Path to created thumbnail
        """
        try:
            img = Image.open(source)
            img.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.Resampling.LANCZOS)
            img.convert("RGB").save(output, "JPEG", quality=THUMBNAIL_QUALITY)
            self.logger.debug(f"Created thumbnail: {output}")
            return output
        except Exception as e:
            self.logger.error(f"PIL thumbnail processing failed: {e}")
            raise ThumbnailError(f"Failed to process thumbnail: {e}") from e

    def _process_exr_thumbnail(self, source: Path, output: Path) -> Path:
        """Process OpenEXR image to thumbnail.

        Args:
            source: Source EXR path
            output: Output thumbnail path

        Returns:
            Path to created thumbnail
        """
        try:
            import Imath
            import numpy as np
            import OpenEXR

            # Open EXR file
            exr_file = OpenEXR.InputFile(str(source))  # type: ignore[attr-defined]
            header = exr_file.header()  # type: ignore[attr-defined]

            # Get image dimensions
            dw = header["dataWindow"]  # type: ignore[index]
            width: int = dw.max.x - dw.min.x + 1  # type: ignore[attr-defined]
            height: int = dw.max.y - dw.min.y + 1  # type: ignore[attr-defined]

            # Read RGB channels (or use first available channel if no RGB)
            channels = header["channels"]  # type: ignore[index]
            channel_names: list[str] = list(channels.keys())  # type: ignore[attr-defined]

            # Try to find RGB channels (common names: R/G/B, Y/RY/BY, etc.)
            r_channel: str = next(
                (ch for ch in channel_names if ch in ("R", "r", "red", "Red")),
                channel_names[0],
            )
            g_channel: str = next(
                (ch for ch in channel_names if ch in ("G", "g", "green", "Green")),
                r_channel,
            )
            b_channel: str = next(
                (ch for ch in channel_names if ch in ("B", "b", "blue", "Blue")),
                r_channel,
            )

            # Read channel data
            FLOAT = Imath.PixelType(Imath.PixelType.FLOAT)
            r_str = exr_file.channel(r_channel, FLOAT)  # type: ignore[attr-defined]
            g_str = exr_file.channel(g_channel, FLOAT)  # type: ignore[attr-defined]
            b_str = exr_file.channel(b_channel, FLOAT)  # type: ignore[attr-defined]

            # Convert to numpy arrays
            r = np.frombuffer(r_str, dtype=np.float32).reshape(height, width)  # type: ignore[arg-type]
            g = np.frombuffer(g_str, dtype=np.float32).reshape(height, width)  # type: ignore[arg-type]
            b = np.frombuffer(b_str, dtype=np.float32).reshape(height, width)  # type: ignore[arg-type]

            # Stack into RGB image and apply simple tone mapping
            rgb = np.dstack((r, g, b))

            # Simple tone mapping: clamp and convert to 8-bit
            rgb = np.clip(rgb, 0, 1)
            rgb_8bit = (rgb * 255).astype(np.uint8)

            # Convert to PIL Image
            img = Image.fromarray(rgb_8bit, mode="RGB")
            img.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.Resampling.LANCZOS)
            img.save(output, "JPEG", quality=THUMBNAIL_QUALITY)

            self.logger.debug(f"Created EXR thumbnail: {output}")
            return output

        except Exception as e:
            self.logger.error(f"OpenEXR thumbnail processing failed: {e}")
            raise ThumbnailError(f"Failed to process EXR thumbnail: {e}") from e

    def cache_thumbnail_direct(
        self,
        image: QImage,
        show: str,
        sequence: str,
        shot: str,
    ) -> Path | None:
        """Cache a thumbnail from QImage directly.

        Args:
            image: QImage to cache
            show: Show name
            sequence: Sequence name
            shot: Shot name

        Returns:
            Path to cached thumbnail or None on error
        """
        with QMutexLocker(self._lock):
            output_dir = self.thumbnails_dir / show / sequence
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{shot}_thumb.jpg"

            try:
                # Scale if needed
                if image.width() > THUMBNAIL_SIZE or image.height() > THUMBNAIL_SIZE:
                    image = image.scaled(
                        THUMBNAIL_SIZE,
                        THUMBNAIL_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )

                # Save - QImage.save() accepts str or bytes for format parameter
                if image.save(str(output_path), b"JPEG", THUMBNAIL_QUALITY):
                    self.logger.debug(f"Cached QImage thumbnail: {output_path}")
                    return output_path
                self.logger.error(f"Failed to save QImage to: {output_path}")
                return None

            except Exception as e:
                self.logger.error(f"QImage thumbnail caching failed: {e}")
                return None

    # ========================================================================
    # Shot Data Caching Methods
    # ========================================================================

    def get_cached_shots(self) -> list[ShotDict] | None:
        """Get cached shot list if valid.

        Returns:
            List of shot dictionaries or None if not cached/expired
        """
        return self._read_json_cache(self.shots_cache_file)

    def cache_shots(self, shots: Sequence[Shot] | Sequence[ShotDict]) -> None:
        """Cache shot list to file.

        Args:
            shots: Sequence of Shot objects or shot dictionaries
        """
        # Convert Shot objects to dicts
        shot_dicts: list[ShotDict] = []
        for shot in shots:
            if isinstance(shot, dict):
                shot_dicts.append(shot)
            else:
                # Assume Shot object with to_dict method - TYPE_CHECKING import prevents runtime check
                shot_dicts.append(shot.to_dict())

        self._write_json_cache(self.shots_cache_file, shot_dicts)
        self.cache_updated.emit()

    def get_cached_previous_shots(self) -> list[ShotDict] | None:
        """Get cached previous/approved shot list if valid.

        Returns:
            List of shot dictionaries or None if not cached/expired
        """
        return self._read_json_cache(self.previous_shots_cache_file)

    def get_persistent_previous_shots(self) -> list[ShotDict] | None:
        """Get cached previous/approved shot list without TTL expiration.

        This method returns the cached previous shots regardless of age,
        implementing persistent incremental caching where shots accumulate
        over time without expiration.

        Returns:
            List of shot dictionaries or None if not cached
        """
        return self._read_json_cache(self.previous_shots_cache_file, check_ttl=False)

    def cache_previous_shots(self, shots: Sequence[Shot] | Sequence[ShotDict]) -> None:
        """Cache previous/approved shot list to file.

        Args:
            shots: Sequence of Shot objects or shot dictionaries
        """
        shot_dicts: list[ShotDict] = []
        for shot in shots:
            if isinstance(shot, dict):
                shot_dicts.append(shot)
            else:
                # Assume Shot object with to_dict method - TYPE_CHECKING import prevents runtime check
                shot_dicts.append(shot.to_dict())

        self._write_json_cache(self.previous_shots_cache_file, shot_dicts)
        self.cache_updated.emit()

    def get_cached_threede_scenes(self) -> list[ThreeDESceneDict] | None:
        """Get cached 3DE scene list if valid.

        Returns:
            List of scene dictionaries or None if not cached/expired
        """
        result = self._read_json_cache(self.threede_cache_file)
        # Type narrowing: the cache file contains ThreeDESceneDict when written by cache_threede_scenes
        # Runtime validation ensures this is safe
        return cast("list[ThreeDESceneDict] | None", result)

    def has_valid_threede_cache(self) -> bool:
        """Check if we have a valid 3DE cache.

        Returns:
            True if cache exists and is valid
        """
        cached = self.get_cached_threede_scenes()
        return cached is not None

    def cache_threede_scenes(
        self,
        scenes: list[ThreeDESceneDict],
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Cache 3DE scene list to file.

        Args:
            scenes: List of scene dictionaries
            metadata: Optional metadata (ignored in simple implementation)
        """
        self._write_json_cache(self.threede_cache_file, scenes)
        self.cache_updated.emit()

    # ========================================================================
    # Generic Data Caching Methods (backward compatibility)
    # ========================================================================

    def cache_data(self, key: str, data: object) -> None:
        """Cache generic data with a key.

        Args:
            key: Cache key identifier
            data: Data to cache
        """
        if key == "previous_shots":
            # Runtime validation: data must be a sequence of shots or dicts
            if isinstance(data, list | tuple):
                self.cache_previous_shots(
                    cast("Sequence[Shot] | Sequence[ShotDict]", data)
                )
            else:
                self.logger.error(f"Invalid data type for previous_shots: {type(data)}")
        else:
            cache_file = self.cache_dir / f"{key}.json"
            self._write_json_cache(cache_file, data)

    def get_cached_data(self, key: str) -> object | None:
        """Get cached generic data by key.

        Args:
            key: Cache key identifier

        Returns:
            Cached data or None if not found/expired
        """
        if key == "previous_shots":
            return self.get_cached_previous_shots()
        cache_file = self.cache_dir / f"{key}.json"
        return self._read_json_cache(cache_file)

    def clear_cached_data(self, key: str) -> None:
        """Clear cached generic data by key.

        Args:
            key: Cache key identifier
        """
        if key == "previous_shots":
            if self.previous_shots_cache_file.exists():
                self.previous_shots_cache_file.unlink()
        else:
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                cache_file.unlink()

    # ========================================================================
    # Cache Management Methods
    # ========================================================================

    def clear_cache(self) -> None:
        """Clear all cached data."""
        with QMutexLocker(self._lock):
            try:
                # Clear JSON caches
                for cache_file in [
                    self.shots_cache_file,
                    self.previous_shots_cache_file,
                    self.threede_cache_file,
                ]:
                    if cache_file.exists():
                        cache_file.unlink()

                # Clear thumbnails
                if self.thumbnails_dir.exists():
                    shutil.rmtree(self.thumbnails_dir)
                    self.thumbnails_dir.mkdir(parents=True, exist_ok=True)

                self.logger.info("Cache cleared successfully")
                self.cache_updated.emit()

            except Exception as e:
                self.logger.error(f"Failed to clear cache: {e}")

    def get_memory_usage(self) -> dict[str, float | int | str]:
        """Get cache memory usage statistics.

        Returns:
            Dictionary with cache size information
        """
        try:
            total_size = 0
            file_count = 0
            thumbnail_count = 0

            # Count thumbnails
            if self.thumbnails_dir.exists():
                for item in self.thumbnails_dir.rglob("*"):
                    if item.is_file():
                        total_size += item.stat().st_size
                        file_count += 1
                        thumbnail_count += 1

            # Count JSON files
            for cache_file in [
                self.shots_cache_file,
                self.previous_shots_cache_file,
                self.threede_cache_file,
            ]:
                if cache_file.exists():
                    total_size += cache_file.stat().st_size
                    file_count += 1

            return {
                "total_mb": total_size / (1024 * 1024),
                "file_count": file_count,
                "thumbnail_count": thumbnail_count,
                "thumbnail_dir": str(self.thumbnails_dir),
            }

        except Exception as e:
            self.logger.error(f"Failed to get memory usage: {e}")
            return {"total_mb": 0.0, "file_count": 0, "thumbnail_count": 0}

    # ========================================================================
    # Configuration Properties (backward compatibility)
    # ========================================================================

    @property
    def CACHE_THUMBNAIL_SIZE(self) -> int:
        """Get the cached thumbnail size."""
        return THUMBNAIL_SIZE

    @property
    def CACHE_EXPIRY_MINUTES(self) -> int:
        """Get cache expiry time in minutes."""
        return DEFAULT_TTL_MINUTES

    def set_expiry_minutes(self, expiry_minutes: int) -> None:
        """Set cache expiry time.

        Args:
            expiry_minutes: Cache TTL in minutes
        """
        self._cache_ttl = timedelta(minutes=expiry_minutes)
        self.logger.debug(f"Cache TTL set to {expiry_minutes} minutes")

    # ========================================================================
    # Stub Methods (for backward compatibility, no-ops in simple implementation)
    # ========================================================================

    def cache_exr_thumbnails_batch(
        self,
        exr_files: list[tuple[Path, str, str, str]],
    ) -> dict[str, Path | None]:
        """Process multiple EXR thumbnails (simplified: process one by one).

        Args:
            exr_files: List of tuples (source_path, show, sequence, shot)

        Returns:
            Dictionary mapping shot keys to thumbnail paths
        """
        results: dict[str, Path | None] = {}

        for source_path, show, sequence, shot in exr_files:
            cache_key = f"{show}_{sequence}_{shot}"
            result = self.cache_thumbnail(source_path, show, sequence, shot)
            results[cache_key] = result

        return results

    def clear_failed_attempts(self, cache_key: str | None = None) -> None:
        """Clear failed attempts (no-op in simple implementation).

        Args:
            cache_key: Ignored
        """
        # No failure tracking in simple implementation

    def get_failed_attempts_status(self) -> dict[str, dict[str, object]]:
        """Get failed attempts status (always empty in simple implementation).

        Returns:
            Empty dictionary
        """
        return {}

    def set_memory_limit(self, max_memory_mb: int) -> None:
        """Set memory limit (no-op in simple implementation).

        Args:
            max_memory_mb: Ignored
        """
        # No memory management in simple implementation

    def get_failure_status(self) -> dict[str, object]:
        """Get failure status (always empty in simple implementation).

        Returns:
            Empty dictionary
        """
        return {}

    # ========================================================================
    # Internal Helper Methods
    # ========================================================================

    def _read_json_cache(
        self, cache_file: Path, check_ttl: bool = True
    ) -> list[ShotDict | ThreeDESceneDict] | None:
        """Read and validate JSON cache file.

        Args:
            cache_file: Path to cache file
            check_ttl: Whether to check TTL expiration (default True)

        Returns:
            Cached data or None if not found/expired/invalid
        """
        if not cache_file.exists():
            return None

        try:
            # Check TTL (if enabled)
            if check_ttl:
                age = datetime.now() - datetime.fromtimestamp(
                    cache_file.stat().st_mtime
                )
                if age > self._cache_ttl:
                    self.logger.debug(f"Cache expired: {cache_file}")
                    return None

            # Read JSON - returns JSONValue which we validate at runtime
            with open(cache_file) as f:
                raw_data: JSONValue = cast("JSONValue", json.load(f))

            # Validate structure through runtime checks and type narrowing
            if isinstance(raw_data, list):
                # Direct list format - validate it's a list of dicts
                if raw_data and not isinstance(raw_data[0], dict):
                    self.logger.warning(
                        f"Invalid cache format: expected list of dicts, got list of {type(raw_data[0])}"
                    )
                    return None
                return cast("list[ShotDict | ThreeDESceneDict]", raw_data)

            if isinstance(raw_data, dict):
                # Handle wrapped format: {"data": [...], "cached_at": "..."}
                # Try nested keys: data.data, data.shots, data.scenes
                result: JSONValue = raw_data.get("data")
                if result is None:
                    result = raw_data.get("shots")
                if result is None:
                    result = raw_data.get("scenes", [])

                if isinstance(result, list):
                    # Validate it's a list of dicts
                    if result and not isinstance(result[0], dict):
                        self.logger.warning(
                            f"Invalid cache format: expected list of dicts, got list of {type(result[0])}"
                        )
                        return None
                    return cast("list[ShotDict | ThreeDESceneDict]", result)
                return []

            self.logger.warning(
                f"Unexpected cache format: {cache_file}, type: {type(raw_data)}"
            )
            return None

        except Exception as e:
            self.logger.error(f"Failed to read cache file {cache_file}: {e}")
            return None

    def _write_json_cache(self, cache_file: Path, data: object) -> None:
        """Write data to JSON cache file atomically.

        Args:
            cache_file: Path to cache file
            data: Data to cache
        """
        try:
            # Ensure directory exists
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Simple format with metadata
            cache_data = {
                "data": data,
                "cached_at": datetime.now().isoformat(),
            }

            # Atomic write: write to temp file, then rename
            # os.replace() is atomic on POSIX, ensuring readers see either old or new file, never partial
            fd, temp_path = tempfile.mkstemp(
                dir=cache_file.parent, prefix=f".{cache_file.name}.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(cache_data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())  # Ensure data is written to disk

                # Atomic rename (POSIX guarantees atomicity on same filesystem)
                os.replace(temp_path, cache_file)

                self.logger.debug(f"Cached data to: {cache_file}")

            except Exception:
                # Clean up temp file on error
                with contextlib.suppress(OSError):
                    os.unlink(temp_path)
                raise

        except Exception as e:
            self.logger.error(f"Failed to write cache file {cache_file}: {e}")

    def shutdown(self) -> None:
        """Shutdown cache manager (backward compatibility stub).

        The simplified cache manager doesn't need cleanup on shutdown.
        This method exists for backward compatibility with cleanup_manager.py.
        """
        self.logger.debug("Cache manager shutdown called (no-op in simplified version)")
