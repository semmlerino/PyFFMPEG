"""Cache manager for shot data and thumbnails."""

import json
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtGui import QPixmap

from config import Config

if TYPE_CHECKING:
    from shot_model import Shot

# Set up logger for this module
logger = logging.getLogger(__name__)


class CacheManager(QObject):
    """Manages caching of shot data and thumbnails."""

    # Signals
    cache_updated = Signal()

    # Cache settings - use Config values
    @property
    def CACHE_THUMBNAIL_SIZE(self):
        return Config.CACHE_THUMBNAIL_SIZE

    @property
    def CACHE_EXPIRY_MINUTES(self):
        return Config.CACHE_EXPIRY_MINUTES

    def __init__(self, cache_dir: Optional[Path] = None):
        super().__init__()
        # Use provided cache_dir or default to ~/.shotbot/cache
        self.cache_dir = cache_dir or (Path.home() / ".shotbot" / "cache")
        self.thumbnails_dir = self.cache_dir / "thumbnails"
        self.shots_cache_file = self.cache_dir / "shots.json"
        self.threede_scenes_cache_file = self.cache_dir / "threede_scenes.json"
        self._ensure_cache_dirs()

    def _ensure_cache_dirs(self):
        """Ensure cache directories exist."""
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)

    def get_cached_thumbnail(
        self, show: str, sequence: str, shot: str
    ) -> Optional[Path]:
        """Get path to cached thumbnail if it exists."""
        cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"
        if cache_path.exists():
            return cache_path
        return None

    def cache_thumbnail(
        self, source_path: Path, show: str, sequence: str, shot: str
    ) -> Optional[Path]:
        """Cache a thumbnail from source path.

        Args:
            source_path: Path to the source image file
            show: Show name for organizing cache
            sequence: Sequence name for organizing cache
            shot: Shot name for the cached file

        Returns:
            Path to cached thumbnail if successful, None otherwise
        """
        if not source_path or not source_path.exists():
            logger.warning(f"Source thumbnail path does not exist: {source_path}")
            return None

        # Validate cache parameters
        if not all([show, sequence, shot]):
            logger.error("Missing required parameters for thumbnail caching")
            return None

        # Create cache directory
        cache_dir = self.thumbnails_dir / show / sequence
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to create cache directory {cache_dir}: {e}")
            return None

        # Cache file path
        cache_path = cache_dir / f"{shot}_thumb.jpg"

        # Load and process image with proper resource management
        pixmap = None
        scaled = None

        try:
            # Load image
            pixmap = QPixmap(str(source_path))
            if pixmap.isNull():
                logger.warning(f"Failed to load image: {source_path}")
                return None

            # Validate image dimensions to prevent memory issues
            if pixmap.width() > 10000 or pixmap.height() > 10000:
                logger.warning(
                    f"Image too large ({pixmap.width()}x{pixmap.height()}): {source_path}"
                )
                return None

            # Scale to cache size
            scaled = pixmap.scaled(
                self.CACHE_THUMBNAIL_SIZE,
                self.CACHE_THUMBNAIL_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            if scaled.isNull():
                logger.warning(f"Failed to scale thumbnail: {source_path}")
                return None

            # Save to cache
            if scaled.save(str(cache_path), "JPEG", 85):
                logger.debug(f"Cached thumbnail: {cache_path}")
                return cache_path
            else:
                logger.warning(f"Failed to save thumbnail to: {cache_path}")
                return None

        except MemoryError:
            logger.error(f"Out of memory while processing thumbnail: {source_path}")
            return None
        except (OSError, IOError) as e:
            logger.error(f"I/O error while caching thumbnail {source_path}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error caching thumbnail {source_path}: {e}")
            return None
        finally:
            # Clean up Qt objects to prevent memory leaks
            # Note: QPixmap is automatically managed by Qt, but explicit cleanup helps
            del pixmap, scaled

    def get_cached_shots(self) -> Optional[List[Dict[str, str]]]:
        """Get cached shot list if valid.

        Returns:
            List of shot dictionaries if cache is valid, None otherwise
        """
        if not self.shots_cache_file.exists():
            logger.debug("Shot cache file does not exist")
            return None

        try:
            with open(self.shots_cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate cache structure
            if not isinstance(data, dict) or "timestamp" not in data:
                logger.warning("Invalid shot cache structure - missing timestamp")
                return None

            # Check if cache is expired
            try:
                cache_time = datetime.fromisoformat(data["timestamp"])
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid timestamp in shot cache: {e}")
                return None

            if datetime.now() - cache_time > timedelta(
                minutes=self.CACHE_EXPIRY_MINUTES
            ):
                logger.debug(f"Shot cache expired (age: {datetime.now() - cache_time})")
                return None

            shots = data.get("shots", [])
            if not isinstance(shots, list):
                logger.warning("Invalid shot cache structure - shots is not a list")
                return None

            logger.debug(f"Loaded {len(shots)} shots from cache")
            return shots

        except FileNotFoundError:
            logger.debug("Shot cache file not found")
            return None
        except PermissionError as e:
            logger.error(f"Permission denied reading shot cache: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Corrupted shot cache file (JSON decode error): {e}")
            return None
        except (OSError, IOError) as e:
            logger.error(f"I/O error reading shot cache: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error reading shot cache: {e}")
            return None

    def cache_shots(self, shots: Union[List["Shot"], List[Dict[str, str]]]):
        """Cache shot list to file.

        Args:
            shots: List of Shot objects or dictionaries to cache
        """
        if shots is None:
            logger.warning("Attempted to cache None shots")
            return

        try:
            # Convert to list of dictionaries
            shot_dicts: List[Dict[str, str]]

            if not shots:
                shot_dicts = []
            elif isinstance(shots[0], dict):
                # It's already a list of dictionaries
                shot_dicts = shots  # type: ignore[assignment]
            else:
                # It's a list of Shot objects - convert using to_dict()
                try:
                    shot_dicts = [shot.to_dict() for shot in shots]  # type: ignore[attr-defined]
                except AttributeError as e:
                    logger.error(f"Shot objects missing to_dict() method: {e}")
                    return

            data: dict[str, Any] = {
                "timestamp": datetime.now().isoformat(),
                "shots": shot_dicts,
            }

            # Ensure directory exists
            try:
                self.shots_cache_file.parent.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError) as e:
                logger.error(f"Failed to create cache directory: {e}")
                return

            # Write cache file with atomic operation (write to temp file first)
            temp_file = self.shots_cache_file.with_suffix(".tmp")
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

                # Atomic move to final location
                temp_file.replace(self.shots_cache_file)
                logger.debug(
                    f"Cached {len(shot_dicts)} shots to {self.shots_cache_file}"
                )

            except (OSError, IOError) as e:
                logger.error(f"Failed to write shot cache: {e}")
                # Clean up temp file if it exists
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass
                return

        except (TypeError, ValueError) as e:
            logger.error(f"Invalid data while caching shots: {e}")
        except MemoryError:
            logger.error("Out of memory while caching shots")
        except Exception as e:
            logger.exception(f"Unexpected error caching shots: {e}")

    def get_cached_threede_scenes(self) -> Optional[List[Dict[str, Any]]]:
        """Get cached 3DE scene list if valid."""
        if not self.threede_scenes_cache_file.exists():
            return None

        try:
            with open(self.threede_scenes_cache_file, "r") as f:
                data = json.load(f)

            # Check if cache is expired
            cache_time = datetime.fromisoformat(data.get("timestamp", "1970-01-01"))
            if datetime.now() - cache_time > timedelta(
                minutes=self.CACHE_EXPIRY_MINUTES
            ):
                return None

            return data.get("scenes", [])
        except FileNotFoundError:
            logger.debug("3DE scene cache file not found")
            return None
        except PermissionError as e:
            logger.error(f"Permission denied reading 3DE scene cache: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Corrupted 3DE scene cache file: {e}")
            return None
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid timestamp in 3DE scene cache: {e}")
            return None
        except (OSError, IOError) as e:
            logger.error(f"I/O error reading 3DE scene cache: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error reading 3DE scene cache: {e}")
            return None

    def cache_threede_scenes(self, scenes: List[Dict[str, Any]]):
        """Cache 3DE scene list to file."""
        try:
            data: dict[str, Any] = {
                "timestamp": datetime.now().isoformat(),
                "scenes": scenes,
            }

            # Ensure directory exists
            self.threede_scenes_cache_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.threede_scenes_cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except (OSError, IOError, PermissionError) as e:
            logger.error(f"Failed to write 3DE scene cache: {e}")
        except (TypeError, ValueError) as e:
            logger.error(f"Invalid data while caching 3DE scenes: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error caching 3DE scenes: {e}")

    def clear_cache(self):
        """Clear all cached data."""
        try:
            if self.thumbnails_dir.exists():
                shutil.rmtree(self.thumbnails_dir)
            if self.shots_cache_file.exists():
                self.shots_cache_file.unlink()
            if self.threede_scenes_cache_file.exists():
                self.threede_scenes_cache_file.unlink()
            self._ensure_cache_dirs()
        except PermissionError as e:
            logger.error(f"Permission denied while clearing cache: {e}")
        except (OSError, IOError) as e:
            logger.error(f"I/O error while clearing cache: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error clearing cache: {e}")


class ThumbnailCacheLoader(QRunnable):
    """Background thumbnail cache loader."""

    class Signals(QObject):
        loaded = Signal(str, str, str, Path)  # show, sequence, shot, cache_path

    def __init__(
        self,
        cache_manager: CacheManager,
        source_path: Path,
        show: str,
        sequence: str,
        shot: str,
    ):
        super().__init__()
        self.cache_manager = cache_manager
        self.source_path = source_path
        self.show = show
        self.sequence = sequence
        self.shot = shot
        self.signals = self.Signals()

    def run(self):
        """Cache the thumbnail in background."""
        cache_path = self.cache_manager.cache_thumbnail(
            self.source_path, self.show, self.sequence, self.shot
        )
        if cache_path:
            self.signals.loaded.emit(self.show, self.sequence, self.shot, cache_path)
