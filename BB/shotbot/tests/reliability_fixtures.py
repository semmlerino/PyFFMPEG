"""Reliability fixtures for consistent test execution."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from PySide6.QtCore import QThread, QTimer


@pytest.fixture
def reliable_temp_dir():
    """Create a temporary directory that's properly cleaned up."""
    temp_dir = tempfile.mkdtemp(prefix="shotbot_test_")
    temp_path = Path(temp_dir)

    yield temp_path

    # Cleanup with retry
    for _ in range(3):
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            break
        except (OSError, PermissionError):
            QTimer.singleShot(100, lambda: None)  # Small delay


@pytest.fixture
def managed_threads(qtbot):
    """Fixture to track and cleanup threads."""
    threads: list[QThread] = []

    def create_thread():
        thread = QThread()
        threads.append(thread)
        return thread

    yield create_thread

    # Cleanup all threads
    for thread in threads:
        if thread.isRunning():
            thread.quit()
            thread.wait(1000)
            if thread.isRunning():
                thread.terminate()


@pytest.fixture
def signal_waiter(qtbot):
    """Helper for reliable signal waiting."""

    def wait_for_signal(signal, timeout=1000, raising=True):
        """Wait for signal with proper error handling."""
        with qtbot.waitSignal(signal, timeout=timeout, raising=raising) as blocker:
            return blocker

    return wait_for_signal


@pytest.fixture(autouse=True)
def cleanup_qt_objects(qtbot):
    """Automatically cleanup Qt objects after each test."""
    yield
    # Process events to handle deleteLater
    qtbot.wait(10)


@pytest.fixture
def stable_filesystem(tmp_path):
    """Filesystem operations with stability checks."""

    class StableFS:
        def write_file(self, path: Path, content: str):
            path.write_text(content)
            # Ensure write is complete
            assert path.exists()
            assert path.read_text() == content

        def create_dir(self, path: Path):
            path.mkdir(parents=True, exist_ok=True)
            # Ensure directory is created
            assert path.is_dir()

        def remove_file(self, path: Path):
            if path.exists():
                path.unlink()
            # Ensure file is removed
            assert not path.exists()

    return StableFS()
