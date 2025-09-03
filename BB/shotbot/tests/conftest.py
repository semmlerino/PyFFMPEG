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

import gc
import os
import sys
import time
from pathlib import Path
from typing import Any, Generator

import pytest
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication

# Import protocols for type safety

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import test doubles library for proper test double patterns
from tests.test_doubles_library import TestProcessPool

# =============================================================================
# Factory Fixtures (UNIFIED_TESTING_GUIDE Best Practice)
# =============================================================================


@pytest.fixture
def make_shot():
    """Factory fixture for creating Shot instances with customizable parameters.

    Following UNIFIED_TESTING_GUIDE pattern from lines 27-37.
    Creates Shot instances with flexible, test-specific parameters.
    """
    from shot_model import Shot

    def _make_shot(show="test", seq="seq1", shot="0010", workspace_path=None):
        if workspace_path is None:
            workspace_path = f"/shows/{show}/{seq}/{seq}_{shot}"
        return Shot(show, seq, shot, workspace_path)

    return _make_shot


@pytest.fixture
def make_launcher():
    """Factory fixture for creating CustomLauncher instances.

    Following UNIFIED_TESTING_GUIDE factory pattern.
    Creates CustomLauncher instances with flexible parameters for testing.
    """
    from launcher.models import CustomLauncher

    created_launchers = []

    def _make_launcher(
        id=None,
        name="Test Launcher",
        command="echo {shot_name}",
        description="Test launcher for unit tests",
        category="test",
    ):
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
def make_cache_manager():
    """Factory fixture for creating CacheManager instances with tmp_path.

    Following UNIFIED_TESTING_GUIDE factory pattern.
    Creates isolated CacheManager instances with temporary directories.
    """
    from cache_manager import CacheManager

    created_managers = []

    def _make_cache_manager(tmp_path, cache_subdir="cache"):
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
def make_process_pool():
    """Factory fixture for creating TestProcessPoolManager instances.

    Following UNIFIED_TESTING_GUIDE factory pattern.
    Creates test doubles for process pool boundary mocking.
    """
    from tests.test_doubles_library import TestProcessPool

    created_pools = []

    def _make_process_pool(default_output="workspace /test/path"):
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
def make_test_widget(qtbot):
    """Factory for creating test Qt widgets with proper cleanup.
    Following UNIFIED_TESTING_GUIDE pattern for Qt testing.
    """
    from PySide6.QtWidgets import QWidget

    created_widgets = []

    def _make_widget(widget_class=QWidget, **kwargs):
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
def make_test_worker():
    """Factory for creating thread-safe test workers.
    CRITICAL: Uses ThreadSafeTestImage, not QPixmap!
    """
    from tests.test_doubles_extended import TestWorker

    created_workers = []

    def _make_worker(name="test_worker"):
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
def make_test_cache(tmp_path):
    """Factory for creating test cache instances.
    Each cache gets its own temporary directory.
    """
    created_caches = []

    def _make_cache(name="cache"):
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
def make_test_command():
    """Factory for creating test command executors.
    Tracks executed commands and provides controlled outputs.
    """

    def _make_command(default_output="success"):
        from tests.test_doubles_extended import TestCommand

        executor = TestCommand()
        executor.default_output = default_output
        return executor

    return _make_command


@pytest.fixture
def make_test_filesystem(tmp_path):
    """Factory for creating VFX directory structures.
    Creates realistic /shows/{show}/shots/{seq}/{seq}_{shot} paths.
    """

    def _make_filesystem():
        from tests.test_doubles_extended import TestFileSystem

        fs = TestFileSystem(tmp_path)
        return fs

    return _make_filesystem


@pytest.fixture
def workspace_outputs():
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

    # Set Qt environment for offscreen testing
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_LOGGING_RULES"] = "*.debug=false"
    os.environ["PYTEST_QT_API"] = "pyside6"


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
        from utils import clear_all_caches, disable_caching

        clear_all_caches()
        disable_caching()
    except ImportError:
        pass

    # Clear any Qt-related caches or shared objects
    try:
        # Process any pending Qt events to ensure cleanup
        from PySide6.QtCore import QCoreApplication

        app = QCoreApplication.instance()
        if app:
            app.processEvents()
    except ImportError:
        pass

    # Force garbage collection to ensure clean state
    gc.collect()

    yield

    # Clear utils caches and re-enable caching after test
    try:
        from utils import clear_all_caches, enable_caching

        clear_all_caches()
        enable_caching()
    except ImportError:
        pass

    # Process Qt events after test cleanup
    try:
        from PySide6.QtCore import QCoreApplication

        app = QCoreApplication.instance()
        if app:
            app.processEvents()
    except ImportError:
        pass

    # Final garbage collection to prevent memory leaks
    gc.collect()


# =============================================================================
# Cache Testing Fixtures
# =============================================================================


@pytest.fixture
def cache_isolation():
    """Provide cache isolation context manager for tests that need explicit control.

    Use this fixture when a test needs to explicitly control cache isolation,
    for example when testing cache behavior itself.
    """
    try:
        from utils import CacheIsolation

        return CacheIsolation
    except ImportError:
        # Fallback no-op context manager
        from contextlib import contextmanager

        @contextmanager
        def no_op():
            yield

        return no_op


# =============================================================================
# Qt Application Fixtures for Threading Tests
# =============================================================================


@pytest.fixture(scope="function")
def qapp():
    """Create QApplication instance for the entire test session.

    This ensures proper Qt event loop for signal processing.
    """
    app = QCoreApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Don't quit here - let pytest-qt handle cleanup


@pytest.fixture
def qt_signal_blocker():
    """Helper fixture for blocking until Qt signals are processed.

    Use this when you need to ensure signals are delivered in tests.
    """

    def _process_events(timeout_ms=1000):
        """Process Qt events for specified timeout."""
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: None)  # Dummy slot
        timer.start(timeout_ms)

        # Process events until timer expires
        while timer.isActive():
            QCoreApplication.processEvents()

        return True

    return _process_events


# =============================================================================
# Test Doubles Fixtures (Following UNIFIED_TESTING_GUIDE)
# =============================================================================


@pytest.fixture
def test_signal():
    """Create a SignalDouble instance for non-Qt signal testing."""
    from tests.test_doubles_library import SignalDouble

    return SignalDouble()


@pytest.fixture
def test_process_pool():
    """Create a TestProcessPool for subprocess boundary mocking."""
    from tests.test_doubles_library import TestProcessPool

    pool = TestProcessPool()
    yield pool
    pool.reset()  # Clean up after test


@pytest.fixture
def test_filesystem():
    """Create a TestFileSystem for in-memory file operations."""
    from tests.unit.test_doubles import TestFileSystem

    fs = TestFileSystem()
    yield fs
    fs.clear()  # Clean up after test


@pytest.fixture
def test_cache():
    """Create a TestCache for in-memory caching."""
    from tests.unit.test_doubles import TestCache

    cache = TestCache()
    yield cache
    cache.clear()  # Clean up after test


# =============================================================================
# Real Component Fixtures (Following UNIFIED_TESTING_GUIDE)
# =============================================================================


@pytest.fixture
def real_cache_manager(tmp_path):
    """Create a real CacheManager with temporary storage.

    This follows UNIFIED_TESTING_GUIDE: use real components with test boundaries.
    """
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
def real_shot_model(real_cache_manager, test_process_pool):
    """Create a real ShotModel with test doubles only at boundaries.

    This follows UNIFIED_TESTING_GUIDE: real components with boundary mocks.
    """
    from shot_model import ShotModel

    model = ShotModel(cache_manager=real_cache_manager, load_cache=False)
    # Only mock the subprocess boundary
    model._process_pool = test_process_pool  # type: ignore[attr-defined]

    return model


@pytest.fixture
def make_test_shot(tmp_path):
    """Factory for creating real Shot objects with actual files.

    This follows UNIFIED_TESTING_GUIDE: test with real files, not mocks.
    """
    from shot_model import Shot

    def _make_shot(show="test", seq="seq01", shot="0010", with_thumbnail=True):
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
def make_real_3de_file(tmp_path):
    """Factory for creating real 3DE scene files.

    This follows UNIFIED_TESTING_GUIDE: test with real files.
    """

    def _make_3de_file(
        show="test", seq="seq01", shot="0010", user="testuser", version="v001"
    ):
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
def make_real_plate_files(tmp_path):
    """Factory for creating real plate sequences.

    This follows UNIFIED_TESTING_GUIDE: test with real files.
    """

    def _make_plates(
        show="test",
        seq="seq01",
        shot="0010",
        plate_type="BG01",
        colorspace="lin_sgamut3cine",
        frame_count=10,
    ):
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
def make_test_launcher():
    """Factory for creating CustomLauncher instances."""
    from launcher.models import CustomLauncher

    def _make_launcher(
        id=None,
        name="Test Launcher",
        command="echo {shot_name}",
        description="Test launcher",
    ):
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
def make_thread_safe_image():
    """Factory for creating thread-safe images.
    CRITICAL: Use this instead of QPixmap in worker threads!
    """
    from tests.test_doubles_library import ThreadSafeTestImage

    def _make_image(width=100, height=100, color=None):
        image = ThreadSafeTestImage(width, height)
        if color:
            image.fill(color)
        return image

    return _make_image


@pytest.fixture
def workspace_command_outputs():
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
def common_test_paths():
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
def mock_filesystem(tmp_path):
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
def cache_manager(temp_cache_dir):
    """Create a CacheManager instance with temporary storage."""
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
def sample_shot():
    """Create a sample Shot instance for testing."""
    from shot_model import Shot

    return Shot(
        show="testshow",
        sequence="101_ABC",
        shot="0010",
        workspace_path="/shows/testshow/shots/101_ABC/101_ABC_0010",
    )


@pytest.fixture
def shot_model(cache_manager):
    """Create a ShotModel instance for testing."""
    from shot_model import ShotModel

    return ShotModel(cache_manager=cache_manager, load_cache=False)


@pytest.fixture
def shot_model_with_shots(cache_manager):
    """Create a ShotModel with pre-populated shots."""
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
def test_process_pool_with_data():
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
def test_image_file(tmp_path):
    """Create a test image file for caching tests."""
    image_file = tmp_path / "test_image.jpg"

    # Create a valid image using PIL if available, else use Qt
    try:
        from PIL import Image

        # Create a simple 100x100 red image
        img = Image.new("RGB", (100, 100), color="red")
        img.save(str(image_file), format="JPEG")
    except ImportError:
        # Fall back to Qt if PIL not available
        from PySide6.QtGui import QColor, QImage

        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 0, 0))  # Red
        img.save(str(image_file), "JPEG")  # type: ignore[reportCallIssue,reportArgumentType]

    return image_file  # Return Path object, not string


# =============================================================================
# Performance Testing Fixtures
# =============================================================================


@pytest.fixture
def benchmark_timer():
    """Simple timer for performance benchmarking."""
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
def memory_tracker():
    """Track memory usage for performance tests."""
    import os

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
def concurrent_executor():
    """Execute functions concurrently for thread safety testing."""
    import concurrent.futures

    def _execute_concurrent(func, args_list, max_workers=10):
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
def thread_safety_monitor():
    """Monitor for detecting thread safety violations."""
    import threading

    class ThreadSafetyMonitor:
        def __init__(self):
            self.lock = threading.Lock()
            self.violations = []
            self.operations = []

        def record_operation(self, op_name, thread_id=None):
            """Record an operation for analysis."""
            if thread_id is None:
                thread_id = threading.current_thread().ident

            with self.lock:
                self.operations.append((op_name, thread_id, time.time()))

        def record_violation(self, message):
            """Record a thread safety violation."""
            with self.lock:
                self.violations.append(message)

        def assert_no_violations(self):
            """Assert no violations were recorded."""
            assert not self.violations, (
                f"Thread safety violations detected: {self.violations}"
            )

        def get_concurrent_operations(self):
            """Get operations that happened concurrently."""
            concurrent = []
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
def mock_gui_blocking_components(monkeypatch):
    """Automatically mock GUI components that can hang tests.

    This autouse fixture runs before every test to ensure:
    1. QMessageBox never shows blocking dialogs that hang pytest
    2. ProcessPoolManager uses TestProcessPool instead of real subprocesses
    3. MainWindow can be safely created without triggering background threads that call GUI components
    4. NotificationManager calls don't block from worker threads
    5. PersistentTerminalManager FIFO operations don't block tests

    This fixes the MainWindow test hang issue where:
    - MainWindow creates OptimizedShotModel
    - OptimizedShotModel starts AsyncShotLoader threads
    - AsyncShotLoader threads may call NotificationManager.error()
    - NotificationManager.error() calls QMessageBox.critical() from worker thread
    - QMessageBox from non-main thread causes Qt to hang/crash

    Also fixes persistent terminal hangs where:
    - MainWindow creates PersistentTerminalManager when Config.USE_PERSISTENT_TERMINAL=True
    - PersistentTerminalManager creates FIFO operations that can block in test environment
    - Tests hang waiting for FIFO read/write operations to complete
    """
    # Mock QMessageBox methods to prevent blocking dialogs
    from PySide6.QtWidgets import QMessageBox

    # Return appropriate button values immediately without showing dialogs
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )

    # Mock ProcessPoolManager.get_instance() to return TestProcessPool
    # This prevents real subprocess execution that could trigger errors -> NotificationManager -> QMessageBox
    from tests.test_doubles_library import TestProcessPool

    test_pool = TestProcessPool()
    # Set default successful output to prevent load_failed signals
    test_pool.set_outputs("workspace /shows/test/shots/seq01/seq01_0010")

    # Mock the singleton getter to return our test pool
    monkeypatch.setattr(
        "process_pool_manager.ProcessPoolManager.get_instance", lambda: test_pool
    )

    # Also patch it at the module level for direct imports
    import threading

    import process_pool_manager

    # Create MockProcessPoolManager with required class attributes
    MockProcessPoolManagerClass = type(
        "MockProcessPoolManager",
        (),
        {
            "get_instance": staticmethod(lambda: test_pool),
            "_lock": threading.Lock(),  # Required class attribute for singleton pattern
        },
    )

    monkeypatch.setattr(
        process_pool_manager, "ProcessPoolManager", MockProcessPoolManagerClass
    )

    # CRITICAL FIX: Disable persistent terminal to prevent FIFO hangs
    # This prevents MainWindow from creating PersistentTerminalManager that uses FIFO operations
    from config import Config

    monkeypatch.setattr(Config, "USE_PERSISTENT_TERMINAL", False)

    # Also mock PersistentTerminalManager to be extra safe
    class MockPersistentTerminalManager:
        """Mock PersistentTerminalManager that does nothing."""

        def __init__(self, *args, **kwargs):
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
