"""Refactored ProcessPool factory with cleaner abstraction.

This version uses a more maintainable factory pattern with
clear separation of concerns and better configurability.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import threading
from abc import ABC, abstractmethod
from enum import Enum
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class PoolMode(Enum):
    """Process pool operation modes."""

    PRODUCTION = "production"
    MOCK = "mock"
    TEST = "test"
    CUSTOM = "custom"


@runtime_checkable
class ProcessPoolProtocol(Protocol):
    """Protocol that all process pools must implement."""

    def execute_workspace_command(
        self,
        command: str,
        cache_ttl: int = 30,
        timeout: int | None = None,
    ) -> str:
        """Execute a workspace command."""
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
        """Invalidate cached results."""
        ...

    def shutdown(self) -> None:
        """Clean shutdown of the pool."""
        ...


class PoolCreator(ABC):
    """Abstract creator for process pools."""

    @abstractmethod
    def create_pool(self) -> ProcessPoolProtocol:
        """Create a process pool instance.

        Returns:
            ProcessPool implementation
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this creator can create a pool.

        Returns:
            True if pool can be created
        """
        pass


class ProductionPoolCreator(PoolCreator):
    """Creates production ProcessPoolManager instances."""

    def create_pool(self) -> ProcessPoolProtocol:
        """Create production pool.

        Returns:
            ProcessPoolManager instance
        """
        from process_pool_manager import ProcessPoolManager

        logger.info("Creating production ProcessPoolManager")
        return ProcessPoolManager.get_instance()

    def is_available(self) -> bool:
        """Check if production pool is available.

        Returns:
            True if in production environment
        """
        # Could check for VFX environment variables, network access, etc.
        return not os.environ.get("SHOTBOT_MOCK")


class MockPoolCreator(PoolCreator):
    """Creates mock pool instances for testing/development."""

    def __init__(self, mock_type: str = "auto") -> None:
        """Initialize mock creator.

        Args:
            mock_type: Type of mock data to use
        """
        self.mock_type = mock_type

    def create_pool(self) -> ProcessPoolProtocol:
        """Create mock pool.

        Returns:
            Mock pool instance
        """
        from mock_strategy import create_mock_pool

        logger.info(f"Creating mock pool with type: {self.mock_type}")
        return create_mock_pool(self.mock_type)

    def is_available(self) -> bool:
        """Mock pools are always available.

        Returns:
            Always True
        """
        return True


class TestPoolCreator(PoolCreator):
    """Creates test pool for unit tests."""

    def create_pool(self) -> ProcessPoolProtocol:
        """Create test pool.

        Returns:
            TestProcessPool instance
        """
        from tests.test_doubles_library import TestProcessPool

        logger.info("Creating TestProcessPool for unit tests")
        pool = TestProcessPool()

        # Set up minimal test data
        pool.set_outputs(
            "workspace /shows/test/shots/seq01/seq01_0010\n"
            "workspace /shows/test/shots/seq01/seq01_0020"
        )

        return pool

    def is_available(self) -> bool:
        """Check if test pool is available.

        Returns:
            True if test module is available
        """
        return importlib.util.find_spec("tests.test_doubles_library") is not None


class ProcessPoolFactoryRefactored:
    """Refactored factory with cleaner design and configuration."""

    _lock = threading.RLock()
    _instance: ProcessPoolProtocol | None = None
    _mode: PoolMode = PoolMode.PRODUCTION
    _custom_instance: ProcessPoolProtocol | None = None
    _creators: dict[PoolMode, PoolCreator] = {}

    @classmethod
    def configure(
        cls,
        mode: PoolMode | str | None = None,
        mock_type: str = "auto",
    ) -> None:
        """Configure the factory before first use.

        Args:
            mode: Pool mode to use
            mock_type: Type of mock data if using mock mode
        """
        with cls._lock:
            if cls._instance is not None:
                logger.warning(
                    "Factory already initialized. "
                    "Configure before first use for best results."
                )

            # Set mode
            if isinstance(mode, str):
                mode = PoolMode(mode)
            if mode:
                cls._mode = mode

            # Register creators
            cls._register_creators(mock_type)

            logger.info(f"Factory configured for mode: {cls._mode.value}")

    @classmethod
    def _register_creators(cls, mock_type: str) -> None:
        """Register pool creators.

        Args:
            mock_type: Mock data type for mock creator
        """
        cls._creators[PoolMode.PRODUCTION] = ProductionPoolCreator()
        cls._creators[PoolMode.MOCK] = MockPoolCreator(mock_type)
        cls._creators[PoolMode.TEST] = TestPoolCreator()

    @classmethod
    def set_custom_instance(cls, instance: ProcessPoolProtocol) -> None:
        """Set a custom pool instance.

        Args:
            instance: Custom pool implementation
        """
        with cls._lock:
            cls._custom_instance = instance
            cls._mode = PoolMode.CUSTOM
            logger.info("Custom pool instance registered")

    @classmethod
    def get_instance(cls) -> ProcessPoolProtocol:
        """Get the configured pool instance.

        Returns:
            ProcessPool implementation

        Raises:
            RuntimeError: If no suitable pool can be created
        """
        with cls._lock:
            # Return existing instance if available
            if cls._instance is not None:
                return cls._instance

            # Return custom instance if set
            if cls._mode == PoolMode.CUSTOM and cls._custom_instance:
                cls._instance = cls._custom_instance
                return cls._instance

            # Auto-detect mode from environment if not configured
            if not cls._creators:
                cls._auto_configure()

            # Create instance using appropriate creator
            creator = cls._creators.get(cls._mode)
            if not creator:
                raise RuntimeError(f"No creator for mode: {cls._mode}")

            if not creator.is_available():
                # Fallback to mock if production not available
                if cls._mode == PoolMode.PRODUCTION:
                    logger.warning("Production pool not available, using mock")
                    cls._mode = PoolMode.MOCK
                    creator = cls._creators[PoolMode.MOCK]
                else:
                    raise RuntimeError(f"Pool not available: {cls._mode}")

            cls._instance = creator.create_pool()
            return cls._instance

    @classmethod
    def _auto_configure(cls) -> None:
        """Auto-configure based on environment."""
        # Check environment variables
        if os.environ.get("SHOTBOT_TEST"):
            cls.configure(PoolMode.TEST)
        elif os.environ.get("SHOTBOT_MOCK"):
            cls.configure(PoolMode.MOCK)
        else:
            cls.configure(PoolMode.PRODUCTION)

    @classmethod
    def reset(cls) -> None:
        """Reset factory to initial state."""
        with cls._lock:
            # Shutdown existing instance
            if cls._instance:
                try:
                    cls._instance.shutdown()
                except Exception as e:
                    logger.error(f"Error during shutdown: {e}")

            cls._instance = None
            cls._custom_instance = None
            cls._mode = PoolMode.PRODUCTION
            cls._creators.clear()

            logger.info("Factory reset to initial state")

    @classmethod
    def get_mode(cls) -> PoolMode:
        """Get current factory mode.

        Returns:
            Current pool mode
        """
        return cls._mode


# Convenience function for backward compatibility
def get_process_pool() -> ProcessPoolProtocol:
    """Get the process pool instance.

    Returns:
        ProcessPool implementation
    """
    return ProcessPoolFactoryRefactored.get_instance()
