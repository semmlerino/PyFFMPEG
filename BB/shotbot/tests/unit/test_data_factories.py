# pyright: basic
"""Type-safe factories for test data generation.

This module provides factories that create real test objects
following the Test Type Safety Specialist guidelines.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from shot_model import Shot
from threede_scene_model import ThreeDEScene


class TestDataFactory:
    """Factory for creating type-safe test data using real objects."""
    
    @staticmethod
    def create_shot(
        show: str = "test_show",
        sequence: str = "seq01", 
        shot: str = "0010",
        workspace_path: Optional[str] = None
    ) -> Shot:
        """Create a REAL Shot with defaults and overrides."""
        if workspace_path is None:
            workspace_path = f"/shows/{show}/shots/{sequence}/{sequence}_{shot}"
        
        return Shot(
            show=show,
            sequence=sequence,
            shot=shot,
            workspace_path=workspace_path
        )
    
    @staticmethod
    def create_shot_list(count: int = 3) -> List[Shot]:
        """Create a list of real Shot objects for testing."""
        return [
            TestDataFactory.create_shot(
                show="test_show",
                sequence=f"seq{i+1:02d}",
                shot=f"{(i+1)*10:04d}"
            )
            for i in range(count)
        ]
    
    @staticmethod
    def create_3de_scene(
        show: str = "test_show",
        sequence: str = "seq01",
        shot: str = "0010", 
        user: str = "test_user",
        plate: str = "BG01"
    ) -> ThreeDEScene:
        """Create a REAL ThreeDEScene with test data."""
        workspace_path = f"/shows/{show}/shots/{sequence}/{sequence}_{shot}"
        scene_path = f"{workspace_path}/user/{user}/3de/scene.3de"
        
        return ThreeDEScene(
            show=show,
            sequence=sequence,
            shot=shot,
            user=user,
            plate=plate,
            scene_path=scene_path,
            workspace_path=workspace_path
        )
    
    @staticmethod
    def create_cache_data(shots: List[Shot]) -> Dict[str, Any]:
        """Create cache-compatible data from real shots."""
        return {
            "shots": [shot.to_dict() for shot in shots],
            "timestamp": datetime.now().isoformat()
        }
    
    @staticmethod
    def create_expired_cache_data(shots: List[Shot]) -> Dict[str, Any]:
        """Create expired cache data for TTL testing."""
        return {
            "shots": [shot.to_dict() for shot in shots],
            "timestamp": (datetime.now() - timedelta(hours=25)).isoformat()
        }


class MockDataFactory:
    """Factory for creating test doubles at system boundaries only."""
    
    @staticmethod
    def create_workspace_output(shots: List[Shot]) -> str:
        """Create realistic workspace command output."""
        return "\n".join(f"workspace {shot.workspace_path}" for shot in shots)
    
    @staticmethod  
    def create_empty_workspace_output() -> str:
        """Create empty workspace output for failure scenarios."""
        return ""
    
    @staticmethod
    def create_error_workspace_output() -> str:
        """Create error output for subprocess failure testing."""
        return "Error: Command failed"


# Type-safe test constants
class TestConstants:
    """Type-safe constants for testing."""
    
    DEFAULT_TIMEOUT_MS: int = 5000
    CACHE_TTL_SECONDS: int = 60
    MAX_RETRY_COUNT: int = 3
    
    # Qt-related constants
    SIGNAL_TIMEOUT_MS: int = 1000
    EVENT_LOOP_TIMEOUT_MS: int = 100
    
    # File system constants
    THUMBNAIL_SIZE: int = 256
    MAX_FILE_SIZE_MB: int = 100