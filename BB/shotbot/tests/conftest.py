"""Shared fixtures for pytest tests following best practices.

This conftest provides clean, isolated fixtures for tests that need them.
Qt components are NOT mocked to allow real signal testing.
"""

# pyright: basic
"""Shared fixtures for pytest tests following best practices.

This conftest provides clean, isolated fixtures for tests that need them.
Qt components are NOT mocked to allow real signal testing.
"""

import gc
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication

# Import protocols for type safety
from tests.unit.test_protocols import TestConfigDir

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# Cache Isolation Fixtures
# =============================================================================


@pytest.fixture(autouse=False)  # Disabled for performance
def isolated_test_environment():
    """Ensure complete test isolation by clearing all caches and shared state.

    This fixture runs before and after every test to ensure:
    1. All utility caches are cleared
    2. CacheManager instances don't share state
    3. No global state persists between tests
    4. Qt objects are properly cleaned up
    5. Garbage collection removes any lingering objects
    6. Caching is disabled during tests to prevent contamination

    This fixes the critical test isolation issue where tests pass individually
    but fail in suites due to shared cache state.
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
    """Create a TestSignal instance for non-Qt signal testing."""
    from tests.unit.test_doubles import TestSignal

    return TestSignal()


@pytest.fixture
def test_process_pool():
    """Create a TestProcessPool for subprocess boundary mocking."""
    from tests.unit.test_doubles import TestProcessPool

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
    model._process_pool = test_process_pool

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
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> TestConfigDir:
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
def mock_process_pool_manager():
    """Mock ProcessPoolManager for subprocess isolation."""
    with patch("shot_model.ProcessPoolManager") as mock_pool_class:
        instance = Mock()
        instance.execute_workspace_command.return_value = """workspace /shows/show1/shots/seq1/seq1_0010
workspace /shows/show1/shots/seq1/seq1_0020
workspace /shows/show2/shots/seq2/seq2_0030"""

        mock_pool_class.get_instance.return_value = instance
        yield instance


@pytest.fixture
def test_image_file(tmp_path):
    """Create a test image file for caching tests."""
    image_file = tmp_path / "test_image.jpg"
    # Create a minimal JPEG file (just write some bytes)
    # This is a minimal valid JPEG header
    image_file.write_bytes(
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9",
    )
    return image_file  # Return Path object, not string
