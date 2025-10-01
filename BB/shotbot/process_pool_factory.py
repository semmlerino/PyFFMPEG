"""Factory for ProcessPoolManager with dependency injection support.

This module provides a clean way to inject mock implementations
of ProcessPoolManager for testing and development environments.
"""

from __future__ import annotations

# Standard library imports
import logging
import os
import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

# Local application imports

if TYPE_CHECKING:
    # Local application imports
    from type_definitions import PerformanceMetricsDict


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

    def invalidate_cache(self, pattern: str | None = None) -> None:
        """Invalidate command cache."""
        ...

    def shutdown(self) -> None:
        """Shutdown the process pool."""
        ...

    def get_metrics(self) -> PerformanceMetricsDict:
        """Get performance metrics."""
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
    _logger: logging.Logger | None = None

    @classmethod
    def _get_logger(cls) -> logging.Logger:
        """Get class-level logger."""
        if cls._logger is None:
            cls._logger = logging.getLogger(cls.__name__)
        return cls._logger

    @classmethod
    def set_implementation(cls, implementation: ProcessPoolInterface | None) -> None:
        """Set a custom implementation to use instead of the default.

        This must be called BEFORE any code imports ProcessPoolManager.

        Args:
            implementation: Custom implementation or None to use default
        """
        with cls._lock:
            if cls._instance is not None and implementation is not None:
                cls._get_logger().warning(
                    "ProcessPoolManager already initialized. "
                    "Set implementation before first use for proper injection."
                )
            cls._override = implementation
            if implementation is not None:
                cls._factory_mode = "custom"
                cls._get_logger().info(
                    "ProcessPoolFactory: Custom implementation injected"
                )

    @classmethod
    def set_mock_mode(cls, mock_mode: bool = True) -> None:
        """Enable or disable mock mode.

        When enabled, TestProcessPool will be used instead of ProcessPoolManager.

        Args:
            mock_mode: True to enable mock mode, False for production
        """
        with cls._lock:
            if mock_mode:
                cls._factory_mode = "mock"
                cls._get_logger().info("ProcessPoolFactory: Mock mode enabled")
            else:
                cls._factory_mode = "production"
                cls._get_logger().info("ProcessPoolFactory: Production mode enabled")

    @classmethod
    def get_factory_mode(cls) -> str:
        """Get the current factory mode.

        Returns:
            Current mode: "production", "mock", or "custom"
        """
        return cls._factory_mode

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
                cls._get_logger().info("ProcessPoolFactory: Creating mock instance")
                cls._instance = cls._create_mock_instance()
            else:
                cls._get_logger().info(
                    "ProcessPoolFactory: Creating production instance"
                )
                cls._instance = cls._create_production_instance()

            return cls._instance

    @classmethod
    def _create_production_instance(cls) -> ProcessPoolInterface:
        """Create production ProcessPoolManager instance.

        Returns:
            ProcessPoolManager instance
        """
        # Local application imports
        from process_pool_manager import ProcessPoolManager

        # Use the singleton pattern from ProcessPoolManager
        return ProcessPoolManager.get_instance()

    @classmethod
    def _create_mock_instance(cls) -> ProcessPoolInterface:
        """Create mock pool instance.

        Prefers the enhanced MockWorkspacePool that properly simulates
        the VFX environment, falls back to TestProcessPool if needed.

        Returns:
            Mock pool instance with demo data
        """
        # Standard library imports
        from pathlib import Path

        # Try to use the enhanced mock pool first
        try:
            # Local application imports
            from mock_workspace_pool import create_mock_pool_from_filesystem

            cls._get_logger().info("Using enhanced MockWorkspacePool")
            mock_pool = create_mock_pool_from_filesystem()

            # The pool already loaded shots from filesystem or demo
            if hasattr(mock_pool, "shots") and mock_pool.shots:
                cls._get_logger().info(
                    f"Mock pool has {len(mock_pool.shots)} shots ready"
                )

            return mock_pool  # type: ignore[return-value]

        except ImportError:
            # Fall back to simple test pool
            cls._get_logger().info("Falling back to TestProcessPool")
            # Standard library imports
            import json

            # Local application imports
            from tests.test_doubles_library import TestProcessPool

            mock_pool = TestProcessPool()

            # Load demo shots and join them with newlines for ws -sg
            demo_shots_path = Path(__file__).parent / "demo_shots.json"
            if demo_shots_path.exists():
                cls._get_logger().info(f"Loading demo shots from {demo_shots_path}")
                with open(demo_shots_path) as f:
                    # JSON structure is dynamic - use type: ignore for demo data
                    demo_data = json.load(f)  # type: ignore[reportAny]
                    outputs: list[str] = []
                    # Dynamic dict access from JSON - all marked as Any
                    for shot in demo_data.get("shots", []):  # type: ignore[reportAny]
                        show: str = shot.get("show", "demo")  # type: ignore[reportAny]
                        seq: str = shot.get("seq", "seq01")  # type: ignore[reportAny]
                        shot_num: str = shot.get("shot", "0010")  # type: ignore[reportAny]
                        outputs.append(
                            f"workspace /shows/{show}/shots/{seq}/{seq}_{shot_num}"
                        )

                    if outputs:
                        # Set as a single output with all shots joined by newlines
                        # This simulates what 'ws -sg' actually returns
                        mock_pool.set_outputs("\n".join(outputs))
                        cls._get_logger().info(
                            f"Loaded {len(outputs)} demo shots as single output"
                        )
            else:
                # Fallback demo data
                cls._get_logger().info("Using default demo shots")
                default_shots = [
                    "workspace /shows/demo/shots/seq01/seq01_0010",
                    "workspace /shows/demo/shots/seq01/seq01_0020",
                    "workspace /shows/demo/shots/seq01/seq01_0030",
                ]
                mock_pool.set_outputs("\n".join(default_shots))

            return mock_pool  # type: ignore[return-value]

    @classmethod
    def reset(cls) -> None:
        """Reset the factory to initial state.

        Useful for testing to ensure clean state between tests.
        """
        with cls._lock:
            # Shutdown existing instance if it has a shutdown method
            if cls._instance is not None:
                if hasattr(cls._instance, "shutdown"):
                    try:
                        cls._instance.shutdown()
                    except Exception as e:
                        cls._get_logger().warning(f"Error during shutdown: {e}")

            cls._instance = None
            cls._override = None
            cls._factory_mode = "production"
            cls._get_logger().info("ProcessPoolFactory: Reset to initial state")


def get_process_pool() -> ProcessPoolInterface:
    """Convenience function to get the process pool instance.

    This is the recommended way to get a ProcessPoolManager instance
    throughout the application.

    Returns:
        ProcessPoolInterface implementation
    """
    return ProcessPoolFactory.get_instance()
