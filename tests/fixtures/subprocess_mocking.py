"""Subprocess mocking fixtures for parallel test execution.

This module provides autouse fixtures that mock subprocess execution to prevent
crashes in parallel test execution. Without these mocks, multiple workers running
"ws -sg" commands or spawning Popen processes crash at the C level.

EXCEPTION TO UNIFIED_TESTING_V2.MD GUIDANCE:
- Normally subprocess mocking should NOT be autouse
- But ProcessPoolManager is a singleton used throughout the codebase
- Without global mocking, tests crash in parallel when multiple workers
  try to execute real "ws -sg" commands (C-level subprocess crash)
- This is the pragmatic choice for a singleton dependency

OPT-OUT: Use @pytest.mark.real_subprocess to skip these mocks for tests that
need real subprocess behavior.

Fixtures:
    mock_process_pool_manager: Patches ProcessPoolManager singleton (autouse)
    mock_subprocess_popen: Patches subprocess.Popen globally (autouse)
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
