"""Type-safe protocols for test fixtures and doubles.

This module defines protocols that test doubles should implement
to ensure type safety without over-specification.
"""

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns


from __future__ import annotations

from pathlib import Path as PathType  # Renamed to avoid pytest collection
from typing import Any, Dict, List, Optional, Protocol

import pytest

from shot_model import Shot

pytestmark = pytest.mark.unit


from tests.test_doubles_library import TestCacheManager, TestProcessPool


class TestShotFactory(Protocol):
    """Protocol for shot factory fixtures."""

    __test__ = False

    def __call__(
        self,
        show: str = "test",
        sequence: str = "seq01",
        shot: str = "0010",
        with_thumbnail: bool = True,
    ) -> Shot: ...


class TestProcessPool(Protocol):
    """Protocol for process pool test doubles."""

    __test__ = False

    should_fail: bool
    call_count: int
    commands: List[str]

    def set_outputs(self, output: str) -> None: ...

    def set_errors(self, error: str) -> None: ...

    def execute_workspace_command(
        self, command: str, cache_ttl: Optional[int] = None
    ) -> str: ...

    def reset(self) -> None: ...


class TestCacheManager(Protocol):
    """Protocol for cache manager test interfaces."""

    __test__ = False

    def cache_shots(self, shots: List[Any]) -> None: ...

    def get_cached_shots(self) -> Optional[List[Dict[str, Any]]]: ...

    def cache_thumbnail_direct(
        self, source_path: PathType, show: str, sequence: str, shot: str
    ) -> Optional[PathType]: ...

    def clear_cache(self) -> None: ...

    def shutdown(self) -> None: ...


class TestLauncherFactory(Protocol):
    """Protocol for launcher factory fixtures."""

    __test__ = False

    def __call__(
        self, name: str = "Test Launcher", command: str = "echo test", **kwargs: Any
    ) -> Any: ...  # Returns CustomLauncher


# Type aliases for common test types
TestImagePath = PathType
TestConfigDir = PathType
TestTempDir = PathType
