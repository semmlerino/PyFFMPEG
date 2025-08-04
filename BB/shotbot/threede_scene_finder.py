"""Utility for finding 3DE scene files from other users."""

import logging
import os
from pathlib import Path
from typing import List, Optional, Set

from config import Config
from threede_scene_model import ThreeDEScene
from utils import PathUtils, ValidationUtils

# Set up logger for this module
logger = logging.getLogger(__name__)


class ThreeDESceneFinder:
    """Static utility class for discovering 3DE scene files."""

    @staticmethod
    def find_scenes_for_shot(
        shot_workspace_path: str,
        show: str,
        sequence: str,
        shot: str,
        excluded_users: Optional[Set[str]] = None,
    ) -> List[ThreeDEScene]:
        """Find all 3DE scenes for a shot from other users.

        Args:
            shot_workspace_path: The workspace path for the shot
            show: Show name
            sequence: Sequence name
            shot: Shot number
            excluded_users: Set of usernames to exclude (uses current user if None)

        Returns:
            List of ThreeDEScene objects
        """
        # Validate input parameters
        if not ValidationUtils.validate_shot_components(show, sequence, shot):
            logger.warning("Invalid shot components provided")
            return []
            
        if not shot_workspace_path:
            logger.warning("Empty shot workspace path provided")
            return []

        # Get excluded users if not provided
        if excluded_users is None:
            excluded_users = ValidationUtils.get_excluded_users()

        scenes: List[ThreeDEScene] = []
        user_dir = PathUtils.build_path(shot_workspace_path, "user")

        # Check if user directory exists
        if not PathUtils.validate_path_exists(user_dir, "User directory"):
            logger.debug(f"User directory does not exist: {user_dir}")
            return scenes

        logger.debug(f"Scanning for 3DE scenes in {user_dir}")
        logger.debug(f"Excluding users: {excluded_users}")

        try:
            # Iterate through user directories
            scene_count = 0
            user_count = 0
            
            for user_path in user_dir.iterdir():
                if not user_path.is_dir():
                    continue

                user_name = user_path.name
                user_count += 1

                # Skip excluded users
                if user_name in excluded_users:
                    logger.debug(f"Skipping excluded user: {user_name}")
                    continue

                logger.debug(f"Checking user directory: {user_name}")

                # Build 3DE scene path using utility
                scene_base = PathUtils.build_threede_scene_path(shot_workspace_path, user_name)

                if not PathUtils.validate_path_exists(scene_base, f"3DE scene base for {user_name}"):
                    logger.debug(f"No 3DE scene directory for user {user_name}: {scene_base}")
                    continue

                logger.debug(f"Found 3DE scene directory for {user_name}: {scene_base}")

                # Search recursively for .3de files
                threede_files = list(scene_base.rglob("*.3de"))
                logger.debug(f"Found {len(threede_files)} .3de files for user {user_name}")

                for threede_file in threede_files:
                    logger.debug(f"Processing 3DE file: {threede_file}")
                    
                    # Extract plate name from path
                    # Expected: .../scene/{plate}/.../*.3de
                    relative_path = threede_file.relative_to(scene_base)
                    path_parts = relative_path.parts

                    if len(path_parts) >= 2:
                        # First part should be the plate (e.g., FG01, BG01)
                        plate = path_parts[0]
                        logger.debug(f"Extracted plate from path structure: {plate}")
                    else:
                        # If structure is different, use parent directory name
                        plate = threede_file.parent.name
                        logger.debug(f"Using parent directory as plate: {plate}")

                    # Create ThreeDEScene object
                    scene = ThreeDEScene(
                        show=show,
                        sequence=sequence,
                        shot=shot,
                        workspace_path=shot_workspace_path,
                        user=user_name,
                        plate=plate,
                        scene_path=threede_file,
                    )
                    scenes.append(scene)
                    scene_count += 1
                    logger.debug(f"Added 3DE scene: {user_name}/{plate}")

            logger.info(f"Found {scene_count} 3DE scenes from {user_count} users for {show}/{sequence}/{shot}")

        except PermissionError as e:
            logger.error(f"Permission denied accessing user directories: {e}")
        except Exception as e:
            logger.error(f"Error scanning for 3DE scenes: {e}")

        return scenes

    @staticmethod
    def find_all_scenes(
        shots: List[tuple[str, str, str, str]], 
        excluded_users: Optional[Set[str]] = None
    ) -> List[ThreeDEScene]:
        """Find 3DE scenes for multiple shots.

        Args:
            shots: List of (workspace_path, show, sequence, shot) tuples
            excluded_users: Set of usernames to exclude (uses current user if None)

        Returns:
            Combined list of ThreeDEScene objects
        """
        if not shots:
            logger.debug("No shots provided for scene search")
            return []

        all_scenes: List[ThreeDEScene] = []
        logger.info(f"Searching for 3DE scenes across {len(shots)} shots")

        for workspace_path, show, sequence, shot in shots:
            scenes = ThreeDESceneFinder.find_scenes_for_shot(
                workspace_path, show, sequence, shot, excluded_users
            )
            all_scenes.extend(scenes)

        logger.info(f"Found total of {len(all_scenes)} 3DE scenes across all shots")
        return all_scenes

    @staticmethod 
    def verify_scene_exists(scene_path: Path) -> bool:
        """Verify that a 3DE scene file exists and is readable.

        Args:
            scene_path: Path to the .3de file

        Returns:
            True if file exists and is readable
        """
        if not scene_path:
            logger.debug("Empty scene path provided")
            return False

        try:
            # Use PathUtils for consistent validation
            if not PathUtils.validate_path_exists(scene_path, "3DE scene file"):
                return False
                
            # Additional checks for file type and readability
            if not scene_path.is_file():
                logger.debug(f"Path is not a file: {scene_path}")
                return False
                
            if not os.access(scene_path, os.R_OK):
                logger.debug(f"File is not readable: {scene_path}")
                return False
                
            # Check file extension
            if scene_path.suffix.lower() not in [ext.lower() for ext in Config.THREEDE_EXTENSIONS]:
                logger.debug(f"File does not have 3DE extension: {scene_path}")
                return False
                
            logger.debug(f"3DE scene file verified: {scene_path}")
            return True
            
        except Exception as e:
            logger.warning(f"Error verifying 3DE scene file {scene_path}: {e}")
            return False
