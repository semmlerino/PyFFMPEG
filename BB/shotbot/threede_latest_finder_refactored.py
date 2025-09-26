"""Refactored 3DE finder using BaseSceneFinder."""

from __future__ import annotations

import re
from pathlib import Path

from base_scene_finder import BaseSceneFinder


class ThreeDELatestFinder(BaseSceneFinder):
    """Finds the latest 3DE scene file in a workspace.

    Simplified version using BaseSceneFinder for common functionality.
    """

    # Pattern to match version in 3DE filenames (e.g., _v001, _v002)
    VERSION_PATTERN = re.compile(r"_v(\d{3})\.3de$")

    def get_scene_paths(self, user_dir: Path) -> list[Path]:
        """Get 3DE-specific scene directories.

        Args:
            user_dir: User directory path

        Returns:
            List of paths to search for 3DE files
        """
        # 3DE files are in: user/{username}/mm/3de/mm-default/scenes/scene/
        threede_base = user_dir / "mm" / "3de" / "mm-default" / "scenes" / "scene"
        return [threede_base] if threede_base.exists() else []

    def get_file_extensions(self) -> list[str]:
        """Get 3DE file extensions.

        Returns:
            List of 3DE file extensions
        """
        return [".3de"]

    def find_latest_threede_scene(
        self,
        workspace_path: str,
        shot_name: str | None = None,
    ) -> Path | None:
        """Find the latest 3DE scene file in a workspace.

        This method maintains the original interface for compatibility.
        3DE files are organized in plate subdirectories, which are handled
        by the base class's _search_directory method.

        Args:
            workspace_path: Full path to the shot workspace
            shot_name: Optional shot name for better logging

        Returns:
            Path to the latest 3DE scene file, or None if not found
        """
        return self.find_latest_scene(workspace_path, shot_name)

    @staticmethod
    def find_all_threede_scenes(workspace_path: str) -> list[Path]:
        """Find all 3DE scene files in a workspace.

        Static method for compatibility with existing code.

        Args:
            workspace_path: Full path to the shot workspace

        Returns:
            List of paths to all 3DE scene files, sorted by version
        """
        finder = ThreeDELatestFinder()
        return finder.find_all_scenes(workspace_path)

    def find_scenes_by_plate(
        self,
        workspace_path: str,
        plate_name: str | None = None,
    ) -> dict[str, list[Path]]:
        """Find 3DE scenes organized by plate directory.

        3DE-specific method to handle plate organization.

        Args:
            workspace_path: Full path to the shot workspace
            plate_name: Optional specific plate to filter

        Returns:
            Dictionary mapping plate names to lists of 3DE files
        """
        all_scenes = self.find_all_scenes(workspace_path, include_all=True)
        plate_scenes: dict[str, list[Path]] = {}

        for scene_path in all_scenes:
            # Extract plate name from path
            # Path structure: .../scenes/scene/{plate_name}/file.3de
            parts = scene_path.parts
            if "scene" in parts:
                scene_idx = parts.index("scene")
                if scene_idx + 1 < len(parts) - 1:  # Plate dir between scene and file
                    plate = parts[scene_idx + 1]

                    # Filter by plate name if specified
                    if plate_name and plate.lower() != plate_name.lower():
                        continue

                    if plate not in plate_scenes:
                        plate_scenes[plate] = []
                    plate_scenes[plate].append(scene_path)

        # Sort files within each plate
        for plate in plate_scenes:
            plate_scenes[plate].sort()

        return plate_scenes

    def get_latest_per_plate(self, workspace_path: str) -> dict[str, Path]:
        """Get the latest 3DE scene for each plate.

        Args:
            workspace_path: Full path to the shot workspace

        Returns:
            Dictionary mapping plate names to their latest 3DE file
        """
        plate_scenes = self.find_scenes_by_plate(workspace_path)
        latest_per_plate: dict[str, Path] = {}

        for plate, scenes in plate_scenes.items():
            if not scenes:
                continue

            # Find latest in this plate
            versioned: list[tuple[Path, int]] = []
            for scene in scenes:
                version = self._extract_version(scene)
                if version is not None:
                    versioned.append((scene, version))

            if versioned:
                versioned.sort(key=lambda x: x[1])
                latest_per_plate[plate] = versioned[-1][0]
            elif scenes:
                # No versioned files, use most recent
                latest_per_plate[plate] = max(
                    scenes,
                    key=lambda p: p.stat().st_mtime if p.exists() else 0
                )

        return latest_per_plate