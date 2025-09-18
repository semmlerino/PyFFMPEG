"""Storage backend for atomic file operations and directory management."""

from __future__ import annotations

import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

from error_handling_mixin import ErrorHandlingMixin
from logging_mixin import LoggingMixin

logger = logging.getLogger(__name__)


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

        # Create unique temporary file to avoid collisions
        temp_file = file_path.with_suffix(f".tmp_{uuid.uuid4().hex[:8]}")

        try:
            # Write to temporary file first
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)

            # Atomic move to final location
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
