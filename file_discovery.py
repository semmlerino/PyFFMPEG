"""File and directory discovery utilities for VFX pipeline.

This module provides utilities for discovering and creating files and
directories in the VFX pipeline structure.
"""

from __future__ import annotations

# Standard library imports
import re
from pathlib import Path

# Local application imports
from config import Config
from logging_mixin import get_module_logger
from path_validators import PathValidators
from utils import normalize_plate_id


logger = get_module_logger(__name__)


class FileDiscovery:
    """Utilities for file and directory discovery."""

    @staticmethod
    def safe_mkdir(path: str | Path, description: str = "Directory") -> bool:
        """Safely create directory with error handling.

        Args:
            path: Directory path to create
            description: Description for logging

        Returns:
            True if successful, False otherwise
        """
        if not path:
            logger.error(f"Cannot create {description}: empty path")
            return False

        path_obj = Path(path) if isinstance(path, str) else path
        try:
            path_obj.mkdir(parents=True, exist_ok=True)
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to create {description} {path_obj}: {e}")
            return False

    @staticmethod
    def find_mov_file_for_path(thumbnail_path: Path) -> Path | None:
        """Find a MOV file in the same version directory structure as a thumbnail.

        Given a path like:
        /shows/show/shots/seq/shot/publish/.../v001/exr/1920x1080/file.exr

        Searches for MOV files in:
        /shows/show/shots/seq/shot/publish/.../v001/mov/

        Args:
            thumbnail_path: Path to the original thumbnail (EXR or other format)

        Returns:
            Path to the MOV file if found, or None
        """
        try:
            # Walk up the directory tree to find a v001 (or similar version) directory
            current = thumbnail_path.parent
            version_dir = None
            max_depth = 5  # Limit search depth to avoid excessive traversal

            for _ in range(max_depth):
                if not current or current == current.parent:
                    break

                # Check if this looks like a version directory (v###)
                if current.name.startswith("v") and current.name[1:].isdigit():
                    version_dir = current
                    break

                current = current.parent

            if not version_dir:
                logger.debug(
                    f"Could not find version directory for path: {thumbnail_path}"
                )
                return None

            # Look for mov/ subdirectory
            mov_dir = version_dir / "mov"
            if not mov_dir.exists() or not mov_dir.is_dir():
                logger.debug(f"No mov directory found at: {mov_dir}")
                return None

            # Find MOV files in the directory
            mov_files = list(mov_dir.glob("*.mov")) + list(mov_dir.glob("*.MOV"))

            if not mov_files:
                logger.debug(f"No MOV files found in: {mov_dir}")
                return None

            # Return the first MOV file found (could be sorted by name if needed)
            mov_file = sorted(mov_files)[0]
            logger.debug(f"Found MOV file: {mov_file.name}")
            return mov_file

        except (OSError, PermissionError) as e:
            logger.debug(f"Error searching for MOV file: {e}")
            return None

    @staticmethod
    def discover_plate_directories(
        base_path: str | Path,
    ) -> list[tuple[str, float]]:
        """Dynamically discover plate directories using pattern matching and priority system.

        Supports: FG##, BG##, PL##, EL##, COMP## (where ## is any digit sequence).
        Only directories matching these patterns are returned.
        Uses Config.TURNOVER_PLATE_PRIORITY for ranking plates by type.

        This replaces the hardcoded PLATE_DISCOVERY_PATTERNS approach with dynamic
        discovery, allowing any plate naming (EL01, EL02, EL99, etc.) to work
        automatically without config updates.

        Args:
            base_path: Base path to search for plate directories

        Returns:
            List of (plate_name, priority) tuples sorted by priority (lower = higher priority)
        """
        if not PathValidators.validate_path_exists(base_path, "Plate base path"):
            return []

        path_obj = Path(base_path) if isinstance(base_path, str) else base_path
        found_plates: list[tuple[str, float]] = []

        # Define plate patterns with capturing groups for type identification
        plate_patterns = {
            r"^(FG)\d+$": "FG",  # FG01, FG02, etc.
            r"^(BG)\d+$": "BG",  # BG01, BG02, etc.
            r"^(EL)\d+$": "EL",  # EL01, EL02, etc. (element plates)
            r"^(COMP)\d+$": "COMP",  # COMP01, COMP02, etc.
            r"^(PL)\d+$": "PL",  # PL01, PL02, etc. (turnover plates)
        }

        try:
            for item in path_obj.iterdir():
                if not item.is_dir():
                    continue

                plate_name = item.name
                matched_prefix = None

                # Try to match against known patterns (case-insensitive to handle pl01, PL01, Pl01, etc.)
                for pattern, prefix in plate_patterns.items():
                    if re.match(pattern, plate_name, re.IGNORECASE):
                        matched_prefix = prefix
                        break

                # Only include directories that match known plate patterns
                if matched_prefix:
                    priority = Config.TURNOVER_PLATE_PRIORITY.get(matched_prefix, 3)
                    found_plates.append((plate_name, priority))
                    # Log normalized plate ID for consistency (but use filesystem case for paths)
                    normalized_name = normalize_plate_id(plate_name) or plate_name
                    logger.debug(
                        f"Found plate: {normalized_name} (type: {matched_prefix}, priority: {priority})"
                    )
                else:
                    # Skip non-plate directories (e.g., 'reference', 'backup', etc.)
                    logger.debug(f"Skipping non-plate directory: {plate_name}")

        except (OSError, PermissionError) as e:
            logger.warning(f"Error scanning plate directories in {base_path}: {e}")

        # Sort by priority (LOWER number = HIGHER priority as per config documentation)
        found_plates.sort(key=lambda x: x[1])

        return found_plates
