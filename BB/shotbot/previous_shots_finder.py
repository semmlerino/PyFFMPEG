"""Finder for previous/approved shots that user has worked on."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from shot_model import Shot

logger = logging.getLogger(__name__)


class PreviousShotsFinder:
    """Finds shots that user has worked on but are no longer active.

    This class scans the filesystem for shots containing user work directories
    and filters out currently active shots to show only approved/completed ones.
    """

    def __init__(self, username: str | None = None):
        """Initialize the previous shots finder.

        Args:
            username: Username to search for. If None, uses current user.
        """
        # Get raw username
        raw_username = username or os.environ.get("USER") or os.getlogin()

        # SECURITY FIX: Sanitize username to prevent path traversal attacks
        # Remove any path traversal characters (., /, \)
        self.username = re.sub(r"[./\\]", "", raw_username)

        # Validate that username is not empty after sanitization
        if not self.username:
            raise ValueError(f"Invalid username after sanitization: '{raw_username}'")

        # Additional validation: username should only contain alphanumeric, dash, and underscore
        if not re.match(r"^[a-zA-Z0-9_-]+$", self.username):
            raise ValueError(f"Username contains invalid characters: '{self.username}'")

        self.user_path_pattern = f"/user/{self.username}"
        self._shot_pattern = re.compile(r"/shows/([^/]+)/shots/([^/]+)/([^/]+)/")
        logger.info(f"PreviousShotsFinder initialized for user: {self.username}")

    def find_user_shots(self, shows_root: Path = Path("/shows")) -> list[Shot]:
        """Find all shots that contain user work directories.

        Args:
            shows_root: Root directory to search for shots.

        Returns:
            List of Shot objects where user has work directories.
        """
        shots = []

        if not shows_root.exists():
            logger.warning(f"Shows root does not exist: {shows_root}")
            return shots

        try:
            # Use find command for efficient filesystem traversal
            # Look for directories matching */user/{username}
            cmd = [
                "find",
                str(shows_root),
                "-type",
                "d",
                "-path",
                f"*{self.user_path_pattern}",
                "-maxdepth",
                "8",  # Limit depth for performance
            ]

            logger.debug(f"Running find command: {' '.join(cmd)}")

            # SECURITY FIX: Use stderr=subprocess.DEVNULL instead of shell redirection
            # Note: Can't use capture_output=True with stderr=subprocess.DEVNULL
            # Increased timeout to 120 seconds for large filesystem searches
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,  # Capture stdout explicitly
                stderr=subprocess.DEVNULL,  # Suppress stderr
                text=True,
                timeout=120,  # Increased from 30 to 120 seconds
                shell=False,
            )

            if result.returncode != 0:
                logger.warning(
                    f"Find command returned non-zero exit code: {result.returncode}"
                )

            # Parse each found path to extract shot information
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                shot = self._parse_shot_from_path(line)
                if shot and shot not in shots:
                    shots.append(shot)

            logger.info(f"Found {len(shots)} shots with user work")

        except subprocess.TimeoutExpired:
            logger.error("Find command timed out after 120 seconds")
        except Exception as e:
            logger.error(f"Error finding user shots: {e}")

        return shots

    def _parse_shot_from_path(self, path: str) -> Shot | None:
        """Parse shot information from a filesystem path.

        Args:
            path: Path containing shot information.

        Returns:
            Shot object if path is valid, None otherwise.
        """
        match = self._shot_pattern.search(path)
        if match:
            show, sequence, shot_name = match.groups()

            # Build the workspace path
            workspace_path = f"/shows/{show}/shots/{sequence}/{shot_name}"

            try:
                return Shot(
                    show=show,
                    sequence=sequence,
                    shot=shot_name,
                    workspace_path=workspace_path,
                )
            except Exception as e:
                logger.debug(f"Could not create Shot from path {path}: {e}")

        return None

    def filter_approved_shots(
        self, all_user_shots: list[Shot], active_shots: list[Shot]
    ) -> list[Shot]:
        """Filter out active shots to get only approved/completed ones.

        Args:
            all_user_shots: All shots where user has work.
            active_shots: Currently active shots from workspace.

        Returns:
            List of approved shots (user shots minus active shots).
        """
        # Create a set of active shot identifiers for efficient lookup
        active_ids = {(shot.show, shot.sequence, shot.shot) for shot in active_shots}

        # Filter out active shots
        approved_shots = [
            shot
            for shot in all_user_shots
            if (shot.show, shot.sequence, shot.shot) not in active_ids
        ]

        logger.info(
            f"Filtered {len(all_user_shots)} user shots to "
            f"{len(approved_shots)} approved shots"
        )

        return approved_shots

    def find_approved_shots(
        self, active_shots: list[Shot], shows_root: Path = Path("/shows")
    ) -> list[Shot]:
        """Find all approved shots for the user.

        This is a convenience method that combines finding user shots
        and filtering out active ones.

        Args:
            active_shots: Currently active shots from workspace.
            shows_root: Root directory to search for shots.

        Returns:
            List of approved/completed shots.
        """
        all_user_shots = self.find_user_shots(shows_root)
        return self.filter_approved_shots(all_user_shots, active_shots)

    def get_shot_details(self, shot: Shot) -> dict[str, Any]:
        """Get additional details about an approved shot.

        Args:
            shot: Shot to get details for.

        Returns:
            Dictionary with shot details including paths and metadata.
        """
        details = {
            "show": shot.show,
            "sequence": shot.sequence,
            "shot": shot.shot,
            "workspace_path": shot.workspace_path,
            "user_path": f"{shot.workspace_path}{self.user_path_pattern}",
            "status": "approved",  # These are all approved shots
        }

        # Check if user directory still exists
        user_dir = Path(details["user_path"])
        details["user_dir_exists"] = str(user_dir.exists())

        # Check for common VFX work files
        if user_dir.exists():
            details["has_3de"] = str(any(user_dir.rglob("*.3de")))
            details["has_nuke"] = str(any(user_dir.rglob("*.nk")))
            details["has_maya"] = str(any(user_dir.rglob("*.m[ab]")))

        return details
