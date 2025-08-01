"""3DE scene data model for tracking scenes from other users."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cache_manager import CacheManager
from config import Config
from shot_model import Shot


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

    @property
    def full_name(self) -> str:
        """Get full shot name."""
        return f"{self.sequence}_{self.shot}"

    @property
    def display_name(self) -> str:
        """Get display name including user and plate."""
        return f"{self.full_name} - {self.user} ({self.plate})"

    @property
    def thumbnail_dir(self) -> Path:
        """Get thumbnail directory path (same as regular shots)."""
        return Path(
            Config.THUMBNAIL_PATH_PATTERN.format(
                shows_root=Config.SHOWS_ROOT,
                show=self.show,
                sequence=self.sequence,
                shot=self.full_name,
            )
        )

    def get_thumbnail_path(self) -> Optional[Path]:
        """Get first available thumbnail or None."""
        if not self.thumbnail_dir.exists():
            return None

        # Look for jpg files
        jpg_files = list(self.thumbnail_dir.glob("*.jpg"))
        if jpg_files:
            return jpg_files[0]

        # Also check for jpeg extension
        jpeg_files = list(self.thumbnail_dir.glob("*.jpeg"))
        if jpeg_files:
            return jpeg_files[0]

        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for caching."""
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
    def from_dict(cls, data: dict[str, Any]) -> "ThreeDEScene":
        """Create from dictionary."""
        return cls(
            show=data["show"],
            sequence=data["sequence"],
            shot=data["shot"],
            workspace_path=data["workspace_path"],
            user=data["user"],
            plate=data["plate"],
            scene_path=Path(data["scene_path"]),
        )


class ThreeDESceneModel:
    """Manages 3DE scene data and discovery."""

    def __init__(
        self, cache_manager: Optional[CacheManager] = None, load_cache: bool = True
    ):
        self.scenes: list[ThreeDEScene] = []
        self.cache_manager = cache_manager or CacheManager()
        self._excluded_users = {"gabriel-h"}
        # Only load cache if requested (allows tests to start clean)
        if load_cache:
            self._load_from_cache()

    def _load_from_cache(self) -> bool:
        """Load 3DE scenes from cache if available."""
        cached_data = self.cache_manager.get_cached_threede_scenes()
        if cached_data:
            self.scenes = []
            for scene_data in cached_data:
                self.scenes.append(ThreeDEScene.from_dict(scene_data))
            return True
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

            # Discover scenes for all shots
            new_scenes: list[ThreeDEScene] = []
            for shot in shots:
                scenes = ThreeDESceneFinder.find_scenes_for_shot(
                    shot.workspace_path,
                    shot.show,
                    shot.sequence,
                    shot.shot,
                    self._excluded_users,
                )
                new_scenes.extend(scenes)

            # Create comparison set
            new_scene_data = {
                (scene.full_name, scene.user, scene.plate, str(scene.scene_path))
                for scene in new_scenes
            }

            # Check if there are changes
            has_changes = old_scene_data != new_scene_data

            if has_changes:
                self.scenes = new_scenes
                # Sort by shot name, then user, then plate
                self.scenes.sort(key=lambda s: (s.full_name, s.user, s.plate))
                # Cache the results
                if self.scenes:
                    self.cache_manager.cache_threede_scenes(self.to_dict())

            return True, has_changes

        except Exception as e:
            print(f"Error refreshing 3DE scenes: {e}")
            return False, False

    def get_scene_by_index(self, index: int) -> Optional[ThreeDEScene]:
        """Get scene by index."""
        if 0 <= index < len(self.scenes):
            return self.scenes[index]
        return None

    def find_scene_by_display_name(self, display_name: str) -> Optional[ThreeDEScene]:
        """Find scene by display name."""
        for scene in self.scenes:
            if scene.display_name == display_name:
                return scene
        return None

    def to_dict(self) -> list[dict[str, Any]]:
        """Convert scenes to dictionary format for caching."""
        return [scene.to_dict() for scene in self.scenes]
