"""Storage backend for atomic file operations and directory management."""

from __future__ import annotations

# Standard library imports
import json
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Standard library imports
    from collections.abc import Callable

    # Local application imports
    from type_definitions import ValidationResultDict

    from .memory_manager import MemoryManager
    from .thumbnail_manager import ThumbnailManager

# Platform-specific file locking
if sys.platform == "win32":
    # Standard library imports
    import msvcrt
else:
    import fcntl

# Local application imports
from error_handling_mixin import ErrorHandlingMixin
from logging_mixin import LoggingMixin


class StorageBackend(ErrorHandlingMixin, LoggingMixin):
    """Handles atomic file I/O operations and directory management for caching.

    This class provides thread-safe file operations with proper error handling,
    atomic writes using temporary files, and robust directory creation with
    fallback mechanisms.
    """

    def __init__(self) -> None:
        """Initialize storage backend."""
        self._fallback_directories: dict[Path, Path] = {}  # Maps original to fallback

    def ensure_directory(self, directory: Path, max_retries: int = 3) -> bool:
        """Ensure directory exists, creating it if necessary with fallback.

        Args:
            directory: Directory path to create
            max_retries: Maximum number of creation attempts

        Returns:
            True if directory exists or was created successfully
        """
        for attempt in range(max_retries):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"Ensured directory exists: {directory}")
                return True

            except (OSError, PermissionError) as e:
                self.logger.error(
                    f"Failed to create directory (attempt {attempt + 1}/{max_retries}): {e}"
                )

                if attempt == max_retries - 1:
                    # Last attempt failed, try fallback temp directory
                    try:
                        fallback_dir = Path(tempfile.mkdtemp(prefix="shotbot_cache_"))
                        self.logger.warning(f"Using fallback directory: {fallback_dir}")
                        # Store the fallback directory mapping
                        self._fallback_directories[directory] = fallback_dir
                        self.logger.info(
                            f"Mapped {directory} -> {fallback_dir} for fallback"
                        )
                        return True

                    except Exception as fallback_error:
                        self.logger.critical(
                            f"Failed to create fallback directory: {fallback_error}"
                        )
                        return False

            except Exception as e:
                self.logger.exception(f"Unexpected error creating directory: {e}")
                if attempt == max_retries - 1:
                    return False

        return False

    def get_actual_directory(self, requested_directory: Path) -> Path:
        """Get the actual directory being used (original or fallback).

        Args:
            requested_directory: The originally requested directory

        Returns:
            The actual directory path being used (may be a fallback)
        """
        return self._fallback_directories.get(requested_directory, requested_directory)

    def write_json(
        self, file_path: Path, data: dict[str, Any], indent: int = 2
    ) -> bool:
        """Write JSON data to file using atomic operation.

        Uses a temporary file with UUID suffix to ensure atomicity.
        If the write succeeds, the temp file is atomically moved to the target.

        Args:
            file_path: Target file path
            data: Dictionary data to write as JSON
            indent: JSON indentation level

        Returns:
            True if write succeeded, False otherwise
        """
        if not data:
            self.logger.warning(f"Attempted to write empty data to {file_path}")
            return False

        # Ensure parent directory exists and get actual path
        if not self.ensure_directory(file_path.parent):
            self.logger.error(f"Failed to create parent directory for {file_path}")
            return False

        # Use actual directory (may be fallback)
        actual_parent = self.get_actual_directory(file_path.parent)
        actual_file_path = actual_parent / file_path.name

        # Update file_path to use actual directory
        file_path = actual_file_path

        # Create lock file for synchronization
        lock_file = file_path.with_suffix(".lock")
        lock_fd = None

        # Create unique temporary file to avoid collisions
        temp_file = file_path.with_suffix(f".tmp_{uuid.uuid4().hex[:8]}")

        try:
            # Acquire exclusive lock
            lock_fd = open(lock_file, "w")

            if sys.platform == "win32":
                # Windows file locking with timeout
                max_wait = 5.0  # 5 second timeout
                start_time = time.time()
                while True:
                    try:
                        msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.time() - start_time > max_wait:
                            raise TimeoutError("Failed to acquire file lock")
                        time.sleep(0.01)
            else:
                # Unix file locking (Linux, Mac)
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)

            # Write to temporary file first (while holding lock)
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)

            # Atomic move to final location (while holding lock)
            temp_file.replace(file_path)

            self.logger.debug(f"Successfully wrote JSON data to {file_path}")
            return True

        except OSError as e:
            self.logger.error(f"I/O error writing JSON to {file_path}: {e}")
            self._cleanup_temp_file(temp_file)
            return False

        except (TypeError, ValueError) as e:
            self.logger.error(f"JSON serialization error for {file_path}: {e}")
            self._cleanup_temp_file(temp_file)
            return False

        except Exception as e:
            self.logger.exception(f"Unexpected error writing JSON to {file_path}: {e}")
            self._cleanup_temp_file(temp_file)
            return False

        finally:
            # Always release the lock and close the lock file
            if lock_fd:
                try:
                    if sys.platform == "win32":
                        msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass  # Best effort unlock
                finally:
                    lock_fd.close()
                    # Clean up lock file (best effort)
                    try:
                        lock_file.unlink()
                    except Exception:
                        pass

    def atomic_update_json(
        self,
        file_path: Path,
        update_func: Callable[[dict[str, Any] | None], dict[str, Any]],
        default: dict[str, Any] | None = None,
    ) -> bool:
        """Atomically read, update, and write JSON data.

        This method ensures the entire read-modify-write cycle is atomic,
        preventing race conditions when multiple threads update the same file.

        Args:
            file_path: Target file path
            update_func: Function that takes current data and returns updated data
            default: Default data if file doesn't exist

        Returns:
            True if update succeeded, False otherwise
        """
        # Ensure parent directory exists first
        if not self.ensure_directory(file_path.parent):
            return False

        # Use actual directory (may be fallback) consistently
        actual_parent = self.get_actual_directory(file_path.parent)
        actual_file_path = actual_parent / file_path.name

        # Create lock file for synchronization
        lock_file = actual_file_path.with_suffix(".lock")
        lock_fd = None

        try:
            # Acquire exclusive lock for entire operation
            lock_fd = open(lock_file, "w")

            if sys.platform == "win32":
                # Windows file locking with timeout
                max_wait = 5.0
                start_time = time.time()
                while True:
                    try:
                        msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.time() - start_time > max_wait:
                            raise TimeoutError("Failed to acquire file lock")
                        time.sleep(0.01)
            else:
                # Unix file locking
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)

            # Read current data (while holding lock) - use actual path
            current_data = (
                self.read_json(actual_file_path)
                if actual_file_path.exists()
                else default
            )

            # Apply update function
            new_data = update_func(current_data)

            # Write updated data directly (we already hold the lock)
            # Create unique temporary file
            temp_file = actual_file_path.with_suffix(f".tmp_{uuid.uuid4().hex[:8]}")

            try:
                # Write to temporary file
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(new_data, f, indent=2, ensure_ascii=False)

                # Atomic move to final location
                temp_file.replace(actual_file_path)
                return True

            except Exception:
                self._cleanup_temp_file(temp_file)
                return False

        except Exception as e:
            self.logger.exception(f"Error in atomic update for {file_path}: {e}")
            return False

        finally:
            # Release lock
            if lock_fd:
                try:
                    if sys.platform == "win32":
                        msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                finally:
                    lock_fd.close()
                    try:
                        lock_file.unlink()
                    except Exception:
                        pass

    def read_json(self, file_path: Path) -> dict[str, Any] | None:
        """Read JSON data from file with comprehensive error handling.

        Args:
            file_path: File path to read from

        Returns:
            Dictionary data if successful, None if failed
        """
        # Use EAFP pattern to avoid race condition
        try:
            with open(file_path, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)

            # Validate that we got a dictionary
            if not isinstance(data, dict):
                self.logger.warning(
                    f"JSON file does not contain a dictionary: {file_path}"
                )
                return None

            self.logger.debug(f"Successfully read JSON data from {file_path}")
            return data

        except FileNotFoundError:
            self.logger.debug(f"JSON file not found: {file_path}")
            return None

        except PermissionError as e:
            self.logger.error(f"Permission denied reading {file_path}: {e}")
            return None

        except json.JSONDecodeError as e:
            self.logger.warning(f"Corrupted JSON file {file_path}: {e}")
            return None

        except OSError as e:
            self.logger.error(f"I/O error reading {file_path}: {e}")
            return None

        except Exception as e:
            self.logger.exception(f"Unexpected error reading {file_path}: {e}")
            return None

    def delete_file(self, file_path: Path) -> bool:
        """Safely delete a file with error handling.

        Args:
            file_path: File path to delete

        Returns:
            True if deleted successfully or file didn't exist
        """
        # Use EAFP pattern to avoid race condition
        try:
            file_path.unlink()
            self.logger.debug(f"Deleted file: {file_path}")
            return True

        except FileNotFoundError:
            # File already gone, that's fine
            return True

        except (OSError, PermissionError) as e:
            self.logger.error(f"Failed to delete file {file_path}: {e}")
            return False

        except Exception as e:
            self.logger.exception(f"Unexpected error deleting {file_path}: {e}")
            return False

    def move_file(self, source: Path, destination: Path) -> bool:
        """Move file atomically with error handling.

        Args:
            source: Source file path
            destination: Destination file path

        Returns:
            True if move succeeded
        """
        # Use EAFP pattern to avoid race condition
        try:
            # Ensure destination directory exists
            if not self.ensure_directory(destination.parent):
                return False

            source.replace(destination)
            self.logger.debug(f"Moved file: {source} -> {destination}")
            return True

        except FileNotFoundError:
            self.logger.error(f"Source file does not exist: {source}")
            return False

        except (OSError, PermissionError) as e:
            self.logger.error(f"Failed to move file {source} -> {destination}: {e}")
            return False

        except Exception as e:
            self.logger.exception(
                f"Unexpected error moving file {source} -> {destination}: {e}"
            )
            return False

    def get_file_size(self, file_path: Path) -> int | None:
        """Get file size in bytes with error handling.

        Args:
            file_path: File path to check

        Returns:
            File size in bytes, or None if failed
        """
        try:
            return file_path.stat().st_size

        except OSError as e:
            self.logger.debug(f"Failed to get size of {file_path}: {e}")
            return None

    # ============= Cache Validation Methods (from CacheValidator) =============

    def validate_cache(
        self,
        cache_directory: Path,
        memory_manager: MemoryManager | ThumbnailManager | None = None,
        fix_issues: bool = True,
    ) -> ValidationResultDict:
        """Validate cache consistency and optionally fix issues.

        Integrates validation logic from the original CacheValidator class.

        Args:
            cache_directory: Directory containing cached files to validate
            memory_manager: Optional memory manager to validate tracking
            fix_issues: If True, automatically fix issues found

        Returns:
            Dictionary with validation results and statistics
        """
        self.logger.info(f"Starting cache validation for {cache_directory}...")

        results: ValidationResultDict = {
            "valid": True,
            "issues_found": 0,
            "issues_fixed": 0,
            "orphaned_files": 0,
            "missing_files": 0,
            "size_mismatches": 0,
            "memory_usage_corrected": False,
            "details": [],
        }

        try:
            # Validate directory structure
            structure_results = self._validate_directory_structure(
                cache_directory, fix_issues
            )
            # Merge details properly to avoid overwriting
            results["details"].extend(structure_results.get("details", []))
            structure_results_copy = structure_results.copy()
            structure_results_copy.pop("details", None)
            results.update(structure_results_copy)

            # Validate memory tracking if memory manager provided
            if memory_manager is not None:
                memory_results = self._validate_memory_tracking(
                    memory_manager, fix_issues
                )
                # Merge details properly to avoid overwriting
                results["details"].extend(memory_results.get("details", []))
                memory_results_copy = memory_results.copy()
                memory_results_copy.pop("details", None)
                results.update(memory_results_copy)

                # Find orphaned files
                orphan_results = self._find_orphaned_files(
                    cache_directory, memory_manager, fix_issues
                )
                # Merge details properly to avoid overwriting
                results["details"].extend(orphan_results.get("details", []))
                orphan_results_copy = orphan_results.copy()
                orphan_results_copy.pop("details", None)
                results.update(orphan_results_copy)

            # Calculate final status
            total_issues = (
                results["missing_files"]
                + results["size_mismatches"]
                + results["orphaned_files"]
                + results.get("structure_issues", 0)
            )

            results["issues_found"] = total_issues
            results["valid"] = total_issues == 0

            if results["valid"]:
                self.logger.info("Cache validation passed - no issues found")
            else:
                self.logger.info(
                    f"Cache validation found {total_issues} issues, "
                    + f"fixed {results['issues_fixed']}"
                )

            return results

        except Exception as e:
            self.logger.error(f"Error during cache validation: {e}")
            return {
                "valid": False,
                "error": str(e),
                "issues_found": 0,
                "issues_fixed": 0,
            }

    def repair_cache(
        self,
        cache_directory: Path,
        memory_manager: MemoryManager | ThumbnailManager | None = None,
    ) -> ValidationResultDict:
        """Perform comprehensive cache repair operations.

        Args:
            cache_directory: Directory containing cached files to repair
            memory_manager: Optional memory manager for tracking validation

        Returns:
            Dictionary with repair results
        """
        self.logger.info(
            f"Starting comprehensive cache repair for {cache_directory}..."
        )
        return self.validate_cache(cache_directory, memory_manager, fix_issues=True)

    def get_cache_stats(
        self,
        cache_directory: Path,
        memory_manager: MemoryManager | ThumbnailManager | None = None,
    ) -> dict[str, Any]:
        """Get detailed cache statistics without making changes.

        Args:
            cache_directory: Directory containing cached files
            memory_manager: Optional memory manager for memory stats

        Returns:
            Dictionary with cache statistics
        """
        stats = {
            "cache_directory": str(cache_directory),
            "directory_exists": cache_directory.exists(),
        }

        # Add memory stats if memory manager provided
        if memory_manager:
            stats["memory_stats"] = memory_manager.get_usage_stats()

        if cache_directory.exists():
            # Count actual files on disk (look for common cache file types)
            cache_files = []
            for pattern in ["*.jpg", "*.jpeg", "*.png", "*.json"]:
                cache_files.extend(list(cache_directory.rglob(pattern)))

            stats["actual_file_count"] = len(cache_files)
            stats["actual_total_size_mb"] = sum(
                f.stat().st_size for f in cache_files if f.exists()
            ) / (1024 * 1024)

            # Directory structure info
            subdirs = [d for d in cache_directory.iterdir() if d.is_dir()]
            stats["subdirectories"] = len(subdirs)

            # File type breakdown
            file_types = {}
            for cache_file in cache_files:
                ext = cache_file.suffix.lower()
                file_types[ext] = file_types.get(ext, 0) + 1
            stats["file_types"] = file_types

        else:
            stats["actual_file_count"] = 0
            stats["actual_total_size_mb"] = 0
            stats["subdirectories"] = 0
            stats["file_types"] = {}

        return stats

    def clean_empty_directories(self, cache_directory: Path) -> int:
        """Remove empty subdirectories in the cache.

        Args:
            cache_directory: Directory to clean

        Returns:
            Number of directories removed
        """
        if not cache_directory.exists():
            return 0

        removed_count = 0

        # Find empty directories (bottom-up to handle nested empty dirs)
        for dirpath in sorted(cache_directory.rglob("*"), reverse=True):
            if not dirpath.is_dir():
                continue

            try:
                # Try to remove if empty
                if not any(dirpath.iterdir()):
                    dirpath.rmdir()
                    removed_count += 1
                    self.logger.debug(f"Removed empty directory: {dirpath}")
            except OSError as e:
                self.logger.debug(f"Failed to remove directory {dirpath}: {e}")

        if removed_count > 0:
            self.logger.info(f"Cleaned up {removed_count} empty directories")

        return removed_count

    def _validate_memory_tracking(
        self, memory_manager: MemoryManager | ThumbnailManager, fix_issues: bool
    ) -> dict[str, Any]:
        """Validate memory manager tracking accuracy.

        Args:
            memory_manager: Memory manager instance to validate
            fix_issues: Whether to fix issues found

        Returns:
            Dictionary with validation results
        """
        results = {
            "missing_files": 0,
            "size_mismatches": 0,
            "memory_usage_corrected": False,
            "details": [],
        }

        try:
            # Use the memory manager's validate_tracking method if available
            if hasattr(memory_manager, "validate_tracking"):
                validation_result = memory_manager.validate_tracking()

                results["missing_files"] = validation_result.get("invalid_files", 0)
                results["size_mismatches"] = validation_result.get("size_mismatches", 0)
                results["issues_fixed"] = validation_result.get("issues_fixed", 0)

                if validation_result.get("issues_fixed", 0) > 0:
                    results["memory_usage_corrected"] = True
                    results["details"].append(
                        f"Fixed {validation_result['issues_fixed']} memory tracking issues"
                    )
            else:
                self.logger.debug("Memory manager does not support validation")

        except Exception as e:
            self.logger.error(f"Error validating memory tracking: {e}")
            results["details"].append(f"Memory tracking validation failed: {e}")

        return results

    def _find_orphaned_files(
        self,
        cache_directory: Path,
        memory_manager: MemoryManager | ThumbnailManager,
        fix_issues: bool,
    ) -> dict[str, Any]:
        """Find cache files not being tracked by memory manager.

        Args:
            cache_directory: Directory containing cache files
            memory_manager: Memory manager instance
            fix_issues: Whether to add orphaned files to tracking

        Returns:
            Dictionary with orphan file results
        """
        results = {
            "orphaned_files": 0,
            "details": [],
        }

        if not cache_directory.exists():
            return results

        orphaned_files = []

        # Find all cache files (look for common extensions)
        for pattern in ["*.jpg", "*.jpeg", "*.png"]:
            for cache_file in cache_directory.rglob(pattern):
                if not cache_file.exists():
                    continue

                # Check if tracked by memory manager
                try:
                    if hasattr(
                        memory_manager, "is_item_tracked"
                    ) and not memory_manager.is_item_tracked(cache_file):
                        orphaned_files.append(cache_file)
                except Exception as e:
                    self.logger.debug(f"Error checking tracking for {cache_file}: {e}")

        results["orphaned_files"] = len(orphaned_files)

        if orphaned_files and fix_issues:
            fixed_count = 0
            for orphan_file in orphaned_files:
                try:
                    if hasattr(
                        memory_manager, "track_item"
                    ) and memory_manager.track_item(orphan_file):
                        fixed_count += 1
                except Exception as e:
                    self.logger.debug(
                        f"Failed to track orphaned file {orphan_file}: {e}"
                    )

            results["issues_fixed"] = fixed_count
            if fixed_count > 0:
                results["details"].append(
                    f"Added {fixed_count} orphaned files to tracking"
                )

        elif orphaned_files:
            results["details"].append(f"Found {len(orphaned_files)} orphaned files")

        return results

    def _validate_directory_structure(
        self, cache_directory: Path, fix_issues: bool
    ) -> dict[str, Any]:
        """Validate the cache directory structure.

        Args:
            cache_directory: Directory to validate
            fix_issues: Whether to fix structural issues

        Returns:
            Dictionary with structure validation results
        """
        results = {
            "structure_issues": 0,
            "details": [],
        }

        # Ensure main cache directory exists
        if not cache_directory.exists():
            if fix_issues:
                try:
                    if self.ensure_directory(cache_directory):
                        results["details"].append("Created missing cache directory")
                        results["issues_fixed"] = results.get("issues_fixed", 0) + 1
                    else:
                        results["structure_issues"] += 1
                        results["details"].append("Failed to create cache directory")
                except Exception as e:
                    results["structure_issues"] += 1
                    results["details"].append(f"Directory creation error: {e}")
            else:
                results["structure_issues"] += 1
                results["details"].append("Cache directory does not exist")

        return results

    def _cleanup_temp_file(self, temp_file: Path) -> None:
        """Clean up temporary file if it exists.

        Args:
            temp_file: Temporary file path to clean up
        """
        # Use EAFP pattern to avoid race condition
        try:
            temp_file.unlink()
            self.logger.debug(f"Cleaned up temporary file: {temp_file}")
        except FileNotFoundError:
            # Already gone, that's fine
            pass
        except OSError:
            self.logger.debug(f"Failed to clean up temporary file: {temp_file}")
