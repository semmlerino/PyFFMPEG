"""Common utilities for ShotBot application."""

from __future__ import annotations

import logging
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from types import TracebackType
from typing import Any

from config import Config

# Performance monitoring removed - was using archived module

# Set up logger for this module
logger = logging.getLogger(__name__)

# Cache for path existence checks (with TTL)
_path_cache: dict[str, tuple[bool, float]] = {}
_PATH_CACHE_TTL = 300.0  # seconds - increased from 30 to 300 for better performance
_cache_disabled = False  # Test isolation flag


def clear_all_caches():
    """Clear all utility caches - useful for testing or debugging."""
    global _path_cache
    _path_cache.clear()
    VersionUtils.clear_version_cache()
    # Clear lru_cache decorated functions
    VersionUtils.extract_version_from_path.cache_clear()
    logger.info("Cleared all utility caches")


def disable_caching() -> None:
    """Disable caching completely - useful for testing."""
    global _cache_disabled
    _cache_disabled = True
    clear_all_caches()
    logger.debug("Caching disabled for testing")


def enable_caching() -> None:
    """Re-enable caching after testing."""
    global _cache_disabled
    _cache_disabled = False
    logger.debug("Caching re-enabled after testing")


class CacheIsolation:
    """Context manager for cache isolation in tests."""

    def __init__(self):
        super().__init__()
        self.original_cache_state: dict[str, tuple[bool, float]] | None = None
        self.original_disabled_state: bool | None = None

    def __enter__(self):
        """Enter context with isolated cache."""
        global _path_cache, _cache_disabled
        # Save original state
        self.original_cache_state = _path_cache.copy()
        self.original_disabled_state = _cache_disabled

        # Clear and disable cache
        clear_all_caches()
        disable_caching()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context and restore original state."""
        global _path_cache, _cache_disabled
        # Restore original state
        _path_cache.clear()
        if self.original_cache_state is not None:
            # Update from dict items to handle type correctly
            for key, value in self.original_cache_state.items():
                _path_cache[key] = value
        if self.original_disabled_state is not None:
            _cache_disabled = self.original_disabled_state
        logger.debug("Cache isolation context exited")


def get_cache_stats() -> dict[str, Any]:
    """Get statistics about current cache usage."""
    stats: dict[str, Any] = {
        "path_cache_size": len(_path_cache),
        "version_cache_size": VersionUtils.get_version_cache_size(),
        "extract_version_cache_info": VersionUtils.extract_version_from_path.cache_info(),
    }
    return stats


class PathUtils:
    """Utilities for path construction and validation."""

    @staticmethod
    def build_path(base_path: str | Path, *segments: str) -> Path:
        """Build a path from base path and segments.

        Args:
            base_path: Base path to start from
            *segments: Path segments to append

        Returns:
            Constructed Path object
        """
        if not base_path:
            raise ValueError("Base path cannot be empty")

        path = Path(base_path)
        for segment in segments:
            if not segment:
                logger.warning(f"Empty segment in path construction from {base_path}")
                continue
            path = path / segment
        return path

    @staticmethod
    def build_thumbnail_path(
        shows_root: str,
        show: str,
        sequence: str,
        shot: str,
    ) -> Path:
        """Build thumbnail directory path.

        Args:
            shows_root: Root shows directory
            show: Show name
            sequence: Sequence name
            shot: Shot name

        Returns:
            Path to thumbnail directory
        """
        # VFX convention: shot directory is named {sequence}_{shot}
        shot_dir = f"{sequence}_{shot}"
        return PathUtils.build_path(
            shows_root,
            show,
            "shots",
            sequence,
            shot_dir,
            *Config.THUMBNAIL_SEGMENTS,
        )

    @staticmethod
    def find_turnover_plate_thumbnail(
        shows_root: str,
        show: str,
        sequence: str,
        shot: str,
    ) -> Path | None:
        """Find thumbnail from turnover plate directories with preference order.

        Searches for plate files in:
        /shows/{show}/shots/{sequence}/{shot}/publish/turnover/plate/input_plate/{PLATE}/v001/exr/{resolution}/

        Plate preference order:
        1. FG plates (FG01, FG02, etc.)
        2. BG plates (BG01, BG02, etc.)
        3. Any other available plates (EL01, etc.)

        Args:
            shows_root: Root shows directory
            show: Show name
            sequence: Sequence name
            shot: Shot name

        Returns:
            Path to first frame of best available plate, or None if not found
        """
        # Build base path to turnover plates
        shot_dir = f"{sequence}_{shot}"
        base_path = PathUtils.build_path(
            shows_root,
            show,
            "shots",
            sequence,
            shot_dir,
            "publish",
            "turnover",
            "plate",
            "input_plate",
        )

        # Try the expected path first, but also check parent directories if it doesn't exist
        if not PathUtils.validate_path_exists(base_path, "Turnover plate base"):
            # Try without input_plate subdirectory
            base_path = PathUtils.build_path(
                shows_root,
                show,
                "shots",
                sequence,
                shot_dir,
                "publish",
                "turnover",
                "plate",
            )
            if not PathUtils.validate_path_exists(
                base_path,
                "Turnover plate directory",
            ):
                return None

        # Find all available plate directories
        try:
            plate_dirs = []
            # Check if input_plate is a subdirectory
            input_plate_path = base_path / "input_plate"
            if input_plate_path.exists() and input_plate_path.is_dir():
                # Look for plate directories inside input_plate
                plate_dirs = [d for d in input_plate_path.iterdir() if d.is_dir()]
            else:
                # Look for plate directories directly in base_path
                plate_dirs = [d for d in base_path.iterdir() if d.is_dir()]
        except (OSError, PermissionError) as e:
            logger.debug(f"Error accessing turnover plates: {e}")
            return None

        if not plate_dirs:
            logger.debug(f"No plate directories found in {base_path}")
            return None

        # Sort plates by preference
        def plate_priority(plate_dir: Path) -> tuple[int, str]:
            """Return priority tuple for sorting plates."""
            name = plate_dir.name.upper()
            # Priority: (order, name)
            # Lower order = higher priority
            if name.startswith("FG"):
                return (0, name)  # FG plates highest priority
            if name.startswith("BG"):
                return (1, name)  # BG plates second priority
            return (2, name)  # All others lowest priority

        sorted_plates = sorted(plate_dirs, key=plate_priority)

        # Try each plate in priority order
        for plate_dir in sorted_plates:
            plate_name = plate_dir.name

            # Look for v001/exr/*/
            version_path = plate_dir / "v001" / "exr"
            if not version_path.exists():
                continue

            # Find resolution directories (e.g., 4312x2304)
            try:
                resolution_dirs = [d for d in version_path.iterdir() if d.is_dir()]
            except (OSError, PermissionError):
                continue

            for res_dir in resolution_dirs:
                # Find first frame (typically .1001.exr or .0001.exr)
                exr_files = FileUtils.find_files_by_extension(res_dir, ".exr", limit=10)
                if not exr_files:
                    continue

                # Sort to get the first frame number
                # Files like: GG_000_0050_turnover-plate_EL01_lin_sgamut3cine_v001.1001.exr
                def extract_frame_number(path: Path) -> int:
                    """Extract frame number from filename."""
                    # Match pattern like .1001.exr or .0001.exr
                    match = re.search(r"\.(\d{4})\.exr$", path.name, re.IGNORECASE)
                    if match:
                        return int(match.group(1))
                    return 99999  # Sort non-matching files last

                sorted_frames = sorted(exr_files, key=extract_frame_number)

                if sorted_frames:
                    first_frame = sorted_frames[0]
                    # Check if we should use EXR as fallback
                    # Only return EXR if it's reasonably sized or if we're explicitly allowing fallback
                    file_size_mb = first_frame.stat().st_size / (1024 * 1024)
                    max_direct_size = getattr(
                        Config, "THUMBNAIL_MAX_DIRECT_SIZE_MB", 10
                    )

                    if file_size_mb <= max_direct_size:
                        # Small enough to use directly
                        logger.debug(
                            f"Using turnover plate EXR as fallback: {plate_name} - {first_frame.name} ({file_size_mb:.1f}MB)",
                        )
                        return first_frame
                    # Large EXR - return it anyway, cache_manager will resize with PIL
                    logger.debug(
                        f"Found large turnover plate EXR: {plate_name} - {first_frame.name} ({file_size_mb:.1f}MB) - will resize",
                    )
                    return first_frame

        logger.debug(f"No suitable turnover plates found for {sequence}_{shot}")
        return None

    @staticmethod
    def build_raw_plate_path(workspace_path: str) -> Path:
        """Build raw plate base path.

        Args:
            workspace_path: Shot workspace path

        Returns:
            Path to raw plate directory
        """
        return PathUtils.build_path(workspace_path, *Config.RAW_PLATE_SEGMENTS)

    @staticmethod
    def build_undistortion_path(workspace_path: str, username: str) -> Path:
        """Build undistortion base path.

        Args:
            workspace_path: Shot workspace path
            username: Username for the path

        Returns:
            Path to undistortion directory
        """
        segments = ["user", username] + Config.UNDISTORTION_BASE_SEGMENTS[1:]
        return PathUtils.build_path(workspace_path, *segments)

    @staticmethod
    def build_threede_scene_path(workspace_path: str, username: str) -> Path:
        """Build 3DE scene base path.

        Args:
            workspace_path: Shot workspace path
            username: Username for the path

        Returns:
            Path to 3DE scene directory
        """
        segments = ["user", username] + Config.THREEDE_SCENE_SEGMENTS
        return PathUtils.build_path(workspace_path, *segments)

    @staticmethod
    def validate_path_exists(path: str | Path, description: str = "Path") -> bool:
        """Validate that a path exists.

        Uses caching for frequently checked paths to improve performance.

        Args:
            path: Path to validate
            description: Description for logging

        Returns:
            True if path exists, False otherwise
        """
        if not path:
            logger.debug(f"{description} is empty")
            return False

        # Skip caching if disabled (for testing)
        if _cache_disabled:
            path_obj = Path(path) if isinstance(path, str) else path
            exists = path_obj.exists()
            if not exists:
                logger.debug(f"{description} does not exist (no cache): {path_obj}")
            return exists

        # Convert to Path object and string for caching
        path_obj = Path(path) if isinstance(path, str) else path
        path_str = str(path_obj)
        current_time = time.time()

        # Check cache first
        if path_str in _path_cache:
            cached_exists, timestamp = _path_cache[path_str]
            if current_time - timestamp < _PATH_CACHE_TTL:
                # Return cached result without verification to avoid performance issues
                if not cached_exists:
                    logger.debug(f"{description} does not exist (cached): {path_str}")
                return cached_exists

        # Cache miss or expired - check actual path existence
        exists = path_obj.exists()

        # Cache the result
        _path_cache[path_str] = (exists, current_time)

        # Clean old cache entries (simple cleanup)
        # Increased threshold from 1000 to 5000 for better performance
        if len(_path_cache) > 5000:  # Prevent unlimited growth
            PathUtils._cleanup_path_cache()

        if not exists:
            logger.debug(f"{description} does not exist: {path_obj}")

        return exists

    @staticmethod
    def _cleanup_path_cache():
        """Clean expired entries from path cache.

        Optimized to only clean when cache is getting large,
        and to keep frequently accessed paths.
        """
        # Only clean if cache is significantly over limit
        if len(_path_cache) <= 2500:  # Keep some headroom
            return

        # Sort by timestamp to keep most recently accessed
        sorted_items = sorted(
            _path_cache.items(),
            key=lambda x: x[1][1],  # Sort by timestamp
            reverse=True,  # Most recent first
        )

        # Keep the most recent 2500 entries
        _path_cache.clear()
        for key, value in sorted_items[:2500]:
            _path_cache[key] = value

        logger.debug(f"Cleaned path cache, kept {len(_path_cache)} most recent entries")

    @staticmethod
    def batch_validate_paths(paths: list[str | Path]) -> dict[str, bool]:
        """Validate multiple paths at once for better performance.

        Args:
            paths: List of paths to validate

        Returns:
            Dictionary mapping path strings to existence status
        """
        results: dict[str, bool] = {}
        current_time = time.time()
        paths_to_check: list[tuple[str | Path, str]] = []

        # First pass - check cache
        for path in paths:
            path_str = str(path)
            if path_str in _path_cache:
                cached_exists, timestamp = _path_cache[path_str]
                if current_time - timestamp < _PATH_CACHE_TTL:
                    # Use cached result without verification
                    results[path_str] = cached_exists
                    continue
            paths_to_check.append((path, path_str))

        # Second pass - check filesystem for uncached paths
        for path, path_str in paths_to_check:
            path_obj: Path = Path(path) if isinstance(path, str) else path
            exists: bool = path_obj.exists()
            results[path_str] = exists
            _path_cache[path_str] = (exists, current_time)

        # Clean cache if needed
        # Increased threshold from 1000 to 5000 for better performance
        if len(_path_cache) > 5000:
            PathUtils._cleanup_path_cache()

        return results

    @staticmethod
    def safe_mkdir(path: str | Path, description: str = "Directory") -> bool:
        """Safely create directory with error handling.

        Args:
            path: Directory path to create
            description: Description for logging

        Returns:
            True if successful, False otherwise
        """
        if not path:
            logger.error(f"Cannot create {description}: empty path")
            return False

        path_obj = Path(path) if isinstance(path, str) else path
        try:
            path_obj.mkdir(parents=True, exist_ok=True)
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to create {description} {path_obj}: {e}")
            return False

    @staticmethod
    def find_any_publish_thumbnail(
        shows_root: str,
        show: str,
        sequence: str,
        shot: str,
        max_depth: int = 5,
    ) -> Path | None:
        """Find any image file containing '1001' in the publish folder as a fallback.

        Searches recursively in the publish folder for thumbnail files, with preference
        for lightweight formats (JPG/PNG) but will use EXR as a last resort.

        Args:
            shows_root: Root shows directory
            show: Show name
            sequence: Sequence name
            shot: Shot name
            max_depth: Maximum search depth to prevent deep recursion (default: 5)

        Returns:
            Path to first suitable image file found, or None if not found
        """
        # Build base path to publish directory
        shot_dir = f"{sequence}_{shot}"
        publish_path = PathUtils.build_path(
            shows_root,
            show,
            "shots",
            sequence,
            shot_dir,
            "publish",
        )

        # If publish directory doesn't exist, try the shot directory itself
        if not PathUtils.validate_path_exists(publish_path, "Publish directory"):
            # Try searching the entire shot directory as a fallback
            shot_path = PathUtils.build_path(
                shows_root,
                show,
                "shots",
                sequence,
                shot_dir,
            )
            if PathUtils.validate_path_exists(shot_path, "Shot directory"):
                publish_path = shot_path
                max_depth = min(max_depth, 3)  # Limit depth when searching entire shot
            else:
                return None

        # Recursive search with depth limit for efficiency
        def _search_directory(
            directory: Path,
            current_depth: int = 0,
        ) -> Path | None:
            """Recursively search directory for 1001 EXR files."""
            if current_depth > max_depth:
                return None

            try:
                # Collect all candidate files
                lightweight_candidates: list[Path] = []
                exr_candidates: list[Path] = []

                for file_path in directory.iterdir():
                    if file_path.is_file() and "1001" in file_path.name:
                        suffix_lower = file_path.suffix.lower()
                        # Prefer lightweight formats
                        if suffix_lower in Config.THUMBNAIL_EXTENSIONS:
                            lightweight_candidates.append(file_path)
                        # Collect EXR as fallback
                        elif suffix_lower in getattr(
                            Config, "THUMBNAIL_FALLBACK_EXTENSIONS", [".exr"]
                        ):
                            exr_candidates.append(file_path)

                # Return first lightweight format if found
                if lightweight_candidates:
                    logger.info(
                        f"Found publish thumbnail: {lightweight_candidates[0].name}"
                    )
                    return lightweight_candidates[0]

                # Use EXR as last resort (will be resized by cache_manager)
                if exr_candidates:
                    file_size_mb = exr_candidates[0].stat().st_size / (1024 * 1024)
                    logger.info(
                        f"Using EXR as fallback thumbnail: {exr_candidates[0].name} ({file_size_mb:.1f}MB)",
                    )
                    return exr_candidates[0]

                # Then recurse into subdirectories
                for sub_path in directory.iterdir():
                    if sub_path.is_dir():
                        result = _search_directory(sub_path, current_depth + 1)
                        if result:
                            return result

            except (OSError, PermissionError) as e:
                logger.debug(f"Error searching {directory}: {e}")

            return None

        result = _search_directory(publish_path)
        if result:
            logger.info(
                f"Found any publish thumbnail for {sequence}_{shot}: {result.name}",
            )
        else:
            logger.debug(
                f"No 1001.exr files found in publish folder for {sequence}_{shot}",
            )

        return result

    @staticmethod
    def discover_plate_directories(
        base_path: str | Path,
    ) -> list[tuple[str, int]]:
        """Discover available plate directories and return them in priority order.

        Args:
            base_path: Base path to search for plate directories

        Returns:
            List of (plate_name, priority) tuples sorted by priority
        """
        if not PathUtils.validate_path_exists(base_path, "Plate base path"):
            return []

        path_obj = Path(base_path) if isinstance(base_path, str) else base_path
        found_plates: list[tuple[str, int]] = []

        # Check for each possible plate pattern
        for pattern in Config.PLATE_DISCOVERY_PATTERNS:
            plate_path = path_obj / pattern
            if plate_path.exists() and plate_path.is_dir():
                # Get priority from config or use default
                priority = Config.PLATE_PRIORITY_ORDER.get(pattern, 0)
                found_plates.append((pattern, priority))
                logger.debug(
                    f"Found plate directory: {pattern} with priority {priority}",
                )

        # Sort by priority (higher numbers first)
        found_plates.sort(key=lambda x: x[1], reverse=True)

        return found_plates


class VersionUtils:
    """Utilities for handling versioned directories and files."""

    # Pattern for version directories (v001, v002, etc.)
    VERSION_PATTERN: re.Pattern[str] = re.compile(r"^v(\d{3})$")

    # Cache for version directory listings
    _version_cache: dict[str, tuple[list[tuple[int, str]], float]] = {}

    @classmethod
    def clear_version_cache(cls) -> None:
        """Clear the version cache."""
        cls._version_cache.clear()

    @classmethod
    def get_version_cache_size(cls) -> int:
        """Get the size of the version cache."""
        return len(cls._version_cache)

    @staticmethod
    def find_version_directories(base_path: str | Path) -> list[tuple[int, str]]:
        """Find all version directories in a path.

        Uses caching to avoid repeated directory scans for the same path.

        Args:
            base_path: Path to search for version directories

        Returns:
            List of (version_number, version_string) tuples sorted by version
        """
        if not PathUtils.validate_path_exists(base_path, "Version search path"):
            return []

        path_str = str(base_path)
        current_time = time.time()

        # Check cache first - use the longer TTL for version cache too
        if path_str in VersionUtils._version_cache:
            version_dirs, timestamp = VersionUtils._version_cache[path_str]
            if current_time - timestamp < _PATH_CACHE_TTL:  # Use same TTL as path cache
                return version_dirs.copy()  # Return a copy to prevent modification

        path_obj = Path(base_path) if isinstance(base_path, str) else base_path
        version_dirs: list[tuple[int, str]] = []

        try:
            for item in path_obj.iterdir():
                if item.is_dir():
                    match = VersionUtils.VERSION_PATTERN.match(item.name)
                    if match:
                        version_num = int(match.group(1))
                        version_dirs.append((version_num, item.name))
        except (OSError, PermissionError) as e:
            logger.warning(f"Error scanning for version directories in {path_obj}: {e}")
            return []

        # Sort by version number
        version_dirs.sort(key=lambda x: x[0])

        # Cache the result
        VersionUtils._version_cache[path_str] = (version_dirs.copy(), current_time)

        # Clean cache if it gets too large - increased from 100 to 500
        if len(VersionUtils._version_cache) > 500:
            VersionUtils._cleanup_version_cache()

        return version_dirs

    @staticmethod
    def _cleanup_version_cache():
        """Clean expired entries from version cache.

        Optimized to keep frequently accessed version directories.
        """
        # Only clean if cache is significantly over limit
        if len(VersionUtils._version_cache) <= 250:
            return

        # Sort by timestamp to keep most recently accessed
        sorted_items = sorted(
            VersionUtils._version_cache.items(),
            key=lambda x: x[1][1],  # Sort by timestamp
            reverse=True,  # Most recent first
        )

        # Keep the most recent 250 entries
        VersionUtils.clear_version_cache()
        for key, value in sorted_items[:250]:
            VersionUtils._version_cache[key] = value

        logger.debug(
            f"Cleaned version cache, kept {len(VersionUtils._version_cache)} most recent entries",
        )

    @staticmethod
    def get_latest_version(base_path: str | Path) -> str | None:
        """Get the latest version directory name.

        Args:
            base_path: Path to search for version directories

        Returns:
            Latest version string (e.g., "v003") or None if none found
        """
        version_dirs = VersionUtils.find_version_directories(base_path)
        if not version_dirs:
            logger.debug(f"No version directories found in {base_path}")
            return None

        latest_version = version_dirs[-1][
            1
        ]  # Get the version string from the last (highest) version
        logger.debug(f"Found latest version {latest_version} in {base_path}")
        return latest_version

    @staticmethod
    @lru_cache(maxsize=256)
    def extract_version_from_path(path: str | Path) -> str | None:
        """Extract version from a file or directory path.

        Uses LRU cache since this operation is pure and frequently called.

        Args:
            path: Path that may contain version information

        Returns:
            Version string if found, None otherwise
        """
        path_str = str(path)
        match = re.search(r"(v\d{3})", path_str)
        if match:
            return match.group(1)
        return None


class FileUtils:
    """Utilities for file operations and validation."""

    @staticmethod
    def find_files_by_extension(
        directory: str | Path,
        extensions: str | list[str],
        limit: int | None = None,
    ) -> list[Path]:
        """Find files with specific extensions in a directory.

        This method performs optimized file discovery with early termination
        when limits are reached and uses set-based lookups for extension
        matching to achieve O(1) performance per file check.

        Args:
            directory: Directory path to search. Accepts both string paths
                and pathlib.Path objects for flexibility.
            extensions: File extension(s) to match. Can be a single extension
                string like "jpg" or ".jpg", or a list of extensions like
                ["jpg", "jpeg", "png"]. Leading dots are optional and normalized.
            limit: Maximum number of matching files to return. If None,
                returns all matching files. Used for performance optimization
                in large directories.

        Returns:
            list[Path]: List of pathlib.Path objects for all matching files.
                Returns empty list if directory doesn't exist or no matches found.
                Results are ordered by directory iteration order (not sorted).

        Raises:
            No exceptions are raised. Permission errors and OS errors are
            caught and logged as warnings, returning partial results.

        Examples:
            Single extension search:
                >>> files = FileUtils.find_files_by_extension("/tmp", "txt")
                >>> assert all(f.suffix == ".txt" for f in files)

            Multiple extensions with limit:
                >>> images = FileUtils.find_files_by_extension(
                ...     Path("/images"), ["jpg", "jpeg", "png"], limit=10
                ... )
                >>> assert len(images) <= 10

            Type-safe directory handling:
                >>> from pathlib import Path
                >>> path_obj = Path("/some/directory")
                >>> string_path = "/some/directory"
                >>> # Both work identically due to str | Path type
                >>> files1 = FileUtils.find_files_by_extension(path_obj, "py")
                >>> files2 = FileUtils.find_files_by_extension(string_path, "py")

        Performance:
            - O(n) time complexity where n is number of files in directory
            - Early termination when limit is reached reduces actual runtime
            - Set-based extension lookup provides O(1) extension matching
            - Path validation uses TTL caching to avoid repeated stat calls
        """
        if not PathUtils.validate_path_exists(directory, "Search directory"):
            return []

        # Normalize extensions to set for O(1) lookup
        if isinstance(extensions, str):
            extensions = [extensions]

        normalized_extensions: set[str] = set()
        for ext in extensions:
            if not ext.startswith("."):
                ext = "." + ext
            normalized_extensions.add(ext.lower())

        dir_path = Path(directory) if isinstance(directory, str) else directory
        matching_files: list[Path] = []

        try:
            # Use iterdir() but with early termination optimization
            for file_path in dir_path.iterdir():
                # Check is_file() first as it's usually faster than suffix check
                if file_path.is_file():
                    if file_path.suffix.lower() in normalized_extensions:
                        matching_files.append(file_path)
                        # Early termination if limit reached
                        if limit and len(matching_files) >= limit:
                            break
        except (OSError, PermissionError) as e:
            logger.warning(f"Error scanning directory {dir_path}: {e}")

        return matching_files

    @staticmethod
    def get_first_image_file(
        directory: str | Path,
        allow_fallback: bool = True,
    ) -> Path | None:
        """Get the first image file found in a directory.

        Args:
            directory: Directory to search
            allow_fallback: If True, will check heavy formats (EXR, TIFF) as fallback

        Returns:
            Path to first image file or None if none found
        """
        # First try lightweight preferred extensions
        for ext in Config.THUMBNAIL_EXTENSIONS:
            files = FileUtils.find_files_by_extension(directory, ext, limit=1)
            if files:
                return files[0]

        # If no lightweight formats found and fallback allowed, try heavy formats
        if allow_fallback and hasattr(Config, "THUMBNAIL_FALLBACK_EXTENSIONS"):
            for ext in Config.THUMBNAIL_FALLBACK_EXTENSIONS:
                files = FileUtils.find_files_by_extension(directory, ext, limit=1)
                if files:
                    # Check file size before returning
                    file_path = files[0]
                    max_size_mb = getattr(Config, "THUMBNAIL_MAX_DIRECT_SIZE_MB", 10)
                    if FileUtils.validate_file_size(file_path, max_size_mb):
                        logger.debug(
                            f"Using fallback {ext} file as thumbnail: {file_path.name}",
                        )
                        return file_path
                    logger.debug(
                        f"Fallback {ext} file too large for direct loading: {file_path.name}",
                    )
                    # Still return it - let cache_manager handle resizing
                    return file_path

        return None

    @staticmethod
    def validate_file_size(
        file_path: str | Path,
        max_size_mb: int | None = None,
    ) -> bool:
        """Validate that a file is not too large.

        Args:
            file_path: Path to file to check
            max_size_mb: Maximum size in megabytes (uses Config.MAX_FILE_SIZE_MB if None)

        Returns:
            True if file is within size limit, False otherwise
        """
        if max_size_mb is None:
            max_size_mb = Config.MAX_FILE_SIZE_MB

        if not PathUtils.validate_path_exists(file_path, "File"):
            return False

        path_obj = Path(file_path) if isinstance(file_path, str) else file_path
        try:
            size_bytes = path_obj.stat().st_size
            size_mb = size_bytes / (1024 * 1024)

            if size_mb > max_size_mb:
                logger.warning(
                    f"File too large ({size_mb:.1f}MB > {max_size_mb}MB): {path_obj}",
                )
                return False

            return True
        except (OSError, IOError) as e:
            logger.warning(f"Error checking file size for {path_obj}: {e}")
            return False


class ImageUtils:
    """Utilities for image validation and processing."""

    @staticmethod
    def validate_image_dimensions(
        width: int,
        height: int,
        max_dimension: int | None = None,
        max_memory_mb: int | None = None,
    ) -> bool:
        """Validate image dimensions and estimated memory usage.

        Args:
            width: Image width in pixels
            height: Image height in pixels
            max_dimension: Maximum allowed dimension (uses Config.MAX_THUMBNAIL_DIMENSION_PX if None)
            max_memory_mb: Maximum estimated memory usage in MB (uses Config.MAX_THUMBNAIL_MEMORY_MB if None)

        Returns:
            True if dimensions are acceptable, False otherwise
        """
        if max_dimension is None:
            max_dimension = Config.MAX_THUMBNAIL_DIMENSION_PX
        if max_memory_mb is None:
            max_memory_mb = Config.MAX_THUMBNAIL_MEMORY_MB

        # Check individual dimensions
        if width > max_dimension or height > max_dimension:
            logger.warning(
                f"Image dimensions too large ({width}x{height} > {max_dimension})",
            )
            return False

        # Estimate memory usage (4 bytes per pixel for RGBA)
        estimated_memory_bytes = width * height * 4
        estimated_memory_mb = estimated_memory_bytes / (1024 * 1024)

        if estimated_memory_mb > max_memory_mb:
            logger.warning(
                f"Estimated image memory usage too high ({estimated_memory_mb:.1f}MB > {max_memory_mb}MB)",
            )
            return False

        return True

    @staticmethod
    def get_safe_dimensions_for_thumbnail(
        max_size: int | None = None,
    ) -> tuple[int, int]:
        """Get safe dimensions for thumbnail generation.

        Args:
            max_size: Maximum dimension for thumbnail (uses Config.CACHE_THUMBNAIL_SIZE if None)

        Returns:
            (width, height) tuple for safe thumbnail dimensions
        """
        if max_size is None:
            max_size = Config.CACHE_THUMBNAIL_SIZE
        return (max_size, max_size)


class ValidationUtils:
    """Common validation utilities."""

    @staticmethod
    def validate_not_empty(
        *values: str | None,
        names: list[str] | None = None,
    ) -> bool:
        """Validate that values are not None or empty strings.

        Args:
            *values: Values to validate
            names: Optional names for logging (must match length of values)

        Returns:
            True if all values are non-empty, False otherwise
        """
        if names and len(names) != len(values):
            raise ValueError("Names list must match values length")

        for i, value in enumerate(values):
            if not value:
                name = names[i] if names else f"value {i}"
                logger.warning(f"Empty or None {name}")
                return False

        return True

    @staticmethod
    def validate_shot_components(show: str, sequence: str, shot: str) -> bool:
        """Validate shot component strings.

        Args:
            show: Show name
            sequence: Sequence name
            shot: Shot name

        Returns:
            True if all components are valid, False otherwise
        """
        return ValidationUtils.validate_not_empty(
            show,
            sequence,
            shot,
            names=["show", "sequence", "shot"],
        )

    @staticmethod
    def get_current_username() -> str:
        """Get the current username from environment.

        Returns:
            Current username, falling back to Config.DEFAULT_USERNAME if not found
        """
        # Try multiple environment variables in order of preference
        for env_var in ["USER", "USERNAME", "LOGNAME"]:
            username = os.environ.get(env_var)
            if username:
                logger.debug(f"Found username '{username}' from ${env_var}")
                return username

        # Fallback to config default
        logger.debug(
            f"No username found in environment, using default: {Config.DEFAULT_USERNAME}",
        )
        return Config.DEFAULT_USERNAME

    @staticmethod
    def get_excluded_users(additional_users: set[str] | None = None) -> set[str]:
        """Get set of users to exclude from searches.

        Automatically excludes the current user and any additional specified users.

        Args:
            additional_users: Additional users to exclude beyond current user

        Returns:
            Set of usernames to exclude
        """
        excluded = {ValidationUtils.get_current_username()}

        if additional_users:
            excluded.update(additional_users)

        logger.debug(f"Excluding users: {excluded}")
        return excluded
