"""Finder for the latest 3DE scene files in a workspace."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class ThreeDELatestFinder:
    """Finds the latest 3DE scene file in a workspace."""

    # Pattern to match version in 3DE filenames (e.g., _v001, _v002)
    VERSION_PATTERN = re.compile(r"_v(\d{3})\.3de$")

    @staticmethod
    def find_latest_threede_scene(
        workspace_path: str,
        shot_name: str | None = None,
    ) -> Path | None:
        """Find the latest 3DE scene file in a workspace.

        Searches for 3DE files in the standard VFX directory structure:
        /shows/{show}/shots/{sequence}/{shot}/user/*/mm/3de/mm-default/scenes/scene/*/*.3de

        Args:
            workspace_path: Full path to the shot workspace
            shot_name: Optional shot name for better logging

        Returns:
            Path to the latest 3DE scene file, or None if not found
        """
        if not workspace_path:
            logger.debug("No workspace path provided")
            return None

        workspace = Path(workspace_path)
        if not workspace.exists():
            logger.debug(f"Workspace does not exist: {workspace_path}")
            return None

        # Search pattern: user/*/mm/3de/mm-default/scenes/scene/*/*.3de
        threede_files: list[tuple[Path, int]] = []

        # Search in all user directories
        user_base = workspace / "user"
        if not user_base.exists():
            logger.debug(f"No user directory in workspace: {workspace_path}")
            return None

        # Find all 3DE files
        for user_dir in user_base.iterdir():
            if not user_dir.is_dir():
                continue

            # Check for 3de directory structure
            threede_base = user_dir / "mm" / "3de" / "mm-default" / "scenes" / "scene"
            if not threede_base.exists():
                continue

            # Search for .3de files in subdirectories (plates)
            for plate_dir in threede_base.iterdir():
                if not plate_dir.is_dir():
                    continue

                for threede_file in plate_dir.glob("*.3de"):
                    # Extract version number from filename
                    version = ThreeDELatestFinder._extract_version(threede_file)
                    if version is not None:
                        threede_files.append((threede_file, version))
                        logger.debug(
                            f"Found 3DE file: {threede_file.name} (v{version:03d})"
                        )

        if not threede_files:
            logger.debug(
                f"No 3DE files found in workspace: {shot_name or workspace_path}"
            )
            return None

        # Sort by version number and get the latest
        threede_files.sort(key=lambda x: x[1])
        latest_file = threede_files[-1][0]

        logger.info(
            f"Found latest 3DE scene for {shot_name or 'shot'}: {latest_file.name}"
        )
        return latest_file

    @staticmethod
    def _extract_version(file_path: Path) -> int | None:
        """Extract version number from a 3DE filename.

        Args:
            file_path: Path to the 3DE file

        Returns:
            Version number as integer, or None if not found
        """
        match = ThreeDELatestFinder.VERSION_PATTERN.search(file_path.name)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                logger.debug(f"Could not parse version from: {file_path.name}")
        return None

    @staticmethod
    def find_all_threede_scenes(
        workspace_path: str,
    ) -> list[Path]:
        """Find all 3DE scene files in a workspace.

        Args:
            workspace_path: Full path to the shot workspace

        Returns:
            List of all 3DE scene file paths, sorted by version
        """
        if not workspace_path:
            return []

        workspace = Path(workspace_path)
        if not workspace.exists():
            return []

        threede_files: list[tuple[Path, int]] = []

        # Search in all user directories
        user_base = workspace / "user"
        if not user_base.exists():
            return []

        # Find all 3DE files
        for user_dir in user_base.iterdir():
            if not user_dir.is_dir():
                continue

            # Check for 3de directory structure
            threede_base = user_dir / "mm" / "3de" / "mm-default" / "scenes" / "scene"
            if not threede_base.exists():
                continue

            # Search for .3de files in subdirectories
            for plate_dir in threede_base.iterdir():
                if not plate_dir.is_dir():
                    continue

                for threede_file in plate_dir.glob("*.3de"):
                    version = ThreeDELatestFinder._extract_version(threede_file)
                    if version is not None:
                        threede_files.append((threede_file, version))

        # Sort by version and return paths only
        threede_files.sort(key=lambda x: x[1])
        return [f[0] for f in threede_files]
