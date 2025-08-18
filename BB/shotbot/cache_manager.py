"""Cache manager for shot data and thumbnails."""

import json
import logging
import shutil
import tempfile
import threading
import uuid
from concurrent.futures import Future
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union

from PySide6.QtCore import QObject, QRunnable, Qt, QThread, QThreadPool, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from config import Config, ThreadingConfig

if TYPE_CHECKING:
    from shot_model import Shot

# Set up logger for this module
logger = logging.getLogger(__name__)


class ThumbnailCacheResult:
    """Result container for async thumbnail caching."""

    def __init__(self):
        self.future: Future = Future()
        self.cache_path: Optional[Path] = None
        self.error: Optional[str] = None
        self._complete_event = threading.Event()
        self._completed_lock = threading.Lock()
        self._is_complete = False

    def set_result(self, cache_path: Path):
        """Set successful result (thread-safe, prevents multiple completions)."""
        with self._completed_lock:
            if self._is_complete:
                return  # Already completed, ignore
            self._is_complete = True

        self.cache_path = cache_path
        try:
            self.future.set_result(cache_path)
        except Exception:
            pass  # Future already completed
        self._complete_event.set()

    def set_error(self, error: str):
        """Set error result (thread-safe, prevents multiple completions)."""
        with self._completed_lock:
            if self._is_complete:
                return  # Already completed, ignore
            self._is_complete = True

        self.error = error
        try:
            self.future.set_exception(Exception(error))
        except Exception:
            pass  # Future already completed
        self._complete_event.set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Wait for completion.

        Returns:
            True if completed within timeout
        """
        return self._complete_event.wait(timeout)

    def get_result(self, timeout: Optional[float] = None) -> Optional[Path]:
        """Get result with optional timeout.

        Returns:
            Cached path or None if failed/timeout
        """
        try:
            return self.future.result(timeout=timeout)
        except Exception:
            return None


class CacheManager(QObject):
    """Manages caching of shot data and thumbnails with thread safety and memory monitoring."""

    # Signals
    cache_updated = Signal()

    # Cache settings - use Config values
    @property
    def CACHE_THUMBNAIL_SIZE(self) -> int:
        """Get the cached thumbnail size from configuration.

        Returns:
            int: Thumbnail size in pixels for cached images. This determines
                both the width and height of square thumbnail images stored
                in the cache directory.

        Note:
            This property delegates to Config.CACHE_THUMBNAIL_SIZE to ensure
            cache behavior remains consistent with application configuration.
            Changes to the config value will be reflected immediately.
        """
        return Config.CACHE_THUMBNAIL_SIZE

    @property
    def CACHE_EXPIRY_MINUTES(self) -> int:
        """Get cache expiry time in minutes from configuration.

        Returns:
            int: Number of minutes after which cached data expires and
                requires refreshing. This applies to both shot data and
                3DE scene cache entries.

        Note:
            Cache expiry is checked during read operations. Expired entries
            are automatically refreshed from source data. This property
            delegates to Config.CACHE_EXPIRY_MINUTES for centralized control.
        """
        return Config.CACHE_EXPIRY_MINUTES

    def __init__(self, cache_dir: Optional[Path] = None):
        super().__init__()

        # Thread safety for cache operations - INSTANCE variables, not class!
        self._lock: threading.RLock = threading.RLock()

        # Memory tracking with proper type annotations - INSTANCE variables, not class!
        self._memory_usage_bytes: int = 0
        self._max_memory_bytes: int = (
            ThreadingConfig.CACHE_MAX_MEMORY_MB * 1024 * 1024
        )  # Cache memory limit

        # Use provided cache_dir or default to ~/.shotbot/cache
        self.cache_dir = cache_dir or (Path.home() / ".shotbot" / "cache")
        self.thumbnails_dir = self.cache_dir / "thumbnails"
        self.shots_cache_file = self.cache_dir / "shots.json"
        self.threede_scenes_cache_file = self.cache_dir / "threede_scenes.json"
        self._ensure_cache_dirs()

        # Track cached thumbnails for memory management
        self._cached_thumbnails: Dict[str, int] = {}  # path -> size in bytes

        # Track active async loaders for synchronization
        self._active_loaders: Dict[str, ThumbnailCacheResult] = {}

        # Track last validation time
        self._last_validation_time = datetime.now()
        self._validation_interval_minutes = 30  # Validate every 30 minutes

    def _ensure_cache_dirs(self):
        """Ensure cache directories exist with robust error handling."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
                logger.debug("Ensured cache directory exists: %s", self.thumbnails_dir)
                return
            except (OSError, PermissionError) as e:
                logger.error("Failed to create cache dir (attempt %d): %s", attempt + 1, e)
                if attempt == max_retries - 1:
                    # Use fallback temp directory as last resort
                    try:
                        self.thumbnails_dir = Path(
                            tempfile.mkdtemp(prefix="shotbot_cache_"),
                        )
                        logger.warning(
                            f"Using fallback cache dir: {self.thumbnails_dir}",
                        )
                        return
                    except Exception as fallback_error:
                        logger.critical(
                            f"Failed to create fallback cache dir: {fallback_error}",
                        )
                        raise
            except Exception as e:
                logger.exception(f"Unexpected error creating cache directory: {e}")
                if attempt == max_retries - 1:
                    raise

    def ensure_cache_directory(self) -> bool:
        """Ensure cache directory exists, creating if necessary.

        Returns:
            True if directory exists or was created, False on failure
        """
        try:
            if not self.thumbnails_dir.exists():
                self._ensure_cache_dirs()
            return True
        except Exception as e:
            logger.error(f"Failed to ensure cache directory: {e}")
            return False

    def get_cached_thumbnail(
        self, show: str, sequence: str, shot: str,
    ) -> Optional[Path]:
        """Get path to cached thumbnail if it exists (thread-safe).

        Also performs periodic validation to maintain cache consistency.
        """
        with self._lock:
            # Ensure cache directory exists (in case it was deleted)
            if not self.thumbnails_dir.exists():
                logger.debug("Cache directory missing, recreating...")
                self._ensure_cache_dirs()

            # Check if we should run validation
            time_since_validation = datetime.now() - self._last_validation_time
            if time_since_validation > timedelta(
                minutes=self._validation_interval_minutes,
            ):
                logger.debug("Running periodic cache validation")
                self.validate_cache()
                self._last_validation_time = datetime.now()

            cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"
            if cache_path.exists():
                return cache_path
            return None

    def cache_thumbnail(
        self,
        source_path: Path,
        show: str,
        sequence: str,
        shot: str,
        wait: bool = True,
        timeout: Optional[float] = None,
    ) -> Optional[Union[Path, ThumbnailCacheResult]]:
        """Cache a thumbnail from source path with optional synchronization.

        Args:
            source_path: Path to the source image file
            show: Show name for organizing cache
            sequence: Sequence name for organizing cache
            shot: Shot name for the cached file
            wait: If True, wait for completion and return Path. If False, return ThumbnailCacheResult
            timeout: Maximum wait time in seconds (only used if wait=True)

        Returns:
            If wait=True: Path to cached thumbnail if successful, None otherwise
            If wait=False: ThumbnailCacheResult for async waiting
        """
        if not source_path or not source_path.exists():
            logger.warning(f"Source thumbnail path does not exist: {source_path}")
            return None

        # Validate cache parameters
        if not all([show, sequence, shot]):
            logger.error("Missing required parameters for thumbnail caching")
            return None

        # Generate cache key for tracking
        cache_key = f"{show}_{sequence}_{shot}"

        # Use lock for thread-safe operations
        with self._lock:
            # Check if already being loaded
            if cache_key in self._active_loaders:
                result = self._active_loaders[cache_key]
                if wait:
                    return result.get_result(timeout)
                return result

            # Check if already cached on disk
            cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"
            if cache_path.exists():
                logger.debug(f"Thumbnail already cached: {cache_path}")
                return cache_path

            # Create new result container
            result = ThumbnailCacheResult()
            self._active_loaders[cache_key] = result

        # Create cache directory
        cache_dir = self.thumbnails_dir / show / sequence
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to create cache directory {cache_dir}: {e}")
            result.set_error(str(e))
            self._cleanup_loader(cache_key)
            return None if wait else result

        # Cache file path
        cache_path = cache_dir / f"{shot}_thumb.jpg"

        try:
            # Check if this is a large file that needs special handling
            file_size_mb = source_path.stat().st_size / (1024 * 1024)
            suffix_lower = source_path.suffix.lower()
            is_heavy_format = suffix_lower in getattr(Config, "THUMBNAIL_FALLBACK_EXTENSIONS", [".exr", ".tiff", ".tif"])

            if is_heavy_format and file_size_mb > 10:
                logger.info(
                    f"Processing large {suffix_lower} file ({file_size_mb:.1f}MB): {source_path.name}",
                )

            # Check if we're on the main thread for Qt operations
            app = QApplication.instance()
            is_main_thread = app is not None and QThread.currentThread() == app.thread()

            if not is_main_thread:
                # If called from background thread, use thread pool for Qt operations
                logger.debug(
                    "Cache thumbnail called from background thread - using thread pool",
                )
                # Create a loader task with result container
                loader = ThumbnailCacheLoader(
                    self, source_path, show, sequence, shot, result,
                )
                pool = QThreadPool.globalInstance()
                pool.start(loader)

                # Return based on wait parameter
                if wait:
                    return result.get_result(timeout)
                return result

            # If on main thread, call the direct method
            cached_path = self.cache_thumbnail_direct(source_path, show, sequence, shot)

            # Update result
            if cached_path:
                result.set_result(cached_path)
            else:
                result.set_error("Failed to cache thumbnail")

            # Cleanup loader tracking
            self._cleanup_loader(cache_key)

            # Return appropriate value
            return cached_path if wait else result

        except Exception as e:
            logger.exception(f"Unexpected error caching thumbnail {source_path}: {e}")
            result.set_error(str(e))
            self._cleanup_loader(cache_key)
            return None if wait else result

    def _cleanup_loader(self, cache_key: str):
        """Remove completed loader from tracking."""
        with self._lock:
            self._active_loaders.pop(cache_key, None)

    def cache_thumbnail_direct(
        self, source_path: Path, show: str, sequence: str, shot: str,
    ) -> Optional[Path]:
        """Direct thumbnail caching implementation without thread checks.

        This method does the actual work of caching thumbnails and should only
        be called from the main thread or from ThumbnailCacheLoader to avoid
        infinite recursion.

        Args:
            source_path: Path to the source image file
            show: Show name for organizing cache
            sequence: Sequence name for organizing cache
            shot: Shot name for the cached file

        Returns:
            Path to cached thumbnail if successful, None otherwise
        """
        # Build cache path
        cache_dir = self.thumbnails_dir / show / sequence
        cache_path = cache_dir / f"{shot}_thumb.jpg"

        # Load and process image with proper resource management
        # Use QImage for most formats, PIL for EXR files

        try:
            # Check if this is a large file that needs special handling
            file_size_mb = source_path.stat().st_size / (1024 * 1024)
            suffix_lower = source_path.suffix.lower()
            is_heavy_format = suffix_lower in getattr(Config, "THUMBNAIL_FALLBACK_EXTENSIONS", [".exr", ".tiff", ".tif"])
            
            # Decide whether to use PIL or Qt based on format and size
            use_pil = False
            if is_heavy_format:
                # Always use PIL for heavy formats for better memory handling
                use_pil = True
                if file_size_mb > 10:
                    logger.info(
                        f"Processing large {suffix_lower} file with PIL ({file_size_mb:.1f}MB): {source_path.name}",
                    )
            
            # Try PIL first for heavy formats
            if use_pil:
                try:
                    # Import PIL on demand to avoid dependency if not needed
                    from PIL import Image as PILImage
                    
                    # Open with PIL - it handles EXR efficiently
                    pil_image = PILImage.open(str(source_path))
                    
                    # Validate the image is actually usable
                    if pil_image.size[0] == 0 or pil_image.size[1] == 0:
                        raise ValueError("Image has zero dimensions")
                    
                    # Force loading of image data to verify it's not corrupted
                    try:
                        pil_image.load()
                    except Exception as load_error:
                        raise ValueError(f"Image data is corrupted or unreadable: {load_error}")
                    
                    # Convert to RGB if necessary (EXR might be in different modes)
                    if pil_image.mode not in ["RGB", "RGBA"]:
                        pil_image = pil_image.convert("RGB")
                    
                    # Calculate thumbnail size maintaining aspect ratio
                    thumb_size = (self.CACHE_THUMBNAIL_SIZE, self.CACHE_THUMBNAIL_SIZE)
                    pil_image.thumbnail(thumb_size, PILImage.Resampling.LANCZOS)
                    
                    # Save directly as JPEG
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    temp_path = cache_path.with_suffix(f".tmp_{uuid.uuid4().hex[:8]}")
                    
                    # Higher quality for EXR-derived thumbnails
                    quality = 95 if suffix_lower == ".exr" else 90
                    pil_image.save(str(temp_path), "JPEG", quality=quality, optimize=True)
                    
                    # Atomic move
                    temp_path.replace(cache_path)
                    
                    # Track memory usage
                    with self._lock:
                        try:
                            file_size = cache_path.stat().st_size
                            self._cached_thumbnails[str(cache_path)] = file_size
                            self._memory_usage_bytes += file_size
                            
                            if self._memory_usage_bytes > self._max_memory_bytes:
                                self._evict_old_thumbnails()
                        except (OSError, IOError):
                            pass
                    
                    logger.debug(
                        "Cached %s thumbnail with PIL: %s (%0.1fMB -> %0.1fKB)",
                        suffix_lower, cache_path, file_size_mb, cache_path.stat().st_size / 1024,
                    )
                    return cache_path
                    
                except ImportError:
                    logger.warning("PIL not available, falling back to Qt for image loading")
                    use_pil = False
                except Exception as e:
                    logger.warning(f"PIL failed to process {suffix_lower}: {e}, trying Qt")
                    use_pil = False
            
            # Fall back to Qt if PIL wasn't used or failed
            if not use_pil:
                # Add dimension pre-check for large format files before loading with QImage
                if suffix_lower in [".exr", ".tiff", ".tif"]:
                    try:
                        # Use PIL to get dimensions without loading pixel data
                        from PIL import Image as PILImage
                        with PILImage.open(str(source_path)) as pil_img:
                            width, height = pil_img.size
                            max_dim = 20000 if is_heavy_format else 10000
                            if width > max_dim or height > max_dim:
                                logger.warning(
                                    f"Image too large ({width}x{height} > {max_dim}): {source_path}"
                                )
                                return None
                    except Exception as e:
                        logger.debug(f"Could not pre-check dimensions with PIL: {e}")
                        # Fall through to regular QImage loading
                
                # Load image using QImage
                image = QImage(str(source_path))
                if image.isNull():
                    logger.warning(f"Failed to load image: {source_path}")
                    # For EXR files, provide helpful message
                    if suffix_lower == ".exr":
                        logger.info("Note: Install Pillow with 'pip install Pillow' for better EXR support")
                    return None

            # Validate image dimensions to prevent memory issues (if not already checked)
            # Be more lenient with heavy formats as they're often high-res plates
            if "image" in locals():
                max_dim = 20000 if is_heavy_format else 10000
                if image.width() > max_dim or image.height() > max_dim:
                    logger.warning(
                        f"Image too large ({image.width()}x{image.height()} > {max_dim}): {source_path}",
                    )
                    return None

            # Scale to cache size using QImage
            scaled = image.scaled(
                self.CACHE_THUMBNAIL_SIZE,
                self.CACHE_THUMBNAIL_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            if scaled.isNull():
                logger.warning(f"Failed to scale thumbnail: {source_path}")
                return None

            # Save to cache using atomic write (temp file + rename)
            # Ensure directory exists (might have been deleted concurrently)
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Generate unique temp file to avoid collisions
            temp_path = cache_path.with_suffix(f".tmp_{uuid.uuid4().hex[:8]}")

            try:
                # Use higher quality for heavy format-derived thumbnails
                quality = 95 if is_heavy_format else 85
                if scaled.save(str(temp_path), "JPEG", quality):  # type: ignore[call-overload]
                    # Atomic move - replace if exists
                    temp_path.replace(cache_path)

                    # Track memory usage
                    with self._lock:
                        try:
                            file_size = cache_path.stat().st_size
                            self._cached_thumbnails[str(cache_path)] = file_size
                            self._memory_usage_bytes += file_size

                            # Check if we need to evict old thumbnails
                            if self._memory_usage_bytes > self._max_memory_bytes:
                                self._evict_old_thumbnails()

                        except (OSError, IOError):
                            pass  # Ignore errors in memory tracking

                    logger.debug(
                        f"Cached thumbnail: {cache_path} (total cache: {self._memory_usage_bytes / 1024 / 1024:.1f}MB)",
                    )
                    return cache_path
                logger.warning(
                    f"Failed to save thumbnail to temp file: {temp_path}",
                )
                return None
            finally:
                # Clean up temp file if it still exists
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except (OSError, IOError):
                        pass

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
            # Proper Qt resource cleanup to prevent memory leaks
            if "image" in locals() and image is not None:
                # For QImage objects, explicitly delete
                del image
            if "scaled" in locals() and scaled is not None:
                del scaled
            # Force garbage collection for large images
            import gc
            gc.collect()

    def get_cached_shots(self) -> Optional[List[Dict[str, Any]]]:
        """Get cached shot list if valid.

        Returns:
            List of shot dictionaries if cache is valid, None otherwise
        """
        if not self.shots_cache_file.exists():
            logger.debug("Shot cache file does not exist")
            return None

        try:
            with open(self.shots_cache_file, "r", encoding="utf-8") as f:
                data: Any = json.load(f)

            # Validate cache structure
            if not isinstance(data, dict) or "timestamp" not in data:
                logger.warning("Invalid shot cache structure - missing timestamp")
                return None

            cache_data: Dict[str, Any] = data  # type: ignore[assignment]

            # Check if cache is expired
            try:
                cache_time = datetime.fromisoformat(cache_data["timestamp"])
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid timestamp in shot cache: {e}")
                return None

            if datetime.now() - cache_time > timedelta(
                minutes=self.CACHE_EXPIRY_MINUTES,
            ):
                logger.debug(f"Shot cache expired (age: {datetime.now() - cache_time})")
                return None

            shots_data = cache_data.get("shots", [])
            if not isinstance(shots_data, list):
                logger.warning("Invalid shot cache structure - shots is not a list")
                return None

            # Type assertion since we validated it's a list above
            shots: List[Dict[str, Any]] = shots_data  # type: ignore[assignment]
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

    def cache_shots(self, shots: Union[Sequence["Shot"], Sequence[Dict[str, str]]]):
        """Cache shot list to file.

        Args:
            shots: List of Shot objects or dictionaries to cache
        """
        if shots is None:
            logger.warning("Attempted to cache None shots")
            return

        with self._lock:  # Thread safety for concurrent cache operations
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
                # Use unique temp file name to avoid collisions between threads
                temp_file = self.shots_cache_file.with_suffix(
                    f".tmp_{uuid.uuid4().hex[:8]}",
                )
                try:
                    with open(temp_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)

                    # Atomic move to final location
                    temp_file.replace(self.shots_cache_file)
                    logger.debug(
                        f"Cached {len(shot_dicts)} shots to {self.shots_cache_file}",
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
                minutes=self.CACHE_EXPIRY_MINUTES,
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

    def has_valid_threede_cache(self) -> bool:
        """Check if we have a valid 3DE cache (including valid empty results).

        Returns:
            True if cache exists and is not expired (even if empty), False otherwise
        """
        if not self.threede_scenes_cache_file.exists():
            return False

        try:
            with open(self.threede_scenes_cache_file, "r") as f:
                data = json.load(f)

            # Check if cache is expired
            cache_time = datetime.fromisoformat(data.get("timestamp", "1970-01-01"))
            age = datetime.now() - cache_time

            # Cache is valid if not expired (even if scenes list is empty)
            is_valid = age <= timedelta(minutes=self.CACHE_EXPIRY_MINUTES)

            if is_valid:
                scene_count = len(data.get("scenes", []))
                logger.debug(
                    f"3DE cache is valid (age: {age.total_seconds() / 60:.1f} min, "
                    + f"scenes: {scene_count})",
                )

            return is_valid
        except FileNotFoundError:
            logger.debug("3DE scene cache file not found")
            return False
        except PermissionError as e:
            logger.error(f"Permission denied reading 3DE scene cache: {e}")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"Corrupted 3DE scene cache file: {e}")
            return False
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid timestamp in 3DE scene cache: {e}")
            return False
        except (OSError, IOError) as e:
            logger.error(f"I/O error reading 3DE scene cache: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error reading 3DE scene cache: {e}")
            return False

    def cache_threede_scenes(
        self, scenes: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None,
    ):
        """Cache 3DE scene list to file with optional metadata.

        Args:
            scenes: List of scene dictionaries to cache
            metadata: Optional metadata about the scan (e.g., paths checked, quick check result)
        """
        with self._lock:  # Thread safety for concurrent cache operations
            try:
                data: dict[str, Any] = {
                    "timestamp": datetime.now().isoformat(),
                    "scenes": scenes,
                    "metadata": metadata
                    or {
                        "scan_type": "full" if scenes else "empty",
                        "scene_count": len(scenes),
                        "cached_at": datetime.now().isoformat(),
                    },
                }

                # Ensure directory exists
                self.threede_scenes_cache_file.parent.mkdir(parents=True, exist_ok=True)

                # Use atomic write with unique temp file
                temp_file = self.threede_scenes_cache_file.with_suffix(
                    f".tmp_{uuid.uuid4().hex[:8]}",
                )
                try:
                    with open(temp_file, "w") as f:
                        json.dump(data, f, indent=2)

                    # Atomic move to final location
                    temp_file.replace(self.threede_scenes_cache_file)
                    logger.debug(f"Cached {len(scenes)} 3DE scenes")

                except (OSError, IOError) as e:
                    logger.error(f"Failed to write 3DE scene cache: {e}")
                    # Clean up temp file if it exists
                    if temp_file.exists():
                        try:
                            temp_file.unlink()
                        except OSError:
                            pass

            except (OSError, IOError, PermissionError) as e:
                logger.error(f"Failed to create 3DE cache directory: {e}")
            except (TypeError, ValueError) as e:
                logger.error(f"Invalid data while caching 3DE scenes: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error caching 3DE scenes: {e}")

    def _evict_old_thumbnails(self):
        """Evict oldest thumbnails when memory limit is exceeded."""
        # Sort thumbnails by modification time
        thumbnail_stats: List[Tuple[str, int, float]] = []
        paths_to_remove: List[str] = []

        for path_str, size in list(
            self._cached_thumbnails.items(),
        ):  # Create a copy to iterate
            try:
                path = Path(path_str)
                if path.exists():
                    mtime = path.stat().st_mtime
                    thumbnail_stats.append((path_str, size, mtime))
                else:
                    # Mark for removal if file doesn't exist
                    paths_to_remove.append(path_str)
            except (OSError, IOError):
                # Mark for removal on error
                paths_to_remove.append(path_str)

        # Remove non-existent paths from tracking
        for path_str in paths_to_remove:
            if path_str in self._cached_thumbnails:
                size = self._cached_thumbnails[path_str]
                del self._cached_thumbnails[path_str]
                self._memory_usage_bytes = max(0, self._memory_usage_bytes - size)

        # Sort by modification time (oldest first)
        thumbnail_stats.sort(key=lambda x: x[2])

        # Remove oldest thumbnails until we're under 80% of limit
        target_size = int(self._max_memory_bytes * 0.8)
        for path_str, size, _ in thumbnail_stats:
            if self._memory_usage_bytes <= target_size:
                break

            try:
                Path(path_str).unlink()
                if path_str in self._cached_thumbnails:
                    del self._cached_thumbnails[path_str]
                    self._memory_usage_bytes = max(0, self._memory_usage_bytes - size)
                logger.debug(f"Evicted old thumbnail: {path_str}")
            except (OSError, IOError) as e:
                logger.debug(f"Failed to evict thumbnail {path_str}: {e}")

    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current cache memory usage statistics."""
        with self._lock:
            return {
                "total_bytes": self._memory_usage_bytes,
                "total_mb": self._memory_usage_bytes / 1024 / 1024,
                "max_mb": self._max_memory_bytes / 1024 / 1024,
                "usage_percent": (self._memory_usage_bytes / self._max_memory_bytes)
                * 100,
                "thumbnail_count": len(self._cached_thumbnails),
            }

    def clear_cache(self):
        """Clear all cached data using atomic operations to prevent race conditions."""
        with self._lock:
            try:
                # Create new temp directory first (atomic swap pattern)
                temp_dir = self.cache_dir / f"thumbnails_{uuid.uuid4().hex[:8]}"
                temp_dir.mkdir(parents=True, exist_ok=True)

                # Store old directory reference
                old_thumbnails_dir = self.thumbnails_dir

                # Atomically swap to new directory
                self.thumbnails_dir = temp_dir

                # Now safely clean up old directory and cache files
                if old_thumbnails_dir.exists():
                    try:
                        shutil.rmtree(old_thumbnails_dir, ignore_errors=True)
                    except Exception as e:
                        logger.debug(f"Error removing old thumbnails dir: {e}")

                if self.shots_cache_file.exists():
                    try:
                        self.shots_cache_file.unlink()
                    except (OSError, IOError) as e:
                        logger.debug(f"Error removing shots cache: {e}")

                if self.threede_scenes_cache_file.exists():
                    try:
                        self.threede_scenes_cache_file.unlink()
                    except (OSError, IOError) as e:
                        logger.debug(f"Error removing 3DE scenes cache: {e}")

                # Reset memory tracking
                self._cached_thumbnails.clear()
                self._memory_usage_bytes = 0

                logger.info("Cache cleared successfully")

            except PermissionError as e:
                logger.error(f"Permission denied while clearing cache: {e}")
                # Ensure we still have a working directory
                self._ensure_cache_dirs()
            except (OSError, IOError) as e:
                logger.error(f"I/O error while clearing cache: {e}")
                self._ensure_cache_dirs()
            except Exception as e:
                logger.exception(f"Unexpected error clearing cache: {e}")
                self._ensure_cache_dirs()

    def validate_cache(self) -> Dict[str, Any]:
        """Validate cache consistency and fix issues.

        Returns:
            Dictionary with validation results and statistics.
        """
        with self._lock:
            issues_fixed = 0
            orphaned_files = 0
            invalid_entries = 0

            try:
                # Check tracked thumbnails exist and have correct size
                invalid_paths: List[str] = []
                size_mismatches: List[Tuple[str, int, int]] = []

                for path_str in list(self._cached_thumbnails.keys()):
                    path = Path(path_str)
                    if not path.exists():
                        invalid_paths.append(path_str)
                        invalid_entries += 1
                    else:
                        # Check if tracked size matches actual size
                        try:
                            actual_size = path.stat().st_size
                            tracked_size = self._cached_thumbnails[path_str]
                            if actual_size != tracked_size:
                                size_mismatches.append(
                                    (path_str, actual_size, tracked_size),
                                )
                        except (OSError, IOError):
                            invalid_paths.append(path_str)
                            invalid_entries += 1

                # Remove invalid entries
                for path_str in invalid_paths:
                    if path_str in self._cached_thumbnails:
                        size = self._cached_thumbnails[path_str]
                        del self._cached_thumbnails[path_str]
                        self._memory_usage_bytes = max(
                            0, self._memory_usage_bytes - size,
                        )
                        issues_fixed += 1

                # Fix size mismatches
                for path_str, actual_size, tracked_size in size_mismatches:
                    self._cached_thumbnails[path_str] = actual_size
                    self._memory_usage_bytes += actual_size - tracked_size
                    issues_fixed += 1
                    logger.debug(
                        f"Fixed size mismatch for {path_str}: tracked={tracked_size}, actual={actual_size}",
                    )

                # Check for orphaned thumbnail files not being tracked
                if self.thumbnails_dir.exists():
                    for thumb_file in self.thumbnails_dir.rglob("*.jpg"):
                        if str(thumb_file) not in self._cached_thumbnails:
                            orphaned_files += 1
                            # Add to tracking
                            try:
                                size = thumb_file.stat().st_size
                                self._cached_thumbnails[str(thumb_file)] = size
                                self._memory_usage_bytes += size
                                issues_fixed += 1
                            except (OSError, IOError):
                                pass

                # Recalculate memory usage
                actual_usage = sum(self._cached_thumbnails.values())
                if actual_usage != self._memory_usage_bytes:
                    logger.info(
                        f"Memory usage mismatch: tracked={self._memory_usage_bytes}, actual={actual_usage}. Correcting...",
                    )
                    self._memory_usage_bytes = actual_usage
                    issues_fixed += 1

                return {
                    "valid": issues_fixed == 0,
                    "issues_fixed": issues_fixed,
                    "invalid_entries": invalid_entries,
                    "orphaned_files": orphaned_files,
                    "memory_usage_bytes": self._memory_usage_bytes,
                    "tracked_files": len(self._cached_thumbnails),
                }

            except Exception as e:
                logger.error(f"Error during cache validation: {e}")
                return {
                    "valid": False,
                    "error": str(e),
                }

    def shutdown(self) -> None:
        """Gracefully shutdown the cache manager.

        This method is called during application shutdown to ensure
        proper cleanup of resources and pending operations.
        """
        logger.info("CacheManager shutting down...")

        with self._lock:
            try:
                # Validate and fix any cache inconsistencies before shutdown
                validation_result = self.validate_cache()
                if not validation_result.get("valid", False):
                    logger.info(
                        f"Fixed {validation_result.get('issues_fixed', 0)} cache issues during shutdown",
                    )

                # Flush any pending cache operations
                # Note: Current implementation doesn't have pending operations
                # but this is where we'd handle them if we add async caching

                # Clear memory tracking to prevent leaks
                self._cached_thumbnails.clear()
                self._memory_usage_bytes = 0

                logger.info("CacheManager shutdown complete")

            except Exception as e:
                logger.error(f"Error during cache manager shutdown: {e}")


class ThumbnailCacheLoader(QRunnable):
    """Background thumbnail cache loader with synchronization support."""

    class Signals(QObject):
        loaded = Signal(str, str, str, Path)  # show, sequence, shot, cache_path
        failed = Signal(str, str, str, str)  # show, sequence, shot, error_msg

    def __init__(
        self,
        cache_manager: CacheManager,
        source_path: Path,
        show: str,
        sequence: str,
        shot: str,
        result: Optional[ThumbnailCacheResult] = None,
    ):
        super().__init__()
        self.cache_manager = cache_manager
        self.source_path = source_path
        self.show = show
        self.sequence = sequence
        self.shot = shot
        self.signals = self.Signals()
        self.result = result or ThumbnailCacheResult()
        self.setAutoDelete(True)

    def run(self):
        """Cache the thumbnail in background with result synchronization."""
        try:
            # Call the internal method directly to avoid infinite recursion
            # This is already running on a background thread, so we don't need
            # to check for thread context again
            cache_path = self.cache_manager.cache_thumbnail_direct(
                self.source_path, self.show, self.sequence, self.shot,
            )

            if cache_path:
                # Set successful result
                self.result.set_result(cache_path)

                # Emit signal if still valid
                if hasattr(self, "signals") and self.signals:
                    try:
                        self.signals.loaded.emit(
                            self.show, self.sequence, self.shot, cache_path,
                        )
                    except RuntimeError:
                        pass  # Signals deleted

                logger.debug(f"Successfully cached thumbnail for {self.shot}")
            else:
                # Set error result
                error_msg = f"Cache operation returned None for {self.shot}"
                self.result.set_error(error_msg)

                if hasattr(self, "signals") and self.signals:
                    try:
                        self.signals.failed.emit(
                            self.show, self.sequence, self.shot, error_msg,
                        )
                    except RuntimeError:
                        # Signals object was deleted, safe to ignore
                        pass
                logger.warning(error_msg)

        except Exception as e:
            # Set exception result
            error_msg = f"Exception while caching thumbnail for {self.shot}: {e}"
            self.result.set_error(str(e))

            # Check if signals object still exists before emitting
            if hasattr(self, "signals") and self.signals:
                try:
                    self.signals.failed.emit(
                        self.show, self.sequence, self.shot, str(e),
                    )
                except RuntimeError:
                    # Signals object was deleted, safe to ignore
                    pass
            logger.error(error_msg)

        finally:
            # Cleanup loader from tracking
            cache_key = f"{self.show}_{self.sequence}_{self.shot}"
            self.cache_manager._cleanup_loader(cache_key)
