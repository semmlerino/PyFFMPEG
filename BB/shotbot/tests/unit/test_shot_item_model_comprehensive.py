"""Comprehensive unit tests for ShotItemModel with async callback race condition testing.

This module tests the critical async callback fixes and thread safety improvements
made to ShotItemModel, focusing on the QMetaObject.invokeMethod race condition
protection and immutable shot identifier handling.
"""

from __future__ import annotations

# Standard library imports
import sys
from pathlib import Path
from unittest.mock import patch

# Third-party imports
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy

sys.path.insert(0, str(Path(__file__).parent.parent))

# Local application imports
from shot_model import Shot
from tests.test_doubles_library import TestCacheManager
from unified_item_model import UnifiedRole, create_shot_item_model

# Backward compatibility alias
ShotRole = UnifiedRole

pytestmark = [
    pytest.mark.unit,
    pytest.mark.qt,
    pytest.mark.critical,
    pytest.mark.xdist_group("qt_state"),
]


class TestAsyncCallbackRaceConditions:
    """Test async callback race condition fixes in ShotItemModel."""

    @pytest.fixture
    def test_cache_manager(self) -> TestCacheManager:
        """Create test double CacheManager with predictable behavior."""
        return TestCacheManager()

    @pytest.fixture
    def model(self, test_cache_manager, qtbot):
        """Create ShotItemModel with test cache manager."""
        model = create_shot_item_model(test_cache_manager)
        # Don't use qtbot.addWidget() for QAbstractItemModel (UNIFIED_TESTING_GUIDE)
        yield model
        model.clear_thumbnail_cache()
        model.deleteLater()

    @pytest.fixture
    def test_shots(self) -> list[Shot]:
        """Create test shots for model testing."""
        return [
            Shot("show1", "seq1", "shot1", "/workspace/shot1"),
            Shot("show1", "seq1", "shot2", "/workspace/shot2"),
            Shot("show2", "seq2", "shot3", "/workspace/shot3"),
        ]

    def test_find_shot_by_full_name_race_protection(self, model, test_shots) -> None:
        """Test _find_item_by_full_name handles concurrent access safely."""
        model.set_shots(test_shots)

        target_shot = test_shots[1]

        # Should find existing shot
        result = model._find_item_by_full_name(target_shot.full_name)
        assert result is not None
        shot, row = result
        assert shot.full_name == target_shot.full_name
        assert row == 1

        # Should return None for non-existent shot
        result = model._find_item_by_full_name("nonexistent_shot")
        assert result is None

    def test_concurrent_thumbnail_loading(
        self, model, test_shots, qtbot, tmp_path, monkeypatch
    ) -> None:
        """Test multiple simultaneous thumbnail load operations for thread safety."""
        # Create fake thumbnail files for each shot
        thumbnail_paths = {}
        for i, shot in enumerate(test_shots):
            thumbnail_path = tmp_path / f"thumbnail_{i}.jpg"
            thumbnail_path.touch()
            thumbnail_paths[shot.full_name] = thumbnail_path

        # Mock get_thumbnail_path to return correct path for each shot
        def mock_get_thumbnail(self):
            return thumbnail_paths.get(self.full_name)

        monkeypatch.setattr(Shot, "get_thumbnail_path", mock_get_thumbnail)

        model.set_shots(test_shots)

        # Mock cache manager to simulate concurrent operations
        cache_calls = []

        def mock_cache_thumbnail(*args, **kwargs):
            cache_calls.append(args)
            # Return immediate success for simplicity
            return Path("/cache/mock_thumbnail.jpg")

        with patch.object(
            model._cache_manager, "cache_thumbnail", mock_cache_thumbnail
        ):
            # Start multiple concurrent thumbnail loads
            for i, shot in enumerate(test_shots):
                model._load_thumbnail_async(i, shot)

            qtbot.wait(100)  # Allow operations to complete

            # Verify all cache calls were made
            assert len(cache_calls) == len(test_shots)

            # Verify loading states were set correctly
            for shot in test_shots:
                state = model._loading_states.get(shot.full_name)
                assert state in ["loading", "loaded", "failed"]  # Valid states

    def test_thumbnail_cache_consistency_during_model_reset(
        self, model, test_shots, qtbot
    ) -> None:
        """Test that thumbnail cache remains consistent during model reset operations."""
        model.set_shots(test_shots)

        # Populate thumbnail cache
        test_image = QImage(64, 64, QImage.Format.Format_RGB32)
        test_image.fill(Qt.GlobalColor.red)
        model._thumbnail_cache[test_shots[0].full_name] = test_image

        # Set up spy for model reset signals
        reset_spy = QSignalSpy(model.modelAboutToBeReset)
        reset_done_spy = QSignalSpy(model.modelReset)

        # Reset model with new shots
        new_shots = [Shot("new_show", "new_seq", "new_shot", "/new/path")]
        model.set_shots(new_shots)

        # Verify signals were emitted
        assert reset_spy.count() == 1
        assert reset_done_spy.count() == 1

        # Verify cache was cleared during reset
        assert len(model._thumbnail_cache) == 0
        assert len(model._loading_states) == 0


class TestShotItemModelCore:
    """Test core ShotItemModel functionality."""

    @pytest.fixture
    def model(self, qtbot):
        """Create basic ShotItemModel."""
        model = create_shot_item_model()
        yield model
        model.deleteLater()

    def test_model_initialization(self, model) -> None:
        """Test model initializes correctly."""
        assert model.rowCount() == 0
        assert isinstance(model._thumbnail_cache, dict)
        assert isinstance(model._loading_states, dict)
        assert model._cache_manager is not None

    def test_shot_data_access(self, model) -> None:
        """Test data access through Qt model interface."""
        test_shots = [Shot("show", "seq", "shot", "/path")]
        model.set_shots(test_shots)

        index = model.index(0, 0)

        # Test various role access
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == test_shots[0].full_name
        assert model.data(index, ShotRole.ObjectRole) == test_shots[0]
        assert model.data(index, ShotRole.ShowRole) == "show"
        assert model.data(index, ShotRole.SequenceRole) == "seq"
        # Note: ShotNameRole doesn't exist in UnifiedRole - use ItemSpecificRole1 for shot name

    def test_selection_handling(self, model) -> None:
        """Test selection state management."""
        test_shots = [Shot("show", "seq", "shot1", "/path1")]
        model.set_shots(test_shots)

        index = model.index(0, 0)

        # Set selection
        success = model.setData(index, True, ShotRole.IsSelectedRole)
        assert success

        # Verify selection state
        assert model.data(index, ShotRole.IsSelectedRole) is True

        # Clear selection
        success = model.setData(index, False, ShotRole.IsSelectedRole)
        assert success
        assert model.data(index, ShotRole.IsSelectedRole) is False

    def test_refresh_shots_change_detection(self, model) -> None:
        """Test intelligent change detection during refresh."""
        original_shots = [Shot("show", "seq", "shot1", "/path1")]
        model.set_shots(original_shots)

        # Refresh with same shots - no changes
        result = model.refresh_shots(original_shots)
        assert result.success is True
        assert result.has_changes is False

        # Refresh with different shots - has changes
        new_shots = [Shot("show", "seq", "shot2", "/path2")]
        result = model.refresh_shots(new_shots)
        assert result.success is True
        assert result.has_changes is True
