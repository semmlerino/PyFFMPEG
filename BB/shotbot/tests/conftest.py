"""Shared fixtures for pytest tests following best practices.

This conftest provides clean, isolated fixtures for tests that need them.
Qt components are NOT mocked to allow real signal testing.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# Qt Application Fixtures for Threading Tests
# =============================================================================


@pytest.fixture(scope="session")
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
        QCoreApplication.instance().time if hasattr(
            QCoreApplication.instance(), "time"
        ) else 0
        while timer.isActive():
            QCoreApplication.processEvents()

        return True

    return _process_events


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_cache_dir(tmp_path):
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

    return CacheManager(cache_dir=temp_cache_dir)


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
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    )
    return image_file  # Return Path object, not string
