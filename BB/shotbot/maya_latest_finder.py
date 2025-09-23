"""Finder for the latest Maya scene files in a workspace."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class MayaLatestFinder:
    """Finds the latest Maya scene file in a workspace."""

    # Pattern to match version in Maya filenames (e.g., _v001, _v002)
    VERSION_PATTERN = re.compile(r"_v(\d{3})\.(ma|mb)$")

    @staticmethod
    def find_latest_maya_scene(
        workspace_path: str,
        shot_name: str | None = None,
    ) -> Path | None:
        """Find the latest Maya scene file in a workspace.

        Searches for Maya files (.ma and .mb) in the standard VFX directory structure:
        /shows/{show}/shots/{sequence}/{shot}/user/*/maya/scenes/*.ma
        /shows/{show}/shots/{sequence}/{shot}/user/*/maya/scenes/*.mb

        Args:
            workspace_path: Full path to the shot workspace
            shot_name: Optional shot name for better logging

        Returns:
            Path to the latest Maya scene file, or None if not found
        """
        if not workspace_path:
            logger.debug("No workspace path provided")
            return None

        workspace = Path(workspace_path)
        if not workspace.exists():
            logger.debug(f"Workspace does not exist: {workspace_path}")
            return None

        # Search pattern: user/*/maya/scenes/*.ma or *.mb
        maya_files: list[tuple[Path, int]] = []

        # Search in all user directories
        user_base = workspace / "user"
        if not user_base.exists():
            logger.debug(f"No user directory in workspace: {workspace_path}")
            return None

        # Find all Maya files
        for user_dir in user_base.iterdir():
            if not user_dir.is_dir():
                continue

            # Check for maya directory structure
            maya_scenes = user_dir / "maya" / "scenes"
            if not maya_scenes.exists():
                continue

            # Search for .ma and .mb files
            for maya_file in maya_scenes.glob("*.ma"):
                version = MayaLatestFinder._extract_version(maya_file)
                if version is not None:
                    maya_files.append((maya_file, version))
                    logger.debug(
                        f"Found Maya ASCII file: {maya_file.name} (v{version:03d})"
                    )

            for maya_file in maya_scenes.glob("*.mb"):
                version = MayaLatestFinder._extract_version(maya_file)
                if version is not None:
                    maya_files.append((maya_file, version))
                    logger.debug(
                        f"Found Maya Binary file: {maya_file.name} (v{version:03d})"
                    )

        if not maya_files:
            logger.debug(
                f"No Maya files found in workspace: {shot_name or workspace_path}"
            )
            return None

        # Sort by version number and get the latest
        maya_files.sort(key=lambda x: x[1])
        latest_file = maya_files[-1][0]

        logger.info(
            f"Found latest Maya scene for {shot_name or 'shot'}: {latest_file.name}"
        )
        return latest_file

    @staticmethod
    def _extract_version(file_path: Path) -> int | None:
        """Extract version number from a Maya filename.

        Args:
            file_path: Path to the Maya file

        Returns:
            Version number as integer, or None if not found
        """
        match = MayaLatestFinder.VERSION_PATTERN.search(file_path.name)
        if match:
            return int(match.group(1))

        # Also try without underscore (e.g., v001.ma)
        simple_pattern = re.compile(r"v(\d{3})\.(ma|mb)$")
        match = simple_pattern.search(file_path.name)
        if match:
            return int(match.group(1))

        return None

    @staticmethod
    def find_all_maya_scenes(
        workspace_path: str,
        include_autosave: bool = False,
    ) -> list[Path]:
        """Find all Maya scene files in a workspace.

        Args:
            workspace_path: Full path to the shot workspace
            include_autosave: Whether to include autosave files

        Returns:
            List of all Maya scene files found
        """
        if not workspace_path:
            return []

        workspace = Path(workspace_path)
        if not workspace.exists():
            return []

        maya_files: list[Path] = []
        user_base = workspace / "user"

        if not user_base.exists():
            return []

        for user_dir in user_base.iterdir():
            if not user_dir.is_dir():
                continue

            maya_scenes = user_dir / "maya" / "scenes"
            if not maya_scenes.exists():
                continue

            # Get all .ma and .mb files
            for maya_file in maya_scenes.glob("*.ma"):
                # Skip autosave files unless requested
                if not include_autosave and ".autosave" in maya_file.name:
                    continue
                maya_files.append(maya_file)

            for maya_file in maya_scenes.glob("*.mb"):
                # Skip autosave files unless requested
                if not include_autosave and ".autosave" in maya_file.name:
                    continue
                maya_files.append(maya_file)

        return maya_files