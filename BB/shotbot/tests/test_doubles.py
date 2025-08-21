"""Test doubles and utilities following UNIFIED_TESTING_GUIDE best practices.

This module provides thread-safe test doubles for Qt components that cannot
be used in worker threads, following the guide's Qt Threading Safety section.
"""

from typing import Optional
from unittest.mock import MagicMock

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage


class ThreadSafeTestImage:
    """Thread-safe test double for QPixmap using QImage internally.

    QPixmap is NOT thread-safe and can only be used in the main GUI thread.
    QImage IS thread-safe and can be used in any thread. This class provides
    a QPixmap-like interface while using QImage internally for thread safety.

    Based on Qt's canonical threading pattern for image operations from the
    UNIFIED_TESTING_GUIDE section on Qt Threading Safety.

    Using QPixmap in worker threads causes: "Fatal Python error: Aborted"
    """

    def __init__(self, width: int = 100, height: int = 100):
        """Create a thread-safe test image.

        Args:
            width: Image width in pixels
            height: Image height in pixels
        """
        # Use QImage which is thread-safe, unlike QPixmap
        self._image = QImage(width, height, QImage.Format.Format_RGB32)
        self._width = width
        self._height = height
        self._image.fill(QColor(255, 255, 255))  # Fill with white by default

    def fill(self, color: Optional[QColor] = None) -> None:
        """Fill the image with a color.

        Args:
            color: Color to fill with, defaults to white
        """
        if color is None:
            color = QColor(255, 255, 255)
        self._image.fill(color)

    def isNull(self) -> bool:
        """Check if the image is null.

        Returns:
            True if image is null, False otherwise
        """
        return self._image.isNull()

    def sizeInBytes(self) -> int:
        """Return the size of the image in bytes.

        Returns:
            Size in bytes
        """
        return self._image.sizeInBytes()

    def size(self) -> QSize:
        """Return the size of the image.

        Returns:
            QSize object with width and height
        """
        return QSize(self._width, self._height)

    def save(self, filename: str, format: str = "JPG") -> bool:
        """Save image to file (mock implementation).

        Args:
            filename: Path to save to
            format: Image format

        Returns:
            True (always succeeds in test)
        """
        # Mock implementation for testing
        return True


class TestSignal:
    """Lightweight signal test double for non-Qt components.

    From UNIFIED_TESTING_GUIDE: Use TestSignal for test doubles,
    QSignalSpy only works with real Qt signals.
    """

    __test__ = False

    def __init__(self):
        """Initialize test signal."""
        self.emissions = []
        self.callbacks = []

    def emit(self, *args):
        """Emit signal with arguments.

        Args:
            *args: Arguments to emit with signal
        """
        self.emissions.append(args)
        for callback in self.callbacks:
            callback(*args)

    def connect(self, callback):
        """Connect callback to signal.

        Args:
            callback: Function to call when signal emitted
        """
        self.callbacks.append(callback)

    @property
    def was_emitted(self) -> bool:
        """Check if signal was emitted.

        Returns:
            True if emitted at least once
        """
        return len(self.emissions) > 0

    @property
    def emit_count(self) -> int:
        """Get number of times signal was emitted.

        Returns:
            Number of emissions
        """
        return len(self.emissions)

    def reset(self):
        """Reset signal state for reuse."""
        self.emissions.clear()


class TestSubprocess:
    """Test double for subprocess.run operations.

    Replaces subprocess.run at system boundary for testing.
    Follows UNIFIED_TESTING_GUIDE: Mock only at system boundaries.
    """

    __test__ = False

    def __init__(self):
        """Initialize test subprocess."""
        self.commands = []
        self.results = []
        self.default_result = MagicMock(returncode=0, stdout="test output", stderr="")

    def run(self, cmd, **kwargs):
        """Run command (test implementation).

        Args:
            cmd: Command to run
            **kwargs: Additional arguments

        Returns:
            Mock result object
        """
        self.commands.append((cmd, kwargs))
        if self.results:
            return self.results.pop(0)
        return self.default_result

    def set_results(self, *results):
        """Set predefined results for testing.

        Args:
            *results: Result objects to return
        """
        self.results = list(results)

    def set_success(self, stdout="success"):
        """Set successful result."""
        self.default_result = MagicMock(returncode=0, stdout=stdout, stderr="")

    def set_failure(self, stderr="error"):
        """Set failure result."""
        self.default_result = MagicMock(returncode=1, stdout="", stderr=stderr)


class TestProcessPool:
    """Test double for subprocess operations.

    From UNIFIED_TESTING_GUIDE: Mock only at system boundaries.
    Subprocess calls are external, so this test double replaces them.
    """

    __test__ = False

    def __init__(self):
        """Initialize test process pool."""
        self.commands = []
        self.outputs = []
        self.command_completed = TestSignal()
        self.command_failed = TestSignal()

    def execute(self, command: str, **kwargs) -> str:
        """Execute command (test implementation).

        Args:
            command: Command to execute
            **kwargs: Additional arguments

        Returns:
            Predefined test output
        """
        self.commands.append(command)
        output = self.outputs[0] if self.outputs else "test output"
        self.command_completed.emit(command, output)
        return output

    def set_outputs(self, *outputs):
        """Set predefined outputs for testing.

        Args:
            *outputs: Output strings to return
        """
        self.outputs = list(outputs)


class TestLauncherWorker:
    """Test double for LauncherWorker thread operations.

    Replaces LauncherWorker for testing without actual thread creation.
    Follows UNIFIED_TESTING_GUIDE: Use test doubles instead of mocks.
    """

    __test__ = False

    def __init__(self, launcher_id=None, command=None, dry_run=False):
        """Initialize test launcher worker."""
        self.launcher_id = launcher_id
        self.command = command
        self.dry_run = dry_run
        self.started = TestSignal()
        self.finished = TestSignal()
        self.output = TestSignal()
        self.error = TestSignal()
        self._running = False
        self._result = True

    def start(self):
        """Start worker (test implementation)."""
        self._running = True
        self.started.emit(self.launcher_id)
        if self.dry_run:
            self.output.emit(
                self.launcher_id, f"[DRY RUN] Would execute: {self.command}"
            )
        else:
            self.output.emit(self.launcher_id, "Test output")
        self.finished.emit(self.launcher_id, 0)
        self._running = False

    def isRunning(self):
        """Check if worker is running."""
        return self._running

    def quit(self):
        """Stop worker."""
        self._running = False

    def wait(self, timeout=1000):
        """Wait for worker to finish."""
        self._running = False
        return True

    def set_result(self, success=True):
        """Set the result for testing."""
        self._result = success


class TestShot:
    """Test double for Shot objects.

    Provides real Shot-like behavior for testing.
    """

    __test__ = False

    def __init__(
        self, show="test_show", sequence="seq01", shot="0010", workspace_path=None
    ):
        """Initialize test shot."""
        self.show = show
        self.sequence = sequence
        self.shot = shot
        self.workspace_path = workspace_path or f"/shows/{show}/shots/{sequence}/{shot}"
        self.name = f"{sequence}_{shot}"

    def __str__(self):
        """String representation."""
        return f"{self.show}/{self.sequence}/{self.shot}"

    def get_thumbnail_path(self):
        """Get thumbnail path (test implementation)."""
        return None  # No thumbnail in test


class TestShotModel:
    """Test double for ShotModel.

    Provides shot list management for testing.
    """

    __test__ = False

    def __init__(self):
        """Initialize test shot model."""
        self.shots = []
        self.shots_updated = TestSignal()

    def add_shot(self, shot):
        """Add shot to model."""
        self.shots.append(shot)
        self.shots_updated.emit()

    def get_shots(self):
        """Get all shots."""
        return self.shots

    def refresh_shots(self):
        """Refresh shots (test implementation)."""
        self.shots_updated.emit()
        return True, len(self.shots) > 0


class MockCacheManager:
    """Test double for CacheManager following best practices.

    Provides real behavior for testing without file I/O.
    """

    def __init__(self, cache_dir=None):
        """Initialize mock cache manager.

        Args:
            cache_dir: Optional cache directory (ignored in mock)
        """
        self._cache = {}
        self._thumbnails = {}

    def cache_thumbnail(self, path, show, sequence, shot, wait=False):
        """Cache thumbnail (test implementation).

        Args:
            path: Path to thumbnail
            show: Show name
            sequence: Sequence name
            shot: Shot name
            wait: Whether to wait for completion

        Returns:
            Cached path or None
        """
        key = f"{show}_{sequence}_{shot}"
        self._thumbnails[key] = path

        if wait:
            return path
        else:
            # Return async result object
            result = MagicMock()
            result.result = MagicMock(return_value=path)
            return result

    def get_cached_thumbnail(self, show, sequence, shot):
        """Get cached thumbnail.

        Args:
            show: Show name
            sequence: Sequence name
            shot: Shot name

        Returns:
            Cached path or None
        """
        key = f"{show}_{sequence}_{shot}"
        return self._thumbnails.get(key)

    def clear_cache(self):
        """Clear all caches."""
        self._cache.clear()
        self._thumbnails.clear()


class TestImagePool:
    """Reuse ThreadSafeTestImage instances for performance.

    From UNIFIED_TESTING_GUIDE Performance Considerations section.
    """

    __test__ = False

    def __init__(self):
        """Initialize image pool."""
        self._pool = []

    def get_test_image(self, width=100, height=100):
        """Get test image from pool or create new.

        Args:
            width: Image width
            height: Image height

        Returns:
            ThreadSafeTestImage instance
        """
        if self._pool:
            image = self._pool.pop()
            image.fill()  # Reset to white
            return image
        return ThreadSafeTestImage(width, height)

    def return_image(self, image):
        """Return image to pool for reuse.

        Args:
            image: ThreadSafeTestImage to return
        """
        self._pool.append(image)
