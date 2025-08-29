"""3DE scene data model for tracking scenes from other users."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cache_manager import CacheManager
from config import Config
from shot_model import Shot
from utils import FileUtils, PathUtils, ValidationUtils

logger = logging.getLogger(__name__)

# Sentinel value to distinguish between "not searched" and "searched but found nothing"
_NOT_SEARCHED = object()


@dataclass
class ThreeDEScene:
    """Represents a 3DE scene file from another user."""

    show: str
    sequence: str
    shot: str
    workspace_path: str
    user: str
    plate: str
    scene_path: Path
    _cached_thumbnail_path: Any = field(
        default=_NOT_SEARCHED,
        init=False,
        repr=False,
        compare=False,
    )

    @property
    def full_name(self) -> str:
        """Get full shot name."""
        return f"{self.sequence}_{self.shot}"

    @property
    def display_name(self) -> str:
        """Get display name (simplified for deduplicated scenes)."""
        # Since we show only one scene per shot, we don't need plate info
        return f"{self.full_name} - {self.user}"

    @property
    def thumbnail_dir(self) -> Path:
        """Get thumbnail directory path (same as regular shots)."""
        return PathUtils.build_thumbnail_path(
            Config.SHOWS_ROOT,
            self.show,
            self.sequence,
            self.shot,
        )

    def get_thumbnail_path(self) -> Path | None:
        """Get first available thumbnail or None.

        Tries three fallback options:
        1. Editorial directory thumbnails
        2. Turnover plate thumbnails
        3. Any EXR file containing '1001' in publish folder

        Results are cached after the first search to avoid repeated
        expensive filesystem operations.
        """
        # Return cached result if we've already searched
        if self._cached_thumbnail_path is not _NOT_SEARCHED:
            return self._cached_thumbnail_path

        # Perform the search and cache the result
        thumbnail = None

        # Try editorial thumbnail first
        if PathUtils.validate_path_exists(self.thumbnail_dir, "Thumbnail directory"):
            # Use utility to find first image file
            thumbnail = FileUtils.get_first_image_file(self.thumbnail_dir)
            if thumbnail:
                self._cached_thumbnail_path = thumbnail
                return thumbnail

        # Fall back to turnover plate thumbnails
        thumbnail = PathUtils.find_turnover_plate_thumbnail(  # type: ignore[attr-defined]
            Config.SHOWS_ROOT,
            self.show,
            self.sequence,
            self.shot,
        )
        if thumbnail:
            self._cached_thumbnail_path = thumbnail
            return thumbnail

        # Third fallback: any EXR with 1001 in publish folder
        thumbnail = PathUtils.find_any_publish_thumbnail(  # type: ignore[attr-defined]
            Config.SHOWS_ROOT,
            self.show,
            self.sequence,
            self.shot,
        )

        # Cache the result (even if None) to avoid repeated searches
        self._cached_thumbnail_path = thumbnail
        return thumbnail

    def to_dict(self) -> dict[str, str | Path]:
        """Convert scene to dictionary for caching."""
        return {
            "show": self.show,
            "sequence": self.sequence,
            "shot": self.shot,
            "workspace_path": self.workspace_path,
            "user": self.user,
            "plate": self.plate,
            "scene_path": str(self.scene_path),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | Path]) -> "ThreeDEScene":
        """Create from dictionary."""
        scene = cls(
            show=str(data["show"]),
            sequence=str(data["sequence"]),
            shot=str(data["shot"]),
            workspace_path=str(data["workspace_path"]),
            user=str(data["user"]),
            plate=str(data["plate"]),
            scene_path=Path(data["scene_path"]),
        )
        # Don't restore cached thumbnail path from dict - let it be re-discovered if needed
        # This ensures we don't cache stale paths across sessions
        return scene


class ThreeDESceneModel:
    """Manages 3DE scene data and discovery."""

    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        load_cache: bool = True,
    ):
        self.scenes: list[ThreeDEScene] = []
        self.cache_manager = cache_manager or CacheManager()
        # Get excluded users dynamically (current user + any additional)
        self._excluded_users = ValidationUtils.get_excluded_users()
        # Only load cache if requested (allows tests to start clean)
        if load_cache:
            self._load_from_cache()

    def _load_from_cache(self) -> bool:
        """Load 3DE scenes from cache if available."""
        cached_data = self.cache_manager.get_cached_threede_scenes()
        if cached_data:
            self.scenes = []
            for scene_data in cached_data:
                try:
                    # Skip invalid cached entries (e.g., from old format)
                    self.scenes.append(ThreeDEScene.from_dict(scene_data))
                except (KeyError, TypeError, ValueError) as e:
                    # Skip invalid cached entry
                    print(f"Skipping invalid cached 3DE scene: {e}")
                    continue
            return len(self.scenes) > 0
        return False

    def refresh_scenes(self, shots: list[Shot]) -> tuple[bool, bool]:
        """Refresh 3DE scenes for all shots.

        Args:
            shots: List of shots to scan for 3DE scenes

        Returns:
            (success, has_changes) - whether refresh succeeded and if scenes changed
        """
        from threede_scene_finder import ThreeDESceneFinder

        try:
            # Save current scenes for comparison
            old_scene_data = {
                (scene.full_name, scene.user, scene.plate, str(scene.scene_path))
                for scene in self.scenes
            }

            # Use the new efficient discovery method
            # This finds .3de files first, then extracts shots - much faster!
            new_scenes = ThreeDESceneFinder.find_all_scenes_in_shows_efficient(
                shots,  # User's shots are used to determine which shows to search
                self._excluded_users,
            )

            # Create comparison set
            new_scene_data = {
                (scene.full_name, scene.user, scene.plate, str(scene.scene_path))
                for scene in new_scenes
            }

            # Check if there are changes
            has_changes = old_scene_data != new_scene_data

            if has_changes:
                # Apply deduplication - keep only one scene per shot
                self.scenes = self._deduplicate_scenes_by_shot(new_scenes)
                # Sort deduplicated scenes
                self.scenes.sort(key=lambda s: (s.full_name, s.user))

            # ALWAYS cache results to refresh TTL and ensure persistence
            # This fixes the issue where cache wasn't persisting across restarts
            self.cache_manager.cache_threede_scenes(self.to_dict())

            return True, has_changes

        except Exception as e:
            print(f"Error refreshing 3DE scenes: {e}")
            return False, False

    def get_scene_by_index(self, index: int) -> ThreeDEScene | None:
        """Get scene by index."""
        if 0 <= index < len(self.scenes):
            return self.scenes[index]
        return None

    def find_scene_by_display_name(self, display_name: str) -> ThreeDEScene | None:
        """Find scene by display name."""
        for scene in self.scenes:
            if scene.display_name == display_name:
                return scene
        return None

    def to_dict(self) -> list[dict[str, Any]]:
        """Convert scenes to dictionary format for caching."""
        return [scene.to_dict() for scene in self.scenes]

    def _deduplicate_scenes_by_shot(
        self,
        scenes: list[ThreeDEScene],
    ) -> list[ThreeDEScene]:
        """Keep only the latest/best scene per shot.

        Priority order:
        1. Latest file modification time
        2. Specific plate preference (FG01 > BG01 > others)
        3. Alphabetical plate name as tiebreaker

        Args:
            scenes: List of all discovered scenes

        Returns:
            Deduplicated list with one scene per shot
        """
        # Group scenes by shot
        scenes_by_shot: dict[str, list[ThreeDEScene]] = defaultdict(list)
        for scene in scenes:
            shot_key = f"{scene.show}/{scene.sequence}/{scene.shot}"
            scenes_by_shot[shot_key].append(scene)

        deduplicated: list[ThreeDEScene] = []
        for shot_scenes in scenes_by_shot.values():
            if len(shot_scenes) == 1:
                deduplicated.append(shot_scenes[0])
            else:
                # Select best scene for this shot
                best_scene = self._select_best_scene(shot_scenes)
                deduplicated.append(best_scene)
                logger.debug(
                    f"Selected {best_scene.display_name} from {len(shot_scenes)} scenes",
                )

        return deduplicated

    def _select_best_scene(self, scenes: list[ThreeDEScene]) -> ThreeDEScene:
        """Select the best scene from multiple options.

        Args:
            scenes: List of scenes for the same shot

        Returns:
            Best scene based on priority criteria
        """

        # Priority 1: Latest modification time
        def get_mtime(scene):
            try:
                return scene.scene_path.stat().st_mtime
            except (OSError, AttributeError):
                return 0

        # Priority 2: Plate preference
        plate_priority = {
            "fg01": 3,
            "bg01": 2,
        }  # lowercase for case-insensitive comparison

        def scene_score(scene):
            mtime = get_mtime(scene)
            plate_score = plate_priority.get(scene.plate.lower(), 1)
            return (mtime, plate_score, scene.plate)

        return max(scenes, key=scene_score)
