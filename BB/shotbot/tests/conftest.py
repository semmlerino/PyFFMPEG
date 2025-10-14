"""Shared fixtures and configuration for pytest tests following UNIFIED_TESTING_GUIDE.

This conftest provides:
    - Clean, isolated fixtures for tests
    - Common test doubles to reduce duplication
    - Real components with test boundaries
    - Thread-safe testing patterns
    - Consistent marker configuration

Qt components are NOT mocked to allow real signal testing.
Test doubles are used only at system boundaries.
"""

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns

# pyright: basic

from __future__ import annotations

# Standard library imports
import gc
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

# CRITICAL: Set Qt to offscreen mode BEFORE any Qt imports
# This must happen before ANY Qt modules are imported
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_LOGGING_RULES"] = "*.debug=false"
os.environ["PYTEST_QT_API"] = "pyside6"

# Third-party imports
import pytest

# Now we can import Qt, but immediately patch show methods
from PySide6.QtCore import QCoreApplication, QEventLoop, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox, QWidget

if TYPE_CHECKING:
    from PySide6.QtGui import QShowEvent

# CRITICAL: Monkey-patch Qt show methods at module import time
# This ensures no widgets can ever show, even if created at module level
_original_widget_show = QWidget.show
_original_widget_hide = QWidget.hide
_original_widget_setVisible = QWidget.setVisible
_original_widget_isVisible = QWidget.isVisible
_original_widget_showEvent = QWidget.showEvent
_original_dialog_exec = QDialog.exec
_original_dialog_exec_ = getattr(QDialog, "exec_", None)
_original_mainwindow_show = QMainWindow.show
_original_eventloop_exec = QEventLoop.exec
_original_eventloop_exec_ = getattr(QEventLoop, "exec_", None)

# Track "virtually visible" widgets for testing
_virtually_visible_widgets = set()


def _mock_widget_show(self: QWidget) -> None:
    """Prevent widgets from actually showing."""
    # Mark as "shown" for tests without actually showing
    _virtually_visible_widgets.add(id(self))
    # Don't call the original show


def _mock_widget_hide(self: QWidget) -> None:
    """Hide widget by removing from virtually visible set."""
    _virtually_visible_widgets.discard(id(self))
    # Don't call the original hide


def _mock_widget_setVisible(self: QWidget, visible: bool) -> None:
    """Prevent widgets from becoming visible if visible=True."""
    if not visible:
        # Allow hiding
        _virtually_visible_widgets.discard(id(self))
    else:
        # Mark as "visible" for tests without actually showing
        _virtually_visible_widgets.add(id(self))


def _mock_widget_isVisible(self: QWidget) -> bool:
    """Return virtual visibility state for tests."""
    # Return True if widget was "shown" in test
    return id(self) in _virtually_visible_widgets


def _mock_widget_showEvent(self: QWidget, event: QShowEvent) -> None:
    """Prevent show events from propagating."""
    # Accept the event but don't show anything
    if event:
        event.accept()


def _mock_dialog_exec(self: QDialog) -> int:
    """Prevent dialogs from blocking."""
    return QDialog.DialogCode.Accepted


def _mock_eventloop_exec(self: QEventLoop) -> int:
    """Prevent event loops from blocking in tests while allowing signal delivery."""
    # Process events more thoroughly to allow QThreadPool signals to propagate
    # Standard library imports
    import time

    start_time = time.time()
    max_duration = 0.02  # Process events for up to 20ms (reduced from 100ms)

    while time.time() - start_time < max_duration:
        QCoreApplication.processEvents()
        QCoreApplication.sendPostedEvents()  # Process deferred deletions
        time.sleep(0.001)  # Small delay (1ms)

    # Final processing to ensure all signals are delivered
    QCoreApplication.processEvents()
    return 0


# Apply the patches globally
QWidget.show = _mock_widget_show
QWidget.hide = _mock_widget_hide
QWidget.setVisible = _mock_widget_setVisible
QWidget.isVisible = _mock_widget_isVisible
QWidget.showEvent = _mock_widget_showEvent
QMainWindow.show = _mock_widget_show  # Also patch QMainWindow specifically
QDialog.exec = _mock_dialog_exec
QEventLoop.exec = _mock_eventloop_exec
if _original_dialog_exec_:
    QDialog.exec_ = _mock_dialog_exec
if _original_eventloop_exec_:
    QEventLoop.exec_ = _mock_eventloop_exec

# Also prevent QMessageBox from showing
QMessageBox.critical = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.information = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes

if TYPE_CHECKING:
    # Standard library imports
    from collections.abc import Callable, Generator

    # Local application imports
    from cache_manager import CacheManager
    from launcher.models import CustomLauncher
    from shot_model import Shot
    from tests.test_doubles_extended import (
        TestCache,
        TestCommand,
        TestFileSystem,
        TestWorker,
    )
    from tests.test_doubles_library import TestProcessPool, ThreadSafeTestImage

# Import protocols for type safety

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Local application imports
# Import test doubles library for proper test double patterns
import contextlib

from tests.test_doubles_library import TestProcessPool

# =============================================================================
# Factory Fixtures (UNIFIED_TESTING_GUIDE Best Practice)
# =============================================================================


@pytest.fixture
def make_shot() -> Callable[[str, str, str, str | None], Shot]:
    """Factory fixture for creating Shot instances with customizable parameters.

    Following UNIFIED_TESTING_GUIDE pattern from lines 27-37.
    Creates Shot instances with flexible, test-specific parameters.
    """
    # Local application imports
    from shot_model import Shot

    def _make_shot(
        show: str = "test",
        seq: str = "seq1",
        shot: str = "0010",
        workspace_path: str | None = None,
    ) -> Shot:
        if workspace_path is None:
            workspace_path = f"/shows/{show}/{seq}/{seq}_{shot}"
        return Shot(show, seq, shot, workspace_path)

    return _make_shot


@pytest.fixture
def make_launcher() -> Generator[
    Callable[[str | None, str, str, str, str], CustomLauncher], None, None
]:
    """Factory fixture for creating CustomLauncher instances.

    Following UNIFIED_TESTING_GUIDE factory pattern.
    Creates CustomLauncher instances with flexible parameters for testing.
    """
    # Local application imports
    from launcher.models import CustomLauncher

    created_launchers: list[CustomLauncher] = []

    def _make_launcher(
        id: str | None = None,
        name: str = "Test Launcher",
        command: str = "echo {shot_name}",
        description: str = "Test launcher for unit tests",
        category: str = "test",
    ) -> CustomLauncher:
        launcher_id = id or f"test_launcher_{len(created_launchers)}"
        launcher = CustomLauncher(
            id=launcher_id,
            name=name,
            description=description,
            command=command,
            category=category,
        )
        created_launchers.append(launcher)
        return launcher

    yield _make_launcher

    # Cleanup - clear created launchers list
    created_launchers.clear()


@pytest.fixture
def make_cache_manager() -> Generator[Callable[[Path, str], CacheManager], None, None]:
    """Factory fixture for creating CacheManager instances with tmp_path.

    Following UNIFIED_TESTING_GUIDE factory pattern.
    Creates isolated CacheManager instances with temporary directories.
    """
    # Local application imports
    from cache_manager import CacheManager

    created_managers: list[CacheManager] = []

    def _make_cache_manager(
        tmp_path: Path, cache_subdir: str = "cache"
    ) -> CacheManager:
        cache_dir = tmp_path / cache_subdir
        cache_dir.mkdir(exist_ok=True)

        manager = CacheManager(cache_dir=cache_dir)
        created_managers.append(manager)
        return manager

    yield _make_cache_manager

    # Cleanup all created managers
    for manager in created_managers:
        try:
            manager.clear_cache()
            manager.shutdown()
        except Exception:
            pass  # Ignore cleanup errors
    created_managers.clear()


@pytest.fixture
def make_process_pool() -> Generator[Callable[[str], TestProcessPool], None, None]:
    """Factory fixture for creating TestProcessPoolManager instances.

    Following UNIFIED_TESTING_GUIDE factory pattern.
    Creates test doubles for process pool boundary mocking.
    """
    # Local application imports
    from tests.test_doubles_library import TestProcessPool

    created_pools: list[TestProcessPool] = []

    def _make_process_pool(
        default_output: str = "workspace /test/path",
    ) -> TestProcessPool:
        pool = TestProcessPool()
        pool.default_output = default_output
        created_pools.append(pool)
        return pool

    yield _make_process_pool

    # Cleanup all created pools
    for pool in created_pools:
        try:
            pool.reset()
        except Exception:
            pass  # Ignore cleanup errors
    created_pools.clear()


@pytest.fixture
def make_test_widget(qtbot: Any) -> Generator[Callable[..., QWidget], None, None]:
    """Factory for creating test Qt widgets with proper cleanup.
    Following UNIFIED_TESTING_GUIDE pattern for Qt testing.
    """
    # Third-party imports
    from PySide6.QtWidgets import QWidget

    created_widgets: list[QWidget] = []

    def _make_widget(widget_class: type[QWidget] = QWidget, **kwargs: Any) -> QWidget:
        widget = widget_class(**kwargs)
        qtbot.addWidget(widget)  # Critical for cleanup
        created_widgets.append(widget)
        return widget

    yield _make_widget

    # Cleanup
    for widget in created_widgets:
        if widget and not widget.isDeleted():
            widget.deleteLater()


@pytest.fixture
def make_test_worker() -> Generator[Callable[[str], TestWorker], None, None]:
    """Factory for creating thread-safe test workers.
    CRITICAL: Uses ThreadSafeTestImage, not QPixmap!
    """
    # Local application imports
    from tests.test_doubles_extended import TestWorker

    created_workers: list[TestWorker] = []

    def _make_worker(name: str = "test_worker") -> TestWorker:
        worker = TestWorker()
        worker.name = name
        created_workers.append(worker)
        return worker

    yield _make_worker

    # Cleanup
    for worker in created_workers:
        if worker.is_running:
            worker.complete(None)


@pytest.fixture
def make_test_cache(
    tmp_path: Path,
) -> Generator[Callable[[str], TestCache], None, None]:
    """Factory for creating test cache instances.
    Each cache gets its own temporary directory.
    """
    created_caches: list[TestCache] = []

    def _make_cache(name: str = "cache") -> TestCache:
        # Local application imports
        from tests.test_doubles_extended import TestCache

        cache_dir = tmp_path / name
        cache_dir.mkdir(exist_ok=True)
        cache = TestCache()
        cache.cache_dir = cache_dir
        created_caches.append(cache)
        return cache

    yield _make_cache

    # Cleanup
    for cache in created_caches:
        cache.clear()


@pytest.fixture
def make_test_command() -> Callable[[str], TestCommand]:
    """Factory for creating test command executors.
    Tracks executed commands and provides controlled outputs.
    """

    def _make_command(default_output: str = "success") -> TestCommand:
        # Local application imports
        from tests.test_doubles_extended import TestCommand

        executor = TestCommand()
        executor.default_output = default_output
        return executor

    return _make_command


@pytest.fixture
def make_test_filesystem(tmp_path: Path) -> Callable[[], TestFileSystem]:
    """Factory for creating VFX directory structures.
    Creates realistic /shows/{show}/shots/{seq}/{seq}_{shot} paths.
    """

    def _make_filesystem() -> TestFileSystem:
        # Local application imports
        from tests.test_doubles_extended import TestFileSystem

        fs = TestFileSystem(tmp_path)
        return fs

    return _make_filesystem


@pytest.fixture
def workspace_outputs() -> dict[str, str]:
    """Common workspace command outputs for testing.
    Provides realistic ws -sg output patterns.
    """
    return {
        "single": "workspace /shows/test/shots/seq01/seq01_0010",
        "multiple": (
            "workspace /shows/test/shots/seq01/seq01_0010\n"
            "workspace /shows/test/shots/seq01/seq01_0020\n"
            "workspace /shows/test/shots/seq02/seq02_0010"
        ),
        "vfx_production": (
            "workspace /shows/gator/shots/012_DC/012_DC_1000\n"
            "workspace /shows/jack_ryan/shots/DB_256/DB_256_1200"
        ),
        "empty": "",
        "invalid": "no workspace prefix here",
    }


def pytest_configure(config: Any) -> None:
    """Configure pytest with custom markers following UNIFIED_TESTING_GUIDE."""
    # Register custom markers
    config.addinivalue_line("markers", "unit: Unit tests for individual components")
    config.addinivalue_line(
        "markers", "integration: Integration tests for component interactions"
    )
    config.addinivalue_line("markers", "performance: Performance and benchmark tests")
    config.addinivalue_line("markers", "threading: Threading and concurrency tests")
    config.addinivalue_line("markers", "qt: Tests requiring Qt event loop")
    config.addinivalue_line("markers", "fast: Tests that complete in <100ms")
    config.addinivalue_line("markers", "slow: Tests that take >1s")
    config.addinivalue_line("markers", "critical: Critical path tests that must pass")
    config.addinivalue_line("markers", "wsl: Tests optimized for WSL environment")
    config.addinivalue_line("markers", "flaky: Known flaky tests requiring attention")
    config.addinivalue_line(
        "markers",
        "xdist_group(name): Mark tests to run in same xdist worker (for pytest-xdist)",
    )


# =============================================================================
# pytest-qt Configuration for Parallel Execution
# =============================================================================


@pytest.fixture(scope="session")
def qapp_cls():
    """Force pytest-qt to always create QApplication instead of QCoreApplication.

    This is critical for parallel execution with pytest-xdist. Without this,
    pytest-qt may create QCoreApplication in some workers, and when a test
    needs QPixmap (which requires QGuiApplication/QApplication), it will fail
    with "QPixmap cannot be created without a QGuiApplication".

    By forcing QApplication for all workers, we ensure compatibility with all
    Qt GUI operations including QPixmap, QImage with .toPixmap(), etc.

    See: https://pytest-qt.readthedocs.io/en/latest/app_fixtures.html
    """
    return QApplication


@pytest.fixture(scope="session", autouse=True)
def ensure_qapp_early() -> Generator[QApplication, None, None]:
    """CRITICAL: Create QApplication BEFORE any tests run to prevent parallel crashes.

    In parallel execution, widgets are created before pytest-qt's qapp fixture runs.
    This causes crashes in LoggingMixin.__init__() when super().__init__() tries to
    initialize Qt widgets without a QApplication instance.

    This autouse session fixture ensures QApplication exists from the very start,
    eliminating the race condition between widget creation and Qt initialization.

    MUST be session scope and autouse=True to run before any test setup.
    Directly creates QApplication (not QCoreApplication) to ensure GUI operations work.
    """
    # Create QApplication if it doesn't exist yet
    # MUST use QApplication directly, not qapp_cls, to avoid fixture ordering issues
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    return app

    # Don't quit - let pytest-qt handle cleanup


# =============================================================================
# Session-Level Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Provide path to test data directory."""
    return Path(__file__).parent / "fixtures" / "data"


@pytest.fixture(scope="session")
def performance_threshold() -> dict[str, int]:
    """Performance thresholds for benchmark tests."""
    return {
        "thumbnail_processing": 100,  # ms
        "shot_refresh": 500,  # ms
        "scene_discovery": 1000,  # ms
        "cache_operation": 50,  # ms
    }


# =============================================================================
# Cache Isolation Fixtures
# =============================================================================


# Removed duplicate import - already imported above


@pytest.fixture(
    autouse=False
)  # Can be enabled per-test or per-class using pytest.mark.usefixtures
def isolated_test_environment() -> Generator[None, None, None]:
    """Ensure complete test isolation by clearing all caches and shared state.

    This fixture runs before and after every test to ensure:
    1. All utility caches are cleared
    2. CacheManager instances don't share state
    3. No global state persists between tests
    4. Qt objects are properly cleaned up
    5. Garbage collection removes any lingering objects
    6. Caching is disabled during tests to prevent contamination
    """
    # Clear utils caches and disable caching before test
    try:
        # Local application imports
        from utils import clear_all_caches, disable_caching

        clear_all_caches()
        disable_caching()
    except ImportError:
        pass

    # Clear any Qt-related caches or shared objects
    try:
        # Process any pending Qt events to ensure cleanup
        # Third-party imports
        from PySide6.QtCore import QCoreApplication

        # Local application imports
        from tests.helpers.synchronization import process_qt_events

        app = QCoreApplication.instance()
        if app:
            process_qt_events(app, 10)
    except ImportError:
        pass

    # Force garbage collection to ensure clean state
    gc.collect()

    yield

    # Clear utils caches and re-enable caching after test
    try:
        # Local application imports
        from utils import clear_all_caches, enable_caching

        clear_all_caches()
        enable_caching()
    except ImportError:
        pass

    # Process Qt events after test cleanup
    try:
        # Third-party imports
        from PySide6.QtCore import QCoreApplication

        # Local application imports
        from tests.helpers.synchronization import process_qt_events

        app = QCoreApplication.instance()
        if app:
            process_qt_events(app, 10)
    except ImportError:
        pass

    # Final garbage collection to prevent memory leaks
    gc.collect()


# =============================================================================
# Cache Testing Fixtures
# =============================================================================


@pytest.fixture
def cache_isolation() -> Any:
    """Provide cache isolation context manager for tests that need explicit control.

    Use this fixture when a test needs to explicitly control cache isolation,
    for example when testing cache behavior itself.
    """
    try:
        # Local application imports
        from utils import CacheIsolation

        return CacheIsolation
    except ImportError:
        # Fallback no-op context manager
        # Standard library imports
        from contextlib import contextmanager

        @contextmanager
        def no_op() -> Generator[None, None, None]:
            yield

        return no_op


# =============================================================================
# Qt Application Fixtures for Threading Tests
# =============================================================================


@pytest.fixture(scope="session")
def ensure_qapp() -> Generator[QApplication | None, None, None]:
    """Ensure QApplication instance exists for the entire test session.

    This ensures proper Qt event loop for signal processing.
    Note: Uses session scope to ensure single app instance.
    NOT autouse - pytest-qt's qapp fixture handles this automatically.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
    # Don't quit here - let pytest-qt handle cleanup


@pytest.fixture
def qt_signal_blocker() -> Callable[[int], bool]:
    """Helper fixture for blocking until Qt signals are processed.

    Use this when you need to ensure signals are delivered in tests.
    """

    def _process_events(timeout_ms: int = 1000) -> bool:
        """Process Qt events for specified timeout."""
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: None)  # Dummy slot
        timer.start(timeout_ms)

        # Process events until timer expires using event loop
        loop = QEventLoop()
        while timer.isActive():
            loop.processEvents()

        return True

    return _process_events


# =============================================================================
# Test Doubles Fixtures (Following UNIFIED_TESTING_GUIDE)
# =============================================================================


@pytest.fixture
def test_signal() -> Any:
    """Create a SignalDouble instance for non-Qt signal testing."""
    # Local application imports
    from tests.test_doubles_library import SignalDouble

    return SignalDouble()


@pytest.fixture
def test_process_pool() -> Generator[TestProcessPool, None, None]:
    """Create a TestProcessPool for subprocess boundary mocking."""
    # Local application imports
    from tests.test_doubles_library import TestProcessPool

    pool = TestProcessPool()
    yield pool
    pool.reset()  # Clean up after test


@pytest.fixture
def test_filesystem() -> Generator[Any, None, None]:
    """Create a TestFileSystem for in-memory file operations."""
    # Local application imports
    from tests.unit.test_doubles import TestFileSystem

    fs = TestFileSystem()
    yield fs
    fs.clear()  # Clean up after test


@pytest.fixture
def test_cache() -> Generator[Any, None, None]:
    """Create a TestCache for in-memory caching."""
    # Local application imports
    from tests.unit.test_doubles import TestCache

    cache = TestCache()
    yield cache
    cache.clear()  # Clean up after test


# =============================================================================
# Real Component Fixtures (Following UNIFIED_TESTING_GUIDE)
# =============================================================================


@pytest.fixture
def real_cache_manager(tmp_path: Path) -> Generator[CacheManager, None, None]:
    """Create a real CacheManager with temporary storage.

    This follows UNIFIED_TESTING_GUIDE: use real components with test boundaries.
    """
    # Local application imports
    from cache_manager import CacheManager

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    instance = CacheManager(cache_dir=cache_dir)

    yield instance

    # Cleanup
    try:
        instance.clear_cache()
        instance.shutdown()
    except Exception:
        pass


@pytest.fixture
def real_shot_model(
    real_cache_manager: CacheManager, test_process_pool: TestProcessPool
) -> Any:
    """Create a real ShotModel with test doubles only at boundaries.

    This follows UNIFIED_TESTING_GUIDE: real components with boundary mocks.
    """
    # Local application imports
    from shot_model import ShotModel

    model = ShotModel(cache_manager=real_cache_manager, load_cache=False)
    # Only mock the subprocess boundary
    model._process_pool = test_process_pool  # type: ignore[attr-defined]

    return model


@pytest.fixture
def make_test_shot(tmp_path: Path) -> Callable[[str, str, str, bool], Shot]:
    """Factory for creating real Shot objects with actual files.

    This follows UNIFIED_TESTING_GUIDE: test with real files, not mocks.
    """
    # Local application imports
    from shot_model import Shot

    def _make_shot(
        show: str = "test",
        seq: str = "seq01",
        shot: str = "0010",
        with_thumbnail: bool = True,
    ) -> Shot:
        # Create real directory structure
        shot_name = f"{seq}_{shot}"
        shot_path = tmp_path / "shows" / show / "shots" / seq / shot_name
        shot_path.mkdir(parents=True, exist_ok=True)

        if with_thumbnail:
            # Create real thumbnail file
            thumb_dir = (
                shot_path
                / "publish"
                / "editorial"
                / "cutref"
                / "v001"
                / "jpg"
                / "1920x1080"
            )
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_file = thumb_dir / "frame.1001.jpg"
            # Write minimal JPEG data
            thumb_file.write_bytes(
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
            )

        return Shot(show, seq, shot, str(shot_path))

    return _make_shot


@pytest.fixture
def make_real_3de_file(tmp_path: Path) -> Callable[[str, str, str, str, str], Path]:
    """Factory for creating real 3DE scene files.

    This follows UNIFIED_TESTING_GUIDE: test with real files.
    """

    def _make_3de_file(
        show: str = "test",
        seq: str = "seq01",
        shot: str = "0010",
        user: str = "testuser",
        version: str = "v001",
    ) -> Path:
        shot_name = f"{seq}_{shot}"
        scene_path = (
            tmp_path
            / "shows"
            / show
            / "shots"
            / seq
            / shot_name
            / "user"
            / user
            / "3de"
            / "mm-default"
            / f"{shot_name}_mm_{version}.3de"
        )
        scene_path.parent.mkdir(parents=True, exist_ok=True)

        # Write real 3DE content
        scene_path.write_text(f"# 3DE scene file for {shot_name}\n# Version: {version}")

        return scene_path

    return _make_3de_file


@pytest.fixture
def make_real_plate_files(
    tmp_path: Path,
) -> Callable[[str, str, str, str, str, int], list[Path]]:
    """Factory for creating real plate sequences.

    This follows UNIFIED_TESTING_GUIDE: test with real files.
    """

    def _make_plates(
        show: str = "test",
        seq: str = "seq01",
        shot: str = "0010",
        plate_type: str = "BG01",
        colorspace: str = "lin_sgamut3cine",
        frame_count: int = 10,
    ) -> list[Path]:
        shot_name = f"{seq}_{shot}"
        plate_path = (
            tmp_path
            / "shows"
            / show
            / "shots"
            / seq
            / shot_name
            / "plates"
            / "raw"
            / plate_type
            / colorspace
        )
        plate_path.mkdir(parents=True, exist_ok=True)

        # Create frame sequence
        frames = []
        for frame in range(1001, 1001 + frame_count):
            frame_file = plate_path / f"{shot_name}_{plate_type}.{frame:04d}.exr"
            # Write minimal EXR header
            frame_file.write_bytes(b"v/1\x01")  # Simplified EXR magic number
            frames.append(frame_file)

        return frames

    return _make_plates


# =============================================================================
# Common Test Double Factories (Reduce Duplication)
# =============================================================================


@pytest.fixture
def make_test_launcher() -> Callable[[str | None, str, str, str], CustomLauncher]:
    """Factory for creating CustomLauncher instances."""
    # Local application imports
    from launcher.models import CustomLauncher

    def _make_launcher(
        id: str | None = None,
        name: str = "Test Launcher",
        command: str = "echo {shot_name}",
        description: str = "Test launcher",
    ) -> CustomLauncher:
        launcher_id = id or f"test_launcher_{hash(name)}"
        return CustomLauncher(
            id=launcher_id,
            name=name,
            description=description,
            command=command,
            category="test",
        )

    return _make_launcher


@pytest.fixture
def make_thread_safe_image() -> Callable[[int, int, Any], ThreadSafeTestImage]:
    """Factory for creating thread-safe images.
    CRITICAL: Use this instead of QPixmap in worker threads!
    """
    # Local application imports
    from tests.test_doubles_library import ThreadSafeTestImage

    def _make_image(
        width: int = 100, height: int = 100, color: Any = None
    ) -> ThreadSafeTestImage:
        image = ThreadSafeTestImage(width, height)
        if color:
            image.fill(color)
        return image

    return _make_image


@pytest.fixture
def workspace_command_outputs() -> dict[str, str]:
    """Common workspace command outputs for testing."""
    return {
        "single_shot": "workspace /shows/test/shots/seq01/seq01_0010",
        "multiple_shots": (
            "workspace /shows/test/shots/seq01/seq01_0010\n"
            "workspace /shows/test/shots/seq01/seq01_0020\n"
            "workspace /shows/test/shots/seq02/seq02_0010"
        ),
        "empty": "",
        "invalid": "invalid output without workspace prefix",
        "mixed": (
            "workspace /shows/test/shots/seq01/seq01_0010\n"
            "some random line\n"
            "workspace /shows/test/shots/seq01/seq01_0020"
        ),
    }


@pytest.fixture
def common_test_paths() -> dict[str, str]:
    """Common test paths used across multiple tests."""
    return {
        "shot_path": "/shows/TEST/shots/seq01/seq01_0010",
        "thumbnail_path": "/shows/TEST/shots/seq01/seq01_0010/publish/editorial/cutref/v001/jpg/1920x1080/frame.1001.jpg",
        "3de_path": "/shows/TEST/shots/seq01/seq01_0010/user/testuser/3de/mm-default/seq01_0010_mm_v001.3de",
        "plate_path": "/shows/TEST/shots/seq01/seq01_0010/plates/raw/BG01/lin_sgamut3cine/seq01_0010_BG01.1001.exr",
    }


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory for testing."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def mock_filesystem(tmp_path: Path) -> Path:
    """Create a mock filesystem structure for testing."""
    # Create show structure
    show_path = tmp_path / "testshow" / "shots" / "101_ABC" / "101_ABC_0010"
    show_path.mkdir(parents=True)

    # Create thumbnail path following THUMBNAIL_SEGMENTS config
    # ["publish", "editorial", "cutref", "v001", "jpg", "1920x1080"]
    thumb_path = (
        show_path / "publish" / "editorial" / "cutref" / "v001" / "jpg" / "1920x1080"
    )
    thumb_path.mkdir(parents=True)

    # Create mock thumbnail files in the correct directory
    (thumb_path / "frame.1001.jpg").touch()
    (thumb_path / "frame.1002.jpg").touch()

    # Create 3DE file
    threede_path = show_path / "matchmove"
    threede_path.mkdir(parents=True)
    (threede_path / "101_ABC_0010_v001.3de").touch()

    # Create raw plate path
    plate_path = show_path / "plates" / "raw" / "BG01"
    plate_path.mkdir(parents=True)
    (plate_path / "frame.1001.exr").touch()

    return tmp_path


@pytest.fixture
def cache_manager(temp_cache_dir: Path) -> Generator[CacheManager, None, None]:
    """Create a CacheManager instance with temporary storage."""
    # Local application imports
    from cache_manager import CacheManager

    # Create instance with isolated cache directory
    instance = CacheManager(cache_dir=temp_cache_dir)

    yield instance

    # Explicit cleanup to prevent state pollution
    try:
        instance.clear_cache()
        instance.shutdown()
    except Exception:
        pass  # Ignore cleanup errors


@pytest.fixture
def sample_shot() -> Shot:
    """Create a sample Shot instance for testing."""
    # Local application imports
    from shot_model import Shot

    return Shot(
        show="testshow",
        sequence="101_ABC",
        shot="0010",
        workspace_path="/shows/testshow/shots/101_ABC/101_ABC_0010",
    )


@pytest.fixture
def shot_model(cache_manager: CacheManager) -> Any:
    """Create a ShotModel instance for testing."""
    # Local application imports
    from shot_model import ShotModel

    return ShotModel(cache_manager=cache_manager, load_cache=False)


@pytest.fixture
def shot_model_with_shots(cache_manager: CacheManager) -> Any:
    """Create a ShotModel with pre-populated shots."""
    # Local application imports
    from shot_model import Shot, ShotModel

    model = ShotModel(cache_manager=cache_manager, load_cache=False)

    # Add test shots to the shots list
    test_shots = [
        Shot("show1", "seq1", "0010", "/shows/show1/shots/seq1/seq1_0010"),
        Shot("show1", "seq1", "0020", "/shows/show1/shots/seq1/seq1_0020"),
        Shot("show2", "seq2", "0030", "/shows/show2/shots/seq2/seq2_0030"),
    ]

    model.shots = test_shots

    return model


@pytest.fixture
def test_process_pool_with_data() -> Generator[TestProcessPool, None, None]:
    """TestProcessPool with common test data (UNIFIED_TESTING_GUIDE)."""
    pool = TestProcessPool()
    pool.set_outputs(
        "workspace /shows/show1/shots/seq1/seq1_0010",
        "workspace /shows/show1/shots/seq1/seq1_0020",
        "workspace /shows/show2/shots/seq2/seq2_0030",
    )
    yield pool
    pool.reset()


@pytest.fixture
def test_image_file(tmp_path: Path) -> Path:
    """Create a test image file for caching tests."""
    image_file = tmp_path / "test_image.jpg"

    # Create a valid image using PIL if available, else use Qt
    try:
        # Third-party imports
        from PIL import Image

        # Create a simple 100x100 red image
        img = Image.new("RGB", (100, 100), color="red")
        img.save(str(image_file), format="JPEG")
    except ImportError:
        # Fall back to Qt if PIL not available
        # Third-party imports
        from PySide6.QtGui import QColor, QImage

        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 0, 0))  # Red
        img.save(str(image_file), "JPEG")  # type: ignore[reportCallIssue,reportArgumentType]

    return image_file  # Return Path object, not string


# =============================================================================
# Performance Testing Fixtures
# =============================================================================


@pytest.fixture
def benchmark_timer() -> type[Any]:
    """Simple timer for performance benchmarking."""
    # Standard library imports
    import time

    class BenchmarkTimer:
        def __init__(self) -> None:
            self.start_time: float | None = None
            self.end_time: float | None = None
            self.elapsed: float | None = None

        def __enter__(self) -> BenchmarkTimer:
            self.start_time = time.perf_counter()
            return self

        def __exit__(self, *args: Any) -> None:
            self.end_time = time.perf_counter()
            if self.start_time is not None:
                self.elapsed = (self.end_time - self.start_time) * 1000  # Convert to ms

        def assert_under(self, threshold_ms: float) -> None:
            """Assert that elapsed time is under threshold."""
            assert self.elapsed is not None, "Timer was not used properly"
            assert self.elapsed < threshold_ms, (
                f"Operation took {self.elapsed:.2f}ms, "
                f"exceeding threshold of {threshold_ms}ms"
            )

    return BenchmarkTimer


@pytest.fixture
def memory_tracker() -> type[Any]:
    """Track memory usage for performance tests."""
    # Standard library imports
    import os

    # Third-party imports
    import psutil

    class MemoryTracker:
        def __init__(self) -> None:
            self.process = psutil.Process(os.getpid())
            self.start_memory: int | None = None
            self.end_memory: int | None = None
            self.delta: int | None = None

        def __enter__(self) -> MemoryTracker:
            gc.collect()
            self.start_memory = self.process.memory_info().rss
            return self

        def __exit__(self, *args: Any) -> None:
            gc.collect()
            self.end_memory = self.process.memory_info().rss
            if self.start_memory is not None and self.end_memory is not None:
                self.delta = self.end_memory - self.start_memory

        def assert_under_mb(self, threshold_mb: float) -> None:
            """Assert memory increase is under threshold."""
            assert self.delta is not None, "Memory tracker was not used properly"
            delta_mb = self.delta / (1024 * 1024)
            assert delta_mb < threshold_mb, (
                f"Memory increased by {delta_mb:.2f}MB, "
                f"exceeding threshold of {threshold_mb}MB"
            )

    return MemoryTracker


# =============================================================================
# Thread Safety Testing Fixtures
# =============================================================================


@pytest.fixture
def concurrent_executor() -> Callable[
    [Callable[..., Any], list[tuple[Any, ...]], int], list[Any]
]:
    """Execute functions concurrently for thread safety testing."""
    # Standard library imports
    import concurrent.futures

    def _execute_concurrent(
        func: Callable[..., Any],
        args_list: list[tuple[Any, ...]],
        max_workers: int = 10,
    ) -> list[Any]:
        """Execute function with different args concurrently.

        Args:
            func: Function to execute
            args_list: List of argument tuples
            max_workers: Maximum concurrent workers

        Returns:
            List of results in order
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(func, *args) for args in args_list]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        return results

    return _execute_concurrent


@pytest.fixture
def thread_safety_monitor() -> Any:
    """Monitor for detecting thread safety violations."""
    # Standard library imports
    import threading

    class ThreadSafetyMonitor:
        def __init__(self) -> None:
            self.lock = threading.Lock()
            self.violations: list[str] = []
            self.operations: list[tuple[str, int | None, float]] = []

        def record_operation(self, op_name: str, thread_id: int | None = None) -> None:
            """Record an operation for analysis."""
            if thread_id is None:
                thread_id = threading.current_thread().ident

            with self.lock:
                self.operations.append((op_name, thread_id, time.time()))

        def record_violation(self, message: str) -> None:
            """Record a thread safety violation."""
            with self.lock:
                self.violations.append(message)

        def assert_no_violations(self) -> None:
            """Assert no violations were recorded."""
            assert not self.violations, (
                f"Thread safety violations detected: {self.violations}"
            )

        def get_concurrent_operations(self) -> list[tuple[str, str]]:
            """Get operations that happened concurrently."""
            concurrent: list[tuple[str, str]] = []
            for i, (op1, tid1, time1) in enumerate(self.operations):
                for op2, tid2, time2 in self.operations[i + 1 :]:
                    if tid1 != tid2 and abs(time1 - time2) < 0.001:  # Within 1ms
                        concurrent.append((op1, op2))
            return concurrent

    return ThreadSafetyMonitor()


# =============================================================================
# Autouse Fixtures for Test Safety
# =============================================================================


@pytest.fixture(autouse=True)
def ensure_clean_state_before_test(request: Any) -> Generator[None, None, None]:
    """Ensure clean state BEFORE each test to prevent crashes.

    This fixture runs BEFORE each test to clean up any leftover state
    from previous tests that could cause crashes.

    OPTIMIZATION: Only does ProcessPool cleanup for tests that need it.
    """
    # Only check for ProcessPoolManager if test might use it
    # Most tests don't need this expensive cleanup
    test_file = str(request.fspath)
    needs_process_pool_cleanup = (
        "process_pool" in test_file.lower()
        or "shot_model" in test_file.lower()
        or "main_window" in test_file.lower()
    )

    if needs_process_pool_cleanup:
        # Clean up ProcessPoolManager singleton BEFORE test starts
        try:
            # Standard library imports
            import sys

            # Local application imports
            from process_pool_manager import ProcessPoolManager

            # Check if singleton was created by a previous test
            if (
                hasattr(ProcessPoolManager, "_instance")
                and ProcessPoolManager._instance is not None
            ):
                try:
                    # Shutdown the executor to clean up threads with very short timeout
                    ProcessPoolManager._instance.shutdown(timeout=0.1)
                except Exception:
                    pass  # Ignore shutdown errors
                # Reset the singleton so test gets a fresh instance
                ProcessPoolManager._instance = None
        except ImportError:
            pass  # Module might not be imported yet
        except Exception:
            pass  # Ignore cleanup errors

    # Now let the test run
    return

    # No cleanup here - that's handled by cleanup_qt_resources


@pytest.fixture(autouse=True)
def cleanup_qt_resources(request: Any) -> Generator[None, None, None]:
    """Clean up Qt resources after each test to prevent resource exhaustion.

    This fixture runs after each test to:
    1. Delete all top-level widgets to prevent accumulation
    2. Process pending Qt events to ensure cleanup
    3. Clear virtually visible widgets tracking
    4. Run garbage collection to free memory
    5. Clean up any lingering QTimers and connections

    OPTIMIZATION: Only runs for Qt tests (tests using qapp/qtbot fixtures).
    Non-Qt tests skip this expensive cleanup for better parallel performance.

    This prevents:
    - Fatal Python errors from Qt resource corruption
    - Timeouts when creating QImage/QPixmap objects
    - Memory leaks from accumulated widgets
    - State corruption between tests
    """
    # Let test run first
    yield

    # OPTIMIZATION: Only do Qt cleanup if test actually used Qt
    # Check if test used qapp or qtbot fixtures
    uses_qt = any(
        fixture_name in request.fixturenames
        for fixture_name in ["qapp", "qtbot", "qt_app"]
    )

    if not uses_qt:
        # Non-Qt test - skip expensive Qt cleanup
        return

    # After test completes, clean up Qt resources
    try:
        # Third-party imports
        from PySide6.QtCore import QCoreApplication, QObject, Qt, QThread, QTimer
        from PySide6.QtWidgets import QApplication

        app = QCoreApplication.instance()
        if app and isinstance(app, QApplication):
            # First close all windows and dialogs
            for widget in list(app.topLevelWidgets()):
                try:
                    # Force close without saving
                    widget.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
                    widget.close()
                    widget.deleteLater()
                    # Disconnect all signals to prevent crashes
                    with contextlib.suppress(RuntimeError, TypeError):
                        widget.disconnect()
                except (RuntimeError, AttributeError):
                    # Widget already deleted or no signals
                    pass

            # Stop all timers
            for child in app.findChildren(QTimer):
                try:
                    child.stop()
                    child.deleteLater()
                except RuntimeError:
                    pass

            # Clean up any QThreads (CRITICAL for preventing crashes)
            for thread in app.findChildren(QThread):
                try:
                    if thread.isRunning():
                        thread.quit()
                        if not thread.wait(100):  # Wait up to 0.1 second
                            thread.terminate()  # Force terminate if still running
                            thread.wait(50)
                    thread.deleteLater()
                except RuntimeError:
                    pass

            # Wait for QThreadPool to complete all tasks (only if app exists)
            # Use shorter timeout in test environments to prevent cleanup accumulation
            try:
                if app:  # Only access QThreadPool if app exists
                    pool = QThreadPool.globalInstance()
                    if pool.activeThreadCount() > 0:
                        pool.waitForDone(100)  # Reduced to 100ms for fast test cleanup
            except RuntimeError:
                pass

            # Process events minimal times to speed up cleanup
            # In tests, we only need basic event processing
            for _ in range(2):  # Reduced to 2 iterations for speed
                app.processEvents()
                app.sendPostedEvents(None, 0)  # Process all events

            # Clean up any remaining QObjects
            for obj in app.findChildren(QObject):
                try:
                    if hasattr(obj, "deleteLater"):
                        obj.deleteLater()
                except RuntimeError:
                    pass

            # Final event processing
            app.processEvents()

        # Clear the virtually visible widgets set
        global _virtually_visible_widgets
        _virtually_visible_widgets.clear()

        # Force garbage collection multiple times
        for _ in range(3):
            gc.collect()

    except Exception as e:
        # Don't let cleanup errors fail tests, but log for debugging
        # Standard library imports
        import sys

        print(f"Warning: Qt cleanup error: {e}", file=sys.stderr)


@pytest.fixture(autouse=True)
def enhanced_mainwindow_cleanup(request: Any) -> Generator[None, None, None]:
    """Enhanced MainWindow and cache cleanup for test isolation.

    This fixture provides additional cleanup specifically for MainWindow
    instances and cache managers to prevent resource accumulation crashes.

    OPTIMIZATION: Only runs for Qt tests to avoid overhead on non-Qt tests.
    """
    # Let test run first
    yield

    # OPTIMIZATION: Only run if test used Qt
    uses_qt = any(
        fixture_name in request.fixturenames
        for fixture_name in ["qapp", "qtbot", "qt_app"]
    )

    if not uses_qt:
        return

    # Enhanced cleanup after test
    try:
        # Third-party imports
        from PySide6.QtCore import QCoreApplication

        app = QCoreApplication.instance()
        if app:
            # Find and cleanup any MainWindow instances
            try:
                # Local application imports
                from main_window import MainWindow

                for widget in app.topLevelWidgets():
                    if isinstance(widget, MainWindow):
                        try:
                            # Call our new explicit cleanup method
                            widget.cleanup()
                            # Ensure it's marked for deletion
                            widget.deleteLater()
                        except Exception as e:
                            # Standard library imports
                            import sys

                            print(
                                f"Warning: MainWindow cleanup error: {e}",
                                file=sys.stderr,
                            )
            except ImportError:
                pass  # MainWindow not imported in this test

            # Clean up any CacheManager instances
            try:
                # Force cache cleanup to prevent memory leaks
                # Local application imports
                from cache_manager import CacheManager

                # The CacheManager might be a singleton or instance
                # Try to clean up any static/global references
                if hasattr(CacheManager, "_instance"):
                    instance = CacheManager._instance
                    if instance:
                        with contextlib.suppress(Exception):
                            instance.shutdown()
                        CacheManager._instance = None
            except ImportError:
                pass

            # Additional QPixmap cleanup - force cleanup of Qt image cache
            try:
                # Third-party imports
                from PySide6.QtGui import QPixmapCache

                QPixmapCache.clear()
            except ImportError:
                pass

            # Process events briefly after MainWindow cleanup
            for _ in range(2):
                app.processEvents()

        # Force additional garbage collection after MainWindow cleanup
        # Standard library imports
        import gc

        gc.collect()
        gc.collect()  # Second pass to clean up circular references

    except Exception as e:
        # Standard library imports
        import sys

        print(f"Warning: Enhanced MainWindow cleanup error: {e}", file=sys.stderr)


@pytest.fixture(autouse=True)
def mock_gui_blocking_components(monkeypatch: Any) -> TestProcessPool:
    """Automatically mock GUI components that can hang tests.

    This autouse fixture runs before every test to ensure:
    1. QMessageBox never shows blocking dialogs that hang pytest
    2. ProcessPoolManager uses TestProcessPool instead of real subprocesses
    3. MainWindow can be safely created without triggering background threads that call GUI components
    4. NotificationManager calls don't block from worker threads
    5. PersistentTerminalManager FIFO operations don't block tests

    This fixes the MainWindow test hang issue where:
    - MainWindow creates ShotModel
    - ShotModel starts AsyncShotLoader threads
    - AsyncShotLoader threads may call NotificationManager.error()
    - NotificationManager.error() calls QMessageBox.critical() from worker thread
    - QMessageBox from non-main thread causes Qt to hang/crash

    Also fixes persistent terminal hangs where:
    - MainWindow creates PersistentTerminalManager when Config.USE_PERSISTENT_TERMINAL=True
    - PersistentTerminalManager creates FIFO operations that can block in test environment
    - Tests hang waiting for FIFO read/write operations to complete
    """
    # QMessageBox is already patched at module level, no need to patch again

    # Mock ProcessPoolManager.get_instance() to return TestProcessPool
    # This prevents real subprocess execution that could trigger errors -> NotificationManager -> QMessageBox
    # Local application imports
    from tests.test_doubles_library import TestProcessPool

    test_pool = TestProcessPool()
    # Set default successful output to prevent load_failed signals
    test_pool.set_outputs("workspace /shows/test/shots/seq01/seq01_0010")

    # Mock the singleton getter to return our test pool
    monkeypatch.setattr(
        "process_pool_manager.ProcessPoolManager.get_instance", lambda: test_pool
    )

    # Also patch it at the module level for direct imports

    # Create MockProcessPoolManager with required class attributes
    # Third-party imports
    from PySide6.QtCore import QMutex

    # Local application imports
    import process_pool_manager

    MockProcessPoolManagerClass = type(
        "MockProcessPoolManager",
        (),
        {
            "get_instance": staticmethod(lambda: test_pool),
            "_lock": QMutex(),  # Required class attribute for singleton pattern - must be QMutex for QMutexLocker
            "_instance": None,  # Required for singleton pattern
            "_initialized": False,  # Required for initialization check
        },
    )

    monkeypatch.setattr(
        process_pool_manager, "ProcessPoolManager", MockProcessPoolManagerClass
    )

    # CRITICAL FIX: Disable persistent terminal to prevent FIFO hangs
    # This prevents MainWindow from creating PersistentTerminalManager that uses FIFO operations
    # Local application imports
    from config import Config

    monkeypatch.setattr(Config, "USE_PERSISTENT_TERMINAL", False)

    # Also mock PersistentTerminalManager to be extra safe
    class MockPersistentTerminalManager:
        """Mock PersistentTerminalManager that does nothing."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def send_command(self, command: str, ensure_terminal: bool = True) -> bool:
            return True  # Always succeed without doing anything

        def clear_terminal(self) -> bool:
            return True

        def close_terminal(self) -> bool:
            return True

        def restart_terminal(self) -> bool:
            return True

        def cleanup(self) -> None:
            pass

        def cleanup_fifo_only(self) -> None:
            pass

    # Mock the PersistentTerminalManager import in modules that use it
    monkeypatch.setattr(
        "persistent_terminal_manager.PersistentTerminalManager",
        MockPersistentTerminalManager,
    )

    # Store reference for tests that need to access it
    return test_pool


# =============================================================================
# Controller Test Targets (Single Source of Truth Testing)
# =============================================================================


@pytest.fixture
def launcher_controller_target(qtbot: Any) -> Any:
    """Create a minimal target for LauncherController testing.

    This fixture provides the minimum interface required by LauncherController
    following the LauncherTarget protocol.
    """
    from unittest.mock import Mock

    from PySide6.QtCore import QObject, Signal

    class TestCommandLauncher(QObject):
        """Minimal command launcher for testing."""

        __test__ = False

        command_executed = Signal(str, str)
        command_error = Signal(str, str)

        def __init__(self) -> None:
            super().__init__()
            self.current_shot: Any = None

        def set_current_shot(self, shot: Any) -> None:
            self.current_shot = shot

        def launch_app(self, *args: Any, **kwargs: Any) -> bool:
            return True

    class LauncherControllerTestTarget:
        """Minimal target implementing LauncherTarget protocol."""

        def __init__(self) -> None:
            self.command_launcher = TestCommandLauncher()
            self.launcher_manager: Any = None
            self.launcher_panel = Mock()
            self.log_viewer = Mock()
            self.status_bar = Mock()
            self.custom_launcher_menu = Mock()

        def update_status(self, message: str) -> None:
            pass

    target = LauncherControllerTestTarget()
    # Note: command_launcher is QObject (not QWidget), no need to register with qtbot
    return target


@pytest.fixture
def threede_controller_target(qtbot: Any, launcher_controller_target: Any) -> Any:
    """Create a minimal target for ThreeDEController testing.

    This fixture provides the minimum interface required by ThreeDEController
    following the ThreeDETarget protocol, with LauncherController integration.
    """
    from unittest.mock import Mock

    from controllers.launcher_controller import LauncherController

    class ThreeDEControllerTestTarget:
        """Minimal target implementing ThreeDETarget protocol."""

        def __init__(self, launcher_target: Any) -> None:
            # Create actual launcher controller for integration testing
            self.launcher_controller = LauncherController(launcher_target)

            # Mock other required components
            self.threede_shot_grid = Mock()
            self.shot_info_panel = Mock()
            self.launcher_panel = Mock()
            self.status_bar = Mock()
            self.shot_model = Mock()
            self.threede_scene_model = Mock()
            self.threede_item_model = Mock()
            self.cache_manager = Mock()
            self.command_launcher = launcher_target.command_launcher
            self.closing = False

        def setWindowTitle(self, title: str) -> None:
            pass

        def update_status(self, message: str) -> None:
            pass

        def update_launcher_menu_availability(self, available: bool) -> None:
            pass

        def enable_custom_launcher_buttons(self, enabled: bool) -> None:
            pass

        def launch_app(self, app_name: str) -> None:
            pass

    target = ThreeDEControllerTestTarget(launcher_controller_target)
    return target


# =============================================================================
# pytest-xdist Configuration for Concurrent Test Execution
# =============================================================================


# Note: qapp fixture scope is dynamically determined by pytest-qt
# We enhance it here with xdist-specific cleanup only
@pytest.fixture
def qapp(qapp: Any, request: Any) -> Generator[Any, None, None]:
    """Enhance qapp fixture with xdist worker-specific cleanup.

    When running tests in parallel with pytest-xdist, we need extra cleanup
    after each test to prevent Qt state leakage between tests in the same worker.

    Reference: pytest-qt documentation on parallel execution
    """
    try:
        # Import xdist utility - may not be available in all environments
        from xdist import is_xdist_worker

        in_worker = is_xdist_worker(request)
    except (ImportError, TypeError):
        in_worker = False

    yield qapp

    # Extra cleanup in xdist workers to prevent state leakage
    if in_worker:
        qapp.processEvents()
        QTimer.singleShot(0, lambda: None)  # Flush pending events
        qapp.processEvents()


def pytest_collection_modifyitems(items: list[Any]) -> None:
    """Configure test execution for parallel runs with pytest-xdist.

    This hook ensures that tests which create MainWindow instances run in a
    single worker to avoid Qt threading crashes and resource conflicts.

    The gui_mainwindow marker groups these tests together so they execute
    serially within one worker process while other tests run in parallel.
    """
    # Disabled automatic marker addition - we manage xdist_group explicitly in test files
    # This prevents conflicts between different group names (qt_state vs gui_mainwindow)
    # for item in items:
    #     # Mark all MainWindow tests to run in same xdist group
    #     if "gui_mainwindow" in item.keywords:
    #         item.add_marker(pytest.mark.xdist_group("gui_mainwindow"))
    #
    #     # Also group tests that use real QApplication fixtures
    #     if any(
    #         fixture in item.fixturenames
    #         for fixture in ["qapp", "qtbot", "qt_signal_blocker"]
    #     ):
    #         # If it's an integration test with MainWindow, use gui_mainwindow group
    #         if "integration" in str(item.fspath) and "MainWindow" in item.name:
    #             item.add_marker(pytest.mark.xdist_group("gui_mainwindow"))
