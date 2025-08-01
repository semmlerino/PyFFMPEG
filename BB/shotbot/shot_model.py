"""Shot data model and parser for ws -sg output."""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from cache_manager import CacheManager
from config import Config


@dataclass
class Shot:
    """Represents a single shot."""

    show: str
    sequence: str
    shot: str
    workspace_path: str

    @property
    def full_name(self) -> str:
        """Get full shot name."""
        return f"{self.sequence}_{self.shot}"

    @property
    def thumbnail_dir(self) -> Path:
        """Get thumbnail directory path."""
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

    def to_dict(self) -> Dict[str, str]:
        """Convert shot to dictionary for serialization."""
        return {
            "show": self.show,
            "sequence": self.sequence,
            "shot": self.shot,
            "workspace_path": self.workspace_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Shot":
        """Create shot from dictionary data."""
        return cls(
            show=data["show"],
            sequence=data["sequence"],
            shot=data["shot"],
            workspace_path=data["workspace_path"],
        )


class ShotModel:
    """Manages shot data and parsing."""

    def __init__(
        self, cache_manager: Optional[CacheManager] = None, load_cache: bool = True
    ):
        self.shots: list[Shot] = []
        self.cache_manager = cache_manager or CacheManager()
        self._parse_pattern = re.compile(
            r"workspace\s+(/shows/(\w+)/shots/(\w+)/(\w+))"
        )
        # Only load cache if requested (allows tests to start clean)
        if load_cache:
            self._load_from_cache()

    def _load_from_cache(self) -> bool:
        """Load shots from cache if available."""
        cached_data = self.cache_manager.get_cached_shots()
        if cached_data:
            self.shots = [Shot.from_dict(shot_data) for shot_data in cached_data]
            return True
        return False

    def refresh_shots(self) -> tuple[bool, bool]:
        """Fetch and parse shot list from ws -sg command.

        Returns:
            (success, has_changes) - whether refresh succeeded and if shots changed
        """
        try:
            # Save current shots for comparison (include workspace path)
            old_shot_data = {
                (shot.full_name, shot.workspace_path) for shot in self.shots
            }

            # Run ws -sg command in interactive bash shell to load functions
            result = subprocess.run(
                ["/bin/bash", "-i", "-c", "ws -sg"],
                capture_output=True,
                text=True,
                timeout=10,
                env=os.environ.copy(),
            )

            if result.returncode != 0:
                print(f"Error running ws -sg: {result.stderr}")
                return False, False

            # Parse output
            new_shots = self._parse_ws_output(result.stdout)
            new_shot_data = {
                (shot.full_name, shot.workspace_path) for shot in new_shots
            }

            # Check if there are changes (added, removed, or path changed)
            has_changes = old_shot_data != new_shot_data

            if has_changes:
                self.shots = new_shots
                # Cache the results - pass Shot objects directly
                if self.shots:
                    self.cache_manager.cache_shots(self.shots)

            return True, has_changes

        except subprocess.TimeoutExpired:
            print("Timeout running ws -sg command")
            return False, False
        except FileNotFoundError:
            print("ws command not found")
            return False, False
        except Exception as e:
            print(f"Error fetching shots: {e}")
            return False, False

    def _parse_ws_output(self, output: str) -> list[Shot]:
        """Parse ws -sg output to extract shots."""
        shots: list[Shot] = []

        for line in output.strip().split("\n"):
            match = self._parse_pattern.search(line)
            if match:
                workspace_path = match.group(1)
                show = match.group(2)
                sequence = match.group(3)
                shot_name = match.group(4)

                # Extract shot number from full name (e.g., "108_BQS_0005" -> "0005")
                shot_parts = shot_name.split("_")
                if len(shot_parts) >= 3:
                    shot = shot_parts[-1]
                else:
                    shot = shot_name

                shots.append(
                    Shot(
                        show=show,
                        sequence=sequence,
                        shot=shot,
                        workspace_path=workspace_path,
                    )
                )

        return shots

    def get_shot_by_index(self, index: int) -> Optional[Shot]:
        """Get shot by index."""
        if 0 <= index < len(self.shots):
            return self.shots[index]
        return None

    def find_shot_by_name(self, full_name: str) -> Optional[Shot]:
        """Find shot by full name."""
        for shot in self.shots:
            if shot.full_name == full_name:
                return shot
        return None
