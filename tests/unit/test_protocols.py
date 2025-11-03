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

# Standard library imports
from typing import TYPE_CHECKING, Any, Protocol

# Third-party imports
import pytest


if TYPE_CHECKING:
    # Standard library imports
    import pathlib

    # Local application imports
    from shot_model import Shot

pytestmark = pytest.mark.unit


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


class ProcessPoolProtocol(Protocol):
    """Protocol for process pool test doubles."""

    __test__ = False

    should_fail: bool
    call_count: int
    commands: list[str]

    def set_outputs(self, output: str) -> None: ...

    def set_errors(self, error: str) -> None: ...

    def execute_workspace_command(
        self, command: str, cache_ttl: int | None = None
    ) -> str: ...

    def reset(self) -> None: ...


class CacheManagerProtocol(Protocol):
    """Protocol for cache manager test interfaces."""

    __test__ = False

    def cache_shots(self, shots: list[Any]) -> None: ...

    def get_cached_shots(self) -> list[dict[str, Any | None]]: ...

    def cache_thumbnail_direct(
        self, source_path: pathlib.Path, show: str, sequence: str, shot: str
    ) -> pathlib.Path | None: ...

    def clear_cache(self) -> None: ...

    def shutdown(self) -> None: ...


class TestLauncherFactory(Protocol):
    """Protocol for launcher factory fixtures."""

    __test__ = False

    def __call__(
        self, name: str = "Test Launcher", command: str = "echo test", **kwargs: Any
    ) -> Any: ...  # Returns CustomLauncher


# Type aliases for common test types
# Using string annotations to avoid pathlib import at module level
TestImagePath = "pathlib.Path"
TestConfigDir = "pathlib.Path"
TestTempDir = "pathlib.Path"
