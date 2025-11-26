"""Test doubles for replacing real dependencies in tests.

This module provides test doubles (fakes, stubs, mocks) for complex dependencies
that are difficult or unsafe to use in tests. These doubles implement the same
interfaces as their real counterparts but with controllable behavior.

Fixtures:
    test_process_pool: TestProcessPool instance for mocking ProcessPoolManager
    make_test_launcher: Factory for creating CustomLauncher instances
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest


class TestProcessPool:
    """Test double for ProcessPoolManager implementing ProcessPoolProtocol.

    Provides a configurable test double that tracks calls and allows
    setting custom outputs and errors. Use this instead of real subprocess
    execution to:
    - Prevent crashes in parallel test execution
    - Control command outputs deterministically
    - Track what commands were executed

    Usage:
        def test_something(test_process_pool):
            test_process_pool.set_outputs("output1", "output2")
            # ... code that uses ProcessPoolManager ...
            assert "ws -sg" in test_process_pool.commands
    """

    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(self) -> None:
        self.should_fail = False
        self.fail_with_timeout = False
        self.call_count = 0
        self.commands: list[str] = []
        self._outputs_queue: list[str] = []
        self._errors: str = ""
        self._repeat_output: bool = True  # By default, repeat the same output

    def set_outputs(self, *outputs: str, repeat: bool = True) -> None:
        """Set multiple outputs to return from execute_workspace_command.

        Args:
            *outputs: Variable number of output strings
            repeat: If True (default), returns the last output repeatedly for all calls.
                   If False, pops outputs sequentially and returns empty when exhausted.

        Default behavior (repeat=True) handles race conditions with background threads
        that may call execute_workspace_command() multiple times unpredictably.
        Use repeat=False for tests that need specific sequential outputs.
        """
        self._outputs_queue = list(outputs)
        self._repeat_output = repeat

    def set_errors(self, error: str) -> None:
        """Set errors to raise from execute_workspace_command."""
        self._errors = error

    def execute_workspace_command(
        self,
        command: str,
        cache_ttl: int | None = None,
        timeout: int | None = None,
    ) -> str:
        """Execute a workspace command (test double)."""
        self.call_count += 1
        self.commands.append(command)

        if self.fail_with_timeout:
            raise TimeoutError("Simulated timeout")

        if self.should_fail or self._errors:
            raise RuntimeError(self._errors or "Test error")

        # Return output based on mode
        if self._outputs_queue:
            if self._repeat_output:
                # Return the last output repeatedly (handles background threads)
                return self._outputs_queue[-1]
            # Pop sequentially (for tests needing specific order)
            return self._outputs_queue.pop(0)
        return ""

    def invalidate_cache(self, command: str) -> None:
        """Invalidate the cache for a specific command (test double)."""
        # Track that cache invalidation was called
        self.commands.append(f"invalidate:{command}")

    def reset(self) -> None:
        """Reset the test double state."""
        self.should_fail = False
        self.fail_with_timeout = False
        self.call_count = 0
        self.commands = []
        self._outputs_queue = []
        self._errors = ""
        self._repeat_output = True

    def shutdown(self, timeout: float = 5.0) -> None:
        """Shutdown the test double (no-op for test double)."""
        # Reset state on shutdown for test isolation
        self.reset()

    def find_files_python(self, directory: str, pattern: str) -> list[str]:
        """Find files using Python glob (real implementation for test double).

        This method uses real filesystem operations since it doesn't involve
        subprocess calls that would cause parallel test issues.
        """
        try:
            path = Path(directory)
            if not path.exists():
                return []
            files = list(path.rglob(pattern))
            return [str(f) for f in files]
        except Exception:
            return []


@pytest.fixture
def test_process_pool() -> TestProcessPool:
    """Provide a TestProcessPool instance for mocking ProcessPoolManager.

    Returns:
        TestProcessPool instance that can be configured to return
        specific outputs or simulate errors.

    NOTE: Tests that define their own local `test_process_pool` fixture
    will shadow this global one - the local fixture takes precedence.
    """
    return TestProcessPool()


@pytest.fixture
def make_test_launcher():
    """Factory fixture for creating CustomLauncher instances for testing.

    Returns a callable that creates CustomLauncher instances with sensible
    defaults for testing. All parameters are optional.

    Example usage:
        def test_launcher(make_test_launcher):
            launcher = make_test_launcher(name="Test", command="echo test")
            assert launcher.name == "Test"
    """
    from launcher import CustomLauncher

    def _make_launcher(
        name: str = "Test Launcher",
        command: str = "echo {shot_name}",
        description: str = "Test launcher",
        category: str = "test",
        launcher_id: str | None = None,
    ):
        """Create a CustomLauncher instance for testing.

        Args:
            name: Launcher name (default: "Test Launcher")
            command: Command to execute (default: "echo {shot_name}")
            description: Launcher description (default: "Test launcher")
            category: Launcher category (default: "test")
            launcher_id: Launcher ID (default: auto-generated UUID)

        Returns:
            CustomLauncher instance
        """
        if launcher_id is None:
            launcher_id = str(uuid.uuid4())

        return CustomLauncher(
            id=launcher_id,
            name=name,
            command=command,
            description=description,
            category=category,
        )

    return _make_launcher
