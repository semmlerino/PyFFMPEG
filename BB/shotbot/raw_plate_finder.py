"""Utility for finding raw plate files for shots."""

import logging
import re
from pathlib import Path
from typing import Optional

from utils import PathUtils, VersionUtils

# Set up logger for this module
logger = logging.getLogger(__name__)


class RawPlateFinder:
    """Finds the latest raw plate file for a shot."""

    @staticmethod
    def find_latest_raw_plate(
        shot_workspace_path: str, shot_name: str
    ) -> Optional[str]:
        """
        Find the latest raw plate file path for a shot.

        Args:
            shot_workspace_path: The shot's workspace path (e.g., /shows/ygsk/shots/108_CHV/108_CHV_0015)
            shot_name: The shot name (e.g., 108_CHV_0015)

        Returns:
            Path to the latest raw plate with #### for frame numbers, or None if not found
        """
        # Build base path for raw plate files using utilities
        base_path = PathUtils.build_raw_plate_path(shot_workspace_path)

        if not PathUtils.validate_path_exists(base_path, "Raw plate base path"):
            return None

        # Find the latest version directory
        latest_version = VersionUtils.get_latest_version(base_path)
        if not latest_version:
            logger.debug(f"No version directories found in {base_path}")
            return None

        # Check for EXR directory
        exr_base = base_path / latest_version / "exr"
        if not exr_base.exists():
            return None

        # Find resolution directory (e.g., 4042x2274)
        resolution_dirs = [
            d for d in exr_base.iterdir() if d.is_dir() and "x" in d.name
        ]
        if not resolution_dirs:
            return None

        # Use the first resolution directory found
        resolution_dir = resolution_dirs[0]

        # Construct the file pattern with #### for frame numbers
        plate_pattern = (
            f"{shot_name}_turnover-plate_bg01_aces_{latest_version}.####.exr"
        )

        # Return the full path
        return str(resolution_dir / plate_pattern)

    @staticmethod
    def get_version_from_path(plate_path: str) -> Optional[str]:
        """
        Extract the version number from a raw plate file path.

        Args:
            plate_path: Path to the raw plate file

        Returns:
            Version string (e.g., "v002") or None
        """
        # Use utility function for version extraction
        return VersionUtils.extract_version_from_path(plate_path)

    @staticmethod
    def verify_plate_exists(plate_path: str) -> bool:
        """
        Verify that at least one frame of the plate sequence exists.

        Optimized to scan directory once instead of multiple file existence checks.

        Args:
            plate_path: Path with #### pattern

        Returns:
            True if at least one frame exists
        """
        if not plate_path or "####" not in plate_path:
            logger.debug("Invalid plate path - missing or no frame pattern")
            return False

        dir_path = Path(plate_path).parent
        if not PathUtils.validate_path_exists(dir_path, "Plate directory"):
            return False

        # Extract the base filename pattern for matching
        plate_filename = Path(plate_path).name
        base_pattern = plate_filename.replace("####", r"\d{4}")

        try:
            pattern = re.compile(f"^{base_pattern}$")

            # Single directory scan - more efficient than multiple exists() calls
            for file_path in dir_path.iterdir():
                if file_path.is_file() and pattern.match(file_path.name):
                    logger.debug(f"Found matching plate frame: {file_path.name}")
                    return True

        except (OSError, PermissionError) as e:
            logger.warning(f"Error scanning plate directory {dir_path}: {e}")
            return False
        except re.error as e:
            logger.error(f"Invalid regex pattern '{base_pattern}': {e}")
            return False

        logger.debug(f"No matching frames found for pattern: {base_pattern}")
        return False
