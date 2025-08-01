"""Cache manager for shot data and thumbnails."""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtGui import QPixmap

if TYPE_CHECKING:
    from shot_model import Shot


class CacheManager(QObject):
    """Manages caching of shot data and thumbnails."""

    # Signals
    cache_updated = Signal()

    # Cache settings (configuration constants)
    CACHE_THUMBNAIL_SIZE = 512
    CACHE_EXPIRY_MINUTES = 30

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
        """Cache a thumbnail from source path."""
        if not source_path.exists():
            return None

        # Create cache directory
        cache_dir = self.thumbnails_dir / show / sequence
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache file path
        cache_path = cache_dir / f"{shot}_thumb.jpg"

        try:
            # Load and resize image
            pixmap = QPixmap(str(source_path))
            if pixmap.isNull():
                return None

            # Scale to cache size
            scaled = pixmap.scaled(
                self.CACHE_THUMBNAIL_SIZE,
                self.CACHE_THUMBNAIL_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # Save to cache
            if scaled.save(str(cache_path), "JPEG", 85):
                return cache_path
        except Exception as e:
            print(f"Error caching thumbnail: {e}")

        return None

    def get_cached_shots(self) -> Optional[List[Dict[str, str]]]:
        """Get cached shot list if valid."""
        if not self.shots_cache_file.exists():
            return None

        try:
            with open(self.shots_cache_file, "r") as f:
                data = json.load(f)

            # Check if cache is expired
            cache_time = datetime.fromisoformat(data.get("timestamp", "1970-01-01"))
            if datetime.now() - cache_time > timedelta(
                minutes=self.CACHE_EXPIRY_MINUTES
            ):
                return None

            return data.get("shots", [])
        except Exception as e:
            print(f"Error reading shot cache: {e}")
            return None

    def cache_shots(self, shots: Union[List["Shot"], List[Dict[str, str]]]):
        """Cache shot list to file.

        Args:
            shots: List of Shot objects or dictionaries to cache
        """
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
                shot_dicts = [shot.to_dict() for shot in shots]  # type: ignore[attr-defined]

            data: dict[str, Any] = {
                "timestamp": datetime.now().isoformat(),
                "shots": shot_dicts,
            }

            # Ensure directory exists
            self.shots_cache_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.shots_cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error caching shots: {e}")

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
        except Exception as e:
            print(f"Error reading 3DE scene cache: {e}")
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
        except Exception as e:
            print(f"Error caching 3DE scenes: {e}")

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
        except Exception as e:
            print(f"Error clearing cache: {e}")


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
