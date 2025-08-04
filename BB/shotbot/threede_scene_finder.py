"""Utility for finding 3DE scene files from other users."""

import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Set

from config import Config
from threede_scene_model import ThreeDEScene
from utils import PathUtils, ValidationUtils

# Set up logger for this module
logger = logging.getLogger(__name__)


class PathDiagnostics:
    """Helper class for detailed path diagnostics during 3DE scene finding."""
    
    @staticmethod
    def log_path_attempt(path: Path, description: str, exists: bool = None):
        """Log a path access attempt with detailed information.
        
        Args:
            path: Path being accessed
            description: Description of what this path represents
            exists: Whether path exists (checked if None)
        """
        if exists is None:
            exists = path.exists()
            
        status = "EXISTS" if exists else "MISSING"
        logger.debug(f"PATH CHECK [{status}] {description}: {path}")
        
        if not exists:
            # Check parent directory
            parent = path.parent
            if parent.exists():
                logger.debug(f"  Parent directory exists: {parent}")
                try:
                    siblings = list(parent.iterdir())[:10]  # Limit to first 10
                    sibling_names = [s.name for s in siblings]
                    logger.debug(f"  Parent contains: {sibling_names}")
                except PermissionError:
                    logger.debug(f"  Permission denied listing parent directory")
            else:
                logger.debug(f"  Parent directory also missing: {parent}")
    
    @staticmethod
    def check_alternative_paths(workspace_path: str, username: str) -> List[Path]:
        """Check alternative path patterns for 3DE scenes.
        
        Args:
            workspace_path: Shot workspace path
            username: Username to check for
            
        Returns:
            List of alternative paths that exist
        """
        base_path = Path(workspace_path) / "user" / username
        alternatives = []
        
        # Alternative path patterns to check
        path_patterns = [
            # Current expected pattern
            Config.THREEDE_SCENE_SEGMENTS,
            
            # Alternative patterns from config
            *Config.THREEDE_ALTERNATIVE_PATTERNS,
            
            # Check environment variable patterns
            *PathDiagnostics._get_env_path_patterns(),
        ]
        
        logger.debug(f"Checking {len(path_patterns)} alternative path patterns for user {username}")
        
        for pattern in path_patterns:
            try:
                alt_path = PathUtils.build_path(str(base_path), *pattern)
                PathDiagnostics.log_path_attempt(alt_path, f"Alternative pattern {' -> '.join(pattern)}")
                
                if alt_path.exists():
                    alternatives.append(alt_path)
                    logger.info(f"Found alternative 3DE path for {username}: {alt_path}")
                    
            except Exception as e:
                logger.debug(f"Error checking alternative pattern {pattern}: {e}")
        
        return alternatives
    
    @staticmethod
    def _get_env_path_patterns() -> List[List[str]]:
        """Get path patterns from environment variables.
        
        Returns:
            List of path segment lists based on environment variables
        """
        patterns = []
        
        # Check for 3DE-specific environment variables from config
        env_patterns = {}
        for env_var in Config.THREEDE_ENV_VARS:
            value = os.environ.get(env_var)
            if value:
                env_patterns[env_var] = value
        
        for env_var, value in env_patterns.items():
            if value:
                # Split path and use as segments
                segments = [seg for seg in value.split('/') if seg]
                if segments:
                    patterns.append(segments)
                    logger.debug(f"Added path pattern from {env_var}: {segments}")
        
        return patterns


class ThreeDESceneFinder:
    """Static utility class for discovering 3DE scene files."""

    @staticmethod
    def extract_plate_from_path(file_path: Path, user_path: Path) -> str:
        """Extract meaningful plate/grouping identifier from an arbitrary path.
        
        Args:
            file_path: Full path to the .3de file
            user_path: Base user directory path
            
        Returns:
            Extracted plate/grouping name
        """
        try:
            # Get relative path from user directory
            relative_path = file_path.relative_to(user_path)
            path_parts = relative_path.parts
            
            # Common VFX plate patterns to look for
            plate_patterns = Config.PLATE_NAME_PATTERNS if hasattr(Config, 'PLATE_NAME_PATTERNS') else [
                r'^[bf]g\d{2}$',  # bg01, fg01, etc.
                r'^plate_?\d+$',  # plate01, plate_01
                r'^comp_?\d+$',   # comp01, comp_01
                r'^shot_?\d+$',   # shot01, shot_01
                r'^sc\d+$',       # sc01, sc02
                r'^[\w]+_v\d{3}$', # anything_v001
            ]
            
            # Look through path parts for meaningful names
            for i, part in enumerate(path_parts[:-1]):  # Exclude the filename
                part_lower = part.lower()
                
                # Check if this part matches common plate patterns
                for pattern in plate_patterns:
                    if re.match(pattern, part_lower):
                        logger.debug(f"Found plate pattern match: {part}")
                        return part
                
                # Check for common VFX directory names that indicate grouping
                if part_lower in ['3de', 'scenes', 'scene', 'matchmove', 'mm', 'tracking']:
                    # Use the next directory if available
                    if i + 1 < len(path_parts) - 1:
                        next_part = path_parts[i + 1]
                        if next_part not in ['3de', 'scenes', 'scene', 'exports']:
                            logger.debug(f"Using directory after {part}: {next_part}")
                            return next_part
            
            # If no pattern matched, use intelligent fallback
            # Prefer directories that aren't generic tool/process names
            generic_dirs = {'3de', 'scenes', 'scene', 'mm', 'matchmove', 'tracking', 
                          'work', 'wip', 'exports', 'user', 'files', 'data'}
            
            for part in reversed(path_parts[:-1]):
                if part.lower() not in generic_dirs:
                    logger.debug(f"Using non-generic directory as plate: {part}")
                    return part
            
            # Last resort: use parent directory
            parent_name = file_path.parent.name
            logger.debug(f"Using parent directory as plate: {parent_name}")
            return parent_name
            
        except ValueError:
            # Can't make relative path, use parent directory
            logger.debug(f"Cannot make relative path, using parent: {file_path.parent.name}")
            return file_path.parent.name

    @staticmethod
    def find_scenes_for_shot(
        shot_workspace_path: str,
        show: str,
        sequence: str,
        shot: str,
        excluded_users: Optional[Set[str]] = None,
    ) -> List[ThreeDEScene]:
        """Find all 3DE scenes for a shot from other users.
        
        This method now performs a flexible recursive search for all .3de files
        in user directories, regardless of specific path structure.

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
            logger.warning(f"User directory does not exist: {user_dir}")
            return scenes

        logger.info(f"Performing flexible 3DE scene search in {user_dir}")
        logger.debug(f"Excluding users: {excluded_users}")

        try:
            # Iterate through user directories
            scene_count = 0
            user_count = 0
            total_scanned = 0
            
            for user_path in user_dir.iterdir():
                if not user_path.is_dir():
                    continue

                user_name = user_path.name
                total_scanned += 1

                # Skip excluded users
                if user_name in excluded_users:
                    logger.debug(f"Skipping excluded user: {user_name}")
                    continue

                user_count += 1
                logger.debug(f"Scanning user directory: {user_name}")

                # Recursively find ALL .3de files in the user's directory
                try:
                    threede_files = list(user_path.rglob("*.3de"))
                    
                    if threede_files:
                        logger.info(f"Found {len(threede_files)} .3de files for user {user_name}")
                        
                        for threede_file in threede_files:
                            # Skip if file doesn't exist or isn't readable
                            if not ThreeDESceneFinder.verify_scene_exists(threede_file):
                                logger.debug(f"Skipping inaccessible file: {threede_file}")
                                continue
                            
                            # Extract meaningful plate/grouping from path
                            plate = ThreeDESceneFinder.extract_plate_from_path(threede_file, user_path)
                            
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
                            
                            logger.debug(f"Added 3DE scene: {user_name}/{plate} -> {threede_file.name}")
                    else:
                        logger.debug(f"No .3de files found for user {user_name}")
                        
                except PermissionError:
                    logger.warning(f"Permission denied accessing {user_name} directory")
                except Exception as e:
                    logger.error(f"Error scanning user {user_name}: {e}")

            logger.info(f"Flexible search complete: Found {scene_count} 3DE scenes from {user_count} users (scanned {total_scanned} directories)")

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
