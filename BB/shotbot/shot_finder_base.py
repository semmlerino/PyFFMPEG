"""Base class for shot finder implementations.

This module provides common functionality for all shot finders,
eliminating duplication between targeted and previous shot finders.
"""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from config import Config
from optimized_shot_parser import OptimizedShotParser
from shot_model import Shot

logger = logging.getLogger(__name__)


class ShotFinderBase(ABC):
    """Abstract base class for shot finders with common functionality."""

    def __init__(self, username: str | None = None) -> None:
        """Initialize the shot finder with sanitized username.

        Args:
            username: Username to search for. If None, uses current user.
        """
        # Get raw username
        raw_username = username or os.environ.get("USER") or os.getlogin()

        # Sanitize username to prevent path traversal attacks
        self.username = self._sanitize_username(raw_username)
        self.user_path_pattern = f"/user/{self.username}"

        # Use OptimizedShotParser for improved performance
        self._parser = OptimizedShotParser()

        # Progress tracking
        self._stop_requested = False
        self._progress_callback: Callable[[int, int, str], None] | None = None

        logger.info(f"{self.__class__.__name__} initialized for user: {self.username}")

    @staticmethod
    def _sanitize_username(raw_username: str) -> str:
        """Sanitize username to prevent security issues.

        Args:
            raw_username: Raw username input

        Returns:
            Sanitized username

        Raises:
            ValueError: If username is invalid after sanitization
        """
        # Remove any path traversal characters (., /, \)
        username = re.sub(r"[./\\]", "", raw_username)

        # Validate that username is not empty after sanitization
        if not username:
            raise ValueError(f"Invalid username after sanitization: '{raw_username}'")

        # Additional validation: username should only contain alphanumeric, dash, and underscore
        if not re.match(r"^[a-zA-Z0-9_-]+$", username):
            raise ValueError(f"Username contains invalid characters: '{username}'")

        return username

    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """Set callback for progress reporting.

        Args:
            callback: Function to call with (current, total, message) args
        """
        self._progress_callback = callback

    def request_stop(self) -> None:
        """Request the search to stop."""
        self._stop_requested = True
        logger.info(f"Stop requested for {self.__class__.__name__}")

    def _report_progress(self, current: int, total: int, message: str) -> None:
        """Report progress if callback is set.

        Args:
            current: Current progress value
            total: Total progress value
            message: Progress message
        """
        if self._progress_callback:
            self._progress_callback(current, total, message)

    def _parse_shot_from_path(self, path: str) -> Shot | None:
        """Parse shot information from a filesystem path.

        Args:
            path: Path containing shot information

        Returns:
            Shot object if path is valid, None otherwise
        """
        # Use OptimizedShotParser for better performance
        result = self._parser.parse_shot_path(path)
        if not result:
            return None

        # Validate shot is not empty
        if not result.shot:
            logger.debug(f"Empty shot extracted from path {path}")
            return None

        try:
            return Shot(
                show=result.show,
                sequence=result.sequence,
                shot=result.shot,
                workspace_path=result.workspace_path,
            )
        except Exception as e:
            logger.debug(f"Could not create Shot from path {path}: {e}")
            return None

    def get_shot_details(self, shot: Shot) -> dict[str, Any]:
        """Get additional details about a shot.

        Args:
            shot: Shot to get details for

        Returns:
            Dictionary with shot details including paths and metadata
        """
        details = {
            "show": shot.show,
            "sequence": shot.sequence,
            "shot": shot.shot,
            "workspace_path": shot.workspace_path,
            "user_path": f"{shot.workspace_path}{self.user_path_pattern}",
            "status": self._get_shot_status(shot),
        }

        # Check if user directory still exists
        user_dir = Path(details["user_path"])
        details["user_dir_exists"] = str(user_dir.exists())

        # Check for common VFX work files
        if user_dir.exists():
            details["has_3de"] = str(any(user_dir.rglob("*.3de")))
            details["has_nuke"] = str(any(user_dir.rglob("*.nk")))
            details["has_maya"] = str(any(user_dir.rglob("*.m[ab]")))

            # Look for thumbnails
            thumbnail_path = self._find_thumbnail_for_shot(shot)
            if thumbnail_path:
                details["thumbnail_path"] = str(thumbnail_path)

        return details

    def _find_thumbnail_for_shot(self, shot: Shot) -> Path | None:
        """Find thumbnail for a shot using same logic as Shot class.

        Args:
            shot: Shot object to find thumbnail for

        Returns:
            Path to thumbnail or None if not found
        """
        from utils import FileUtils, PathUtils

        try:
            # Try editorial thumbnail first
            editorial_dir = Path(shot.workspace_path) / "publish" / "editorial"
            if editorial_dir.exists():
                thumbnail = FileUtils.get_first_image_file(editorial_dir)
                if thumbnail:
                    return thumbnail

            # Fall back to turnover plate thumbnails
            thumbnail = PathUtils.find_turnover_plate_thumbnail(
                Config.SHOWS_ROOT,
                shot.show,
                shot.sequence,
                shot.shot,
            )
            if thumbnail:
                return thumbnail

            # Third fallback: any EXR with 1001 in publish folder
            thumbnail = PathUtils.find_any_publish_thumbnail(
                Config.SHOWS_ROOT,
                shot.show,
                shot.sequence,
                shot.shot,
            )
            return thumbnail

        except Exception as e:
            logger.debug(f"Error finding thumbnail for {shot.full_name}: {e}")
            return None

    @abstractmethod
    def _get_shot_status(self, shot: Shot) -> str:
        """Get the status of a shot (to be implemented by subclasses).

        Args:
            shot: Shot to get status for

        Returns:
            Status string (e.g., "approved", "active")
        """
        pass

    @abstractmethod
    def find_shots(self, **kwargs) -> list[Shot]:
        """Find shots based on implementation-specific logic.

        To be implemented by concrete subclasses.

        Returns:
            List of found shots
        """
        pass
