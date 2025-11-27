"""Subprocess mocking fixtures for parallel test execution.

This module provides fixtures for mocking subprocess execution. The default
behavior prevents subprocess crashes in parallel test execution while allowing
tests to opt into real subprocess execution or controlled error scenarios.

DESIGN PHILOSOPHY:
- Autouse mocks provide SAFETY (prevent C-level crashes in parallel execution)
- Opt-in mocks provide CONTROL (test error handling, verify commands, etc.)
- Tests needing real subprocess use @pytest.mark.real_subprocess

Fixture Types:
    AUTOUSE (safety):
        mock_process_pool_manager: Patches ProcessPoolManager singleton
        mock_subprocess_popen: Patches subprocess.Popen globally

    OPT-IN (control):
        subprocess_mock: Controllable mock for testing command execution
        subprocess_error_mock: Pre-configured for error scenarios
        subprocess_timeout_mock: Simulates timeout/hanging processes

OPT-OUT: Use @pytest.mark.real_subprocess to skip autouse mocks for tests that
need real subprocess behavior.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_process_pool_manager(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Patch ProcessPoolManager to use test double (AUTOUSE).

    This fixture patches ProcessPoolManager globally to prevent subprocess crashes
    in parallel test execution. Many components (ShotModel, Workers) internally use
    ProcessPoolManager as a singleton, making it impractical to mock at every call site.

    IMPORTANT: This fixture creates its own internal TestProcessPool to avoid
    interfering with test-local `test_process_pool` fixtures. Tests that define
    their own `test_process_pool` fixture and pass it to components will use their
    local version, while this mock just prevents the singleton from spawning processes.

    Args:
        request: Pytest request for marker checking
        monkeypatch: Pytest monkeypatch fixture

    OPT-OUT: Use @pytest.mark.real_subprocess to skip this mock.
    """
    # Allow opt-out for tests that need real subprocess behavior
    if "real_subprocess" in [m.name for m in request.node.iter_markers()]:
        return  # Skip mock for this test

    # Import and create TestProcessPool directly (not via fixture) to avoid
    # interfering with test-local test_process_pool fixtures
    from tests.fixtures.test_doubles import TestProcessPool

    internal_pool = TestProcessPool()

    # Patch the singleton instance directly - get_instance() checks this first
    monkeypatch.setattr(
        "process_pool_manager.ProcessPoolManager._instance",
        internal_pool,
    )


@pytest.fixture(autouse=True)
def mock_subprocess_popen(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock subprocess.Popen to prevent crashes in launcher/worker.py (AUTOUSE).

    launcher/worker.py directly calls subprocess.Popen (not through ProcessPoolManager),
    which causes parallel test crashes. This fixture mocks Popen globally.

    Args:
        request: Pytest request for marker checking
        monkeypatch: Pytest monkeypatch fixture

    OPT-OUT: Use @pytest.mark.real_subprocess to skip this mock.
    """
    # Allow opt-out for tests that need real subprocess behavior
    if "real_subprocess" in [m.name for m in request.node.iter_markers()]:
        return  # Skip mock for this test

    mock_popen = MagicMock()
    mock_process = mock_popen.return_value
    mock_process.pid = 12345
    mock_process.poll.return_value = 0  # Process finished
    mock_process.wait.return_value = 0  # Exit code 0
    mock_process.returncode = 0
    # Use real file-like objects instead of None (Qt threading requires real file objects)
    mock_process.stdout = io.BytesIO(b"")
    mock_process.stderr = io.BytesIO(b"")
    mock_process.communicate.return_value = (b"", b"")

    # Patch in launcher.worker module namespace (uses `import subprocess`)
    monkeypatch.setattr("launcher.worker.subprocess.Popen", mock_popen)
    # Also patch in subprocess module for any other direct callers
    monkeypatch.setattr("subprocess.Popen", mock_popen)


class SubprocessMock:
    """Controllable subprocess mock for testing command execution.

    This class provides methods to configure expected subprocess behavior,
    including stdout, stderr, return codes, and exceptions.

    Usage:
        def test_command_output(subprocess_mock):
            subprocess_mock.set_output("hello world")
            subprocess_mock.set_return_code(0)
            # ... run code that uses subprocess ...
            assert subprocess_mock.calls == [["my", "command"]]
    """

    def __init__(self) -> None:
        self._mock = MagicMock()
        self._calls: list[list[str]] = []
        self._stdout = b""
        self._stderr = b""
        self._returncode = 0
        self._should_raise: Exception | None = None
        self._setup_mock()

    def _setup_mock(self) -> None:
        """Configure mock behavior."""

        def popen_side_effect(args: list[str], **kwargs: object) -> MagicMock:
            if self._should_raise:
                raise self._should_raise
            self._calls.append(list(args) if isinstance(args, (list, tuple)) else [str(args)])
            process = MagicMock()
            process.pid = 99999
            process.poll.return_value = self._returncode
            process.wait.return_value = self._returncode
            process.returncode = self._returncode
            process.stdout = io.BytesIO(self._stdout)
            process.stderr = io.BytesIO(self._stderr)
            process.communicate.return_value = (self._stdout, self._stderr)
            return process

        self._mock.side_effect = popen_side_effect

    @property
    def mock(self) -> MagicMock:
        """Get the underlying mock object for patching."""
        return self._mock

    @property
    def calls(self) -> list[list[str]]:
        """Get list of command arguments passed to subprocess."""
        return self._calls

    def set_output(self, stdout: str, stderr: str = "") -> None:
        """Set stdout and stderr for mock subprocess."""
        self._stdout = stdout.encode("utf-8")
        self._stderr = stderr.encode("utf-8")

    def set_return_code(self, code: int) -> None:
        """Set return code for mock subprocess."""
        self._returncode = code

    def set_exception(self, exc: Exception) -> None:
        """Configure subprocess to raise an exception."""
        self._should_raise = exc

    def reset(self) -> None:
        """Reset calls and configure defaults."""
        self._calls.clear()
        self._stdout = b""
        self._stderr = b""
        self._returncode = 0
        self._should_raise = None


@pytest.fixture
def subprocess_mock(monkeypatch: pytest.MonkeyPatch) -> SubprocessMock:
    """Provide controllable subprocess mock for testing.

    This fixture gives tests explicit control over subprocess behavior.
    Use this when you need to:
    - Verify specific commands were called
    - Test different stdout/stderr outputs
    - Test error handling for non-zero return codes
    - Test exception handling

    Note: This works alongside the autouse mocks - it provides additional
    control for tests that need to verify subprocess interactions.

    Example:
        def test_launcher_output_parsing(subprocess_mock):
            subprocess_mock.set_output("workspace /shows/test/shots/010/0010")
            subprocess_mock.set_return_code(0)
            # ... test code ...
            assert ["ws", "-sg"] in subprocess_mock.calls
    """
    mock = SubprocessMock()
    monkeypatch.setattr("subprocess.Popen", mock.mock)
    monkeypatch.setattr("launcher.worker.subprocess.Popen", mock.mock)
    return mock


# ==============================================================================
# OPT-IN ERROR FIXTURES
# ==============================================================================
# These fixtures are NOT autouse - use them explicitly when testing error paths


@pytest.fixture
def subprocess_error_mock(monkeypatch: pytest.MonkeyPatch) -> SubprocessMock:
    """Provide subprocess mock pre-configured for error scenarios.

    This fixture returns a SubprocessMock that fails by default (return code 1).
    Use this when testing error handling paths in code that calls subprocess.

    Example:
        def test_launcher_handles_failure(subprocess_error_mock):
            subprocess_error_mock.set_output("", stderr="Command not found")
            result = my_launcher.run_command()
            assert result.success is False
    """
    mock = SubprocessMock()
    mock.set_return_code(1)  # Default to failure
    mock.set_output("", stderr="Command failed")
    monkeypatch.setattr("subprocess.Popen", mock.mock)
    monkeypatch.setattr("launcher.worker.subprocess.Popen", mock.mock)
    return mock


@pytest.fixture
def subprocess_timeout_mock(monkeypatch: pytest.MonkeyPatch) -> SubprocessMock:
    """Provide subprocess mock that simulates timeout/hanging processes.

    This fixture creates a subprocess mock that never returns when polled,
    useful for testing timeout handling logic.

    Example:
        def test_launcher_timeout(subprocess_timeout_mock):
            with pytest.raises(TimeoutError):
                my_launcher.run_command(timeout=1)
    """
    mock = SubprocessMock()
    # Configure to never complete (poll returns None)
    mock._mock.return_value.poll.return_value = None
    mock._mock.return_value.returncode = None
    monkeypatch.setattr("subprocess.Popen", mock.mock)
    monkeypatch.setattr("launcher.worker.subprocess.Popen", mock.mock)
    return mock


@pytest.fixture
def subprocess_exception_mock(monkeypatch: pytest.MonkeyPatch) -> SubprocessMock:
    """Provide subprocess mock that raises OSError on Popen.

    This fixture simulates the case where the subprocess cannot be started
    at all (e.g., command not found, permission denied).

    Example:
        def test_launcher_handles_missing_command(subprocess_exception_mock):
            subprocess_exception_mock.set_exception(
                FileNotFoundError("[Errno 2] No such file or directory: 'missing_cmd'")
            )
            result = my_launcher.run_command("missing_cmd")
            assert result.error_type == "FileNotFoundError"
    """
    mock = SubprocessMock()
    mock.set_exception(FileNotFoundError("[Errno 2] No such file or directory"))
    monkeypatch.setattr("subprocess.Popen", mock.mock)
    monkeypatch.setattr("launcher.worker.subprocess.Popen", mock.mock)
    return mock
