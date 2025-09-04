"""Factory for ProcessPoolManager with dependency injection support.

This module provides a clean way to inject mock implementations
of ProcessPoolManager for testing and development environments.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from process_pool_manager import ProcessPoolManager
    from tests.test_doubles_library import TestProcessPool

logger = logging.getLogger(__name__)


@runtime_checkable
class ProcessPoolInterface(Protocol):
    """Protocol for process pool implementations.
    
    Both ProcessPoolManager and TestProcessPool must implement this interface.
    """
    
    def execute_workspace_command(
        self,
        command: str,
        cache_ttl: int = 30,
        timeout: int | None = None,
    ) -> str:
        """Execute workspace command."""
        ...
    
    def batch_execute(
        self,
        commands: list[str],
        cache_ttl: int = 30,
        session_type: str = "workspace",
    ) -> dict[str, str | None]:
        """Execute multiple commands in parallel."""
        ...
    
    def invalidate_cache(self, pattern: str | None = None):
        """Invalidate command cache."""
        ...
    
    def shutdown(self):
        """Shutdown the process pool."""
        ...


class ProcessPoolFactory:
    """Factory for creating and managing ProcessPoolManager instances.
    
    This factory allows clean dependency injection of mock implementations
    for testing and development environments.
    """
    
    _instance: ProcessPoolInterface | None = None
    _lock = threading.RLock()
    _override: ProcessPoolInterface | None = None
    _factory_mode: str = "production"  # production, mock, custom
    
    @classmethod
    def set_implementation(cls, implementation: ProcessPoolInterface | None):
        """Set a custom implementation to use instead of the default.
        
        This must be called BEFORE any code imports ProcessPoolManager.
        
        Args:
            implementation: Custom implementation or None to use default
        """
        with cls._lock:
            if cls._instance is not None and implementation is not None:
                logger.warning(
                    "ProcessPoolManager already initialized. "
                    "Set implementation before first use for proper injection."
                )
            cls._override = implementation
            if implementation is not None:
                cls._factory_mode = "custom"
                logger.info("ProcessPoolFactory: Custom implementation injected")
    
    @classmethod
    def set_mock_mode(cls, mock_mode: bool = True):
        """Enable or disable mock mode.
        
        When enabled, TestProcessPool will be used instead of ProcessPoolManager.
        
        Args:
            mock_mode: True to enable mock mode, False for production
        """
        with cls._lock:
            if mock_mode:
                cls._factory_mode = "mock"
                logger.info("ProcessPoolFactory: Mock mode enabled")
            else:
                cls._factory_mode = "production"
                logger.info("ProcessPoolFactory: Production mode enabled")
    
    @classmethod
    def get_instance(cls) -> ProcessPoolInterface:
        """Get the process pool instance based on current configuration.
        
        Returns:
            ProcessPoolInterface implementation (real or mock)
        """
        with cls._lock:
            # If we have an override, use it
            if cls._override is not None:
                return cls._override
            
            # If instance already exists, return it
            if cls._instance is not None:
                return cls._instance
            
            # Create instance based on mode
            if cls._factory_mode == "mock" or os.environ.get("SHOTBOT_MOCK") == "1":
                logger.info("ProcessPoolFactory: Creating mock instance")
                cls._instance = cls._create_mock_instance()
            else:
                logger.info("ProcessPoolFactory: Creating production instance")
                cls._instance = cls._create_production_instance()
            
            return cls._instance
    
    @classmethod
    def _create_production_instance(cls) -> ProcessPoolInterface:
        """Create production ProcessPoolManager instance.
        
        Returns:
            ProcessPoolManager instance
        """
        from process_pool_manager import ProcessPoolManager
        
        # Use the singleton pattern from ProcessPoolManager
        return ProcessPoolManager.get_instance()
    
    @classmethod
    def _create_mock_instance(cls) -> ProcessPoolInterface:
        """Create mock TestProcessPool instance.
        
        Returns:
            TestProcessPool instance with demo data
        """
        from tests.test_doubles_library import TestProcessPool
        import json
        from pathlib import Path
        
        mock_pool = TestProcessPool()
        
        # Load demo shots if available
        demo_shots_path = Path(__file__).parent / "demo_shots.json"
        if demo_shots_path.exists():
            logger.info(f"Loading demo shots from {demo_shots_path}")
            with open(demo_shots_path) as f:
                demo_data = json.load(f)
                outputs = []
                for shot in demo_data.get("shots", []):
                    show = shot.get("show", "demo")
                    seq = shot.get("seq", "seq01")
                    shot_num = shot.get("shot", "0010")
                    outputs.append(f"workspace /shows/{show}/shots/{seq}/{seq}_{shot_num}")
                if outputs:
                    mock_pool.set_outputs(*outputs)
                    logger.info(f"Loaded {len(outputs)} demo shots")
        else:
            # Fallback demo data
            logger.info("Using default demo shots")
            mock_pool.set_outputs(
                "workspace /shows/demo/shots/seq01/seq01_0010",
                "workspace /shows/demo/shots/seq01/seq01_0020",
                "workspace /shows/demo/shots/seq01/seq01_0030",
            )
        
        return mock_pool
    
    @classmethod
    def reset(cls):
        """Reset the factory to initial state.
        
        Useful for testing to ensure clean state between tests.
        """
        with cls._lock:
            # Shutdown existing instance if it has a shutdown method
            if cls._instance is not None:
                if hasattr(cls._instance, 'shutdown'):
                    try:
                        cls._instance.shutdown()
                    except Exception as e:
                        logger.warning(f"Error during shutdown: {e}")
            
            cls._instance = None
            cls._override = None
            cls._factory_mode = "production"
            logger.info("ProcessPoolFactory: Reset to initial state")


def get_process_pool() -> ProcessPoolInterface:
    """Convenience function to get the process pool instance.
    
    This is the recommended way to get a ProcessPoolManager instance
    throughout the application.
    
    Returns:
        ProcessPoolInterface implementation
    """
    return ProcessPoolFactory.get_instance()