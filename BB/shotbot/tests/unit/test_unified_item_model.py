"""Tests for UnifiedItemModel to ensure compatibility with replaced models."""

from __future__ import annotations

# Standard library imports
from pathlib import Path
from unittest.mock import MagicMock, patch

# Third-party imports
import pytest
from PySide6.QtCore import Qt

# Local application imports
from shot_model import Shot
from tests.test_doubles import MockCacheManager
from tests.test_helpers import SignalDouble
from threede_scene_model import ThreeDEScene
from unified_item_model import (
    UnifiedItemModel,
    UnifiedItemType,
    UnifiedRole,
    create_previous_shots_item_model,
    create_shot_item_model,
    create_threede_item_model,
)


class MockPreviousShotsModel:
    """Test double for PreviousShotsModel following UNIFIED_TESTING_GUIDE."""

    def __init__(self) -> None:
        self.shots_updated = SignalDouble()
        self.scan_started = SignalDouble()
        self.scan_finished = SignalDouble()
        self.scan_progress = SignalDouble()
        self._shots = []
        self._filter_show = None

        # Mock objects for testing
        self.get_shots = MagicMock(return_value=self._shots)
        self.refresh_shots = MagicMock(return_value=True)

    def add_shot(self, shot) -> None:
        """Add a test shot."""
        self._shots.append(shot)
        # Update the mock return value
        self.get_shots.return_value = self._shots
        self.shots_updated.emit()

    def set_show_filter(self, show: str | None) -> None:
        """Mock show filter."""
        self._filter_show = show

    def get_filtered_shots(self) -> list[Shot]:
        """Mock filtered shots."""
        if not self._filter_show:
            return self._shots
        return [shot for shot in self._shots if shot.show == self._filter_show]


class TestUnifiedItemModelShot:
    """Test UnifiedItemModel with SHOT type for compatibility with ShotItemModel."""

    @pytest.fixture
    def cache_manager(self):
        """Create a mock cache manager."""
        return MockCacheManager()

    @pytest.fixture
    def sample_shots(self):
        """Create sample shots for testing."""
        return [
            Shot(
                show="test_show",
                sequence="seq01",
                shot="shot01",
                workspace_path="/test/path1",
            ),
            Shot(
                show="test_show",
                sequence="seq01",
                shot="shot02",
                workspace_path="/test/path2",
            ),
            Shot(
                show="other_show",
                sequence="seq02",
                shot="shot03",
                workspace_path="/test/path3",
            ),
        ]

    @pytest.fixture
    def unified_model(self, cache_manager):
        """Create a unified model for shot items."""
        model = UnifiedItemModel(UnifiedItemType.SHOT, cache_manager)
        yield model
        # Cleanup to prevent Qt warnings
        model.cleanup()
        model.deleteLater()

    def test_model_initialization(self, unified_model) -> None:
        """Test that the model initializes correctly."""
        assert unified_model.item_type == UnifiedItemType.SHOT
        assert unified_model.rowCount() == 0
        assert hasattr(unified_model, "shots_updated")
        assert hasattr(unified_model, "items_updated")

    def test_factory_function(self, cache_manager) -> None:
        """Test the factory function creates correct model."""
        model = create_shot_item_model(cache_manager)
        try:
            assert model.item_type == UnifiedItemType.SHOT
            assert model._cache_manager == cache_manager
        finally:
            model.cleanup()
            model.deleteLater()

    def test_set_shots_compatibility(self, unified_model, sample_shots) -> None:
        """Test set_shots method works like original ShotItemModel."""
        unified_model.set_shots(sample_shots)

        assert unified_model.rowCount() == 3
        assert len(unified_model.shots) == 3
        assert unified_model.shots[0].full_name == "seq01_shot01"

    def test_data_role_compatibility(self, unified_model, sample_shots) -> None:
        """Test data() method returns correct values for all roles."""
        unified_model.set_shots(sample_shots)
        index = unified_model.index(0, 0)

        # Test display role
        display_data = unified_model.data(index, Qt.ItemDataRole.DisplayRole)
        assert display_data == "seq01_shot01"

        # Test tooltip role
        tooltip_data = unified_model.data(index, Qt.ItemDataRole.ToolTipRole)
        assert "test_show / seq01 / shot01" in tooltip_data
        assert "/test/path1" in tooltip_data

        # Test custom roles
        shot_name = unified_model.data(index, UnifiedRole.ItemSpecificRole1)
        assert shot_name == "shot01"

        full_name = unified_model.data(index, UnifiedRole.FullNameRole)
        assert full_name == "seq01_shot01"

        shot_obj = unified_model.data(index, UnifiedRole.ObjectRole)
        assert isinstance(shot_obj, Shot)
        assert shot_obj.show == "test_show"

    def test_compatibility_methods(self, unified_model, sample_shots) -> None:
        """Test compatibility methods work like original model."""
        unified_model.set_shots(sample_shots)
        index = unified_model.index(1, 0)

        # Test get_shot_at_index
        shot = unified_model.get_shot_at_index(index)
        assert shot is not None
        assert shot.full_name == "seq01_shot02"

        # Test _find_shot_by_full_name
        result = unified_model._find_shot_by_full_name("seq02_shot03")
        assert result is not None
        shot, row = result
        assert shot.full_name == "seq02_shot03"
        assert row == 2

    def test_refresh_shots_compatibility(self, unified_model, sample_shots) -> None:
        """Test refresh_shots method maintains API compatibility."""
        # Set initial shots
        unified_model.set_shots(sample_shots[:2])
        assert unified_model.rowCount() == 2

        # Refresh with same shots (no changes)
        result = unified_model.refresh_shots(sample_shots[:2])
        assert result.success is True
        assert result.has_changes is False

        # Refresh with different shots (has changes)
        result = unified_model.refresh_shots(sample_shots)
        assert result.success is True
        assert result.has_changes is True
        assert unified_model.rowCount() == 3


class TestUnifiedItemModelThreeDe:
    """Test UnifiedItemModel with THREEDE type for compatibility with ThreeDEItemModel."""

    @pytest.fixture
    def cache_manager(self):
        """Create a mock cache manager."""
        return MockCacheManager()

    @pytest.fixture
    def sample_scenes(self):
        """Create sample 3DE scenes for testing."""
        return [
            ThreeDEScene(
                show="test_show",
                sequence="seq01",
                shot="shot01",
                workspace_path="/test/path1",
                user="artist1",
                plate="FG01",
                scene_path=Path("/scenes/test.3de"),
            ),
            ThreeDEScene(
                show="test_show",
                sequence="seq01",
                shot="shot02",
                workspace_path="/test/path2",
                user="artist2",
                plate="BG01",
                scene_path=Path("/scenes/test2.3de"),
            ),
        ]

    @pytest.fixture
    def unified_model(self, cache_manager):
        """Create a unified model for 3DE items."""
        model = UnifiedItemModel(UnifiedItemType.THREEDE, cache_manager)
        yield model
        # Cleanup to prevent Qt warnings
        model.cleanup()
        model.deleteLater()

    def test_threede_initialization(self, unified_model) -> None:
        """Test ThreeDe-specific initialization."""
        assert unified_model.item_type == UnifiedItemType.THREEDE
        assert hasattr(unified_model, "scenes_updated")
        assert hasattr(unified_model, "loading_started")
        assert hasattr(unified_model, "loading_progress")
        assert hasattr(unified_model, "loading_finished")

    def test_factory_function(self, cache_manager) -> None:
        """Test the factory function creates correct model."""
        model = create_threede_item_model(cache_manager)
        try:
            assert model.item_type == UnifiedItemType.THREEDE
        finally:
            model.cleanup()
            model.deleteLater()

    def test_threede_tooltip_format(self, unified_model, sample_scenes) -> None:
        """Test ThreeDe-specific tooltip format."""
        unified_model.set_scenes(sample_scenes)
        index = unified_model.index(0, 0)

        tooltip = unified_model.data(index, Qt.ItemDataRole.ToolTipRole)
        assert "Scene: shot01" in tooltip
        assert "User: artist1" in tooltip
        assert "Path: /scenes/test.3de" in tooltip

    def test_threede_custom_roles(self, unified_model, sample_scenes) -> None:
        """Test ThreeDe-specific custom roles."""
        unified_model.set_scenes(sample_scenes)
        index = unified_model.index(0, 0)

        # Test ThreeDe-specific roles
        shot_name = unified_model.data(index, UnifiedRole.ItemSpecificRole1)
        assert shot_name == "shot01"

        user = unified_model.data(index, UnifiedRole.ItemSpecificRole2)
        assert user == "artist1"

        scene_path = unified_model.data(index, UnifiedRole.ItemSpecificRole3)
        assert scene_path == Path("/scenes/test.3de")

    def test_threede_loading_state(self, unified_model) -> None:
        """Test ThreeDe-specific loading state management."""
        assert not unified_model.is_loading

        # Test loading started
        with patch.object(unified_model, "loading_started") as mock_started:
            unified_model.set_loading_state(True)
            mock_started.emit.assert_called_once()
        assert unified_model.is_loading

        # Test loading finished
        with patch.object(unified_model, "loading_finished") as mock_finished:
            unified_model.set_loading_state(False)
            mock_finished.emit.assert_called_once()
        assert not unified_model.is_loading

    def test_threede_progress_updates(self, unified_model) -> None:
        """Test ThreeDe-specific progress updates."""
        with patch.object(unified_model, "loading_progress") as mock_progress:
            unified_model.update_loading_progress(5, 10)
            mock_progress.emit.assert_called_once_with(5, 10)

    def test_set_scenes_compatibility(self, unified_model, sample_scenes) -> None:
        """Test set_scenes method works like original ThreeDEItemModel."""
        unified_model.set_scenes(sample_scenes)

        assert unified_model.rowCount() == 2
        assert len(unified_model.scenes) == 2
        assert unified_model.scenes[0].user == "artist1"


class TestUnifiedItemModelPrevious:
    """Test UnifiedItemModel with PREVIOUS type for compatibility with PreviousShotsItemModel."""

    @pytest.fixture
    def cache_manager(self):
        """Create a mock cache manager."""
        return MockCacheManager()

    @pytest.fixture
    def mock_previous_model(self):
        """Create a mock previous shots model."""
        return MockPreviousShotsModel()

    @pytest.fixture
    def sample_shots(self):
        """Create sample shots for testing."""
        return [
            Shot(
                show="prev_show",
                sequence="seq01",
                shot="shot01",
                workspace_path="/prev/path1",
            ),
        ]

    @pytest.fixture
    def unified_model(self, cache_manager, mock_previous_model):
        """Create a unified model for previous shots."""
        model = UnifiedItemModel(
            UnifiedItemType.PREVIOUS, cache_manager, None, mock_previous_model
        )
        yield model
        # Cleanup to prevent Qt warnings
        model.cleanup()
        model.deleteLater()

    def test_previous_initialization(self, unified_model, mock_previous_model) -> None:
        """Test Previous-specific initialization."""
        assert unified_model.item_type == UnifiedItemType.PREVIOUS
        assert unified_model._underlying_model == mock_previous_model
        assert hasattr(unified_model, "shots_updated")

    def test_factory_function(self, cache_manager, mock_previous_model) -> None:
        """Test the factory function creates correct model."""
        model = create_previous_shots_item_model(mock_previous_model, cache_manager)
        try:
            assert model.item_type == UnifiedItemType.PREVIOUS
            assert model._underlying_model == mock_previous_model
        finally:
            model.cleanup()
            model.deleteLater()

    def test_underlying_model_integration(
        self, unified_model, mock_previous_model, sample_shots
    ) -> None:
        """Test integration with underlying previous shots model."""
        # Set up mock to return shots
        mock_previous_model.get_shots.return_value = sample_shots

        # Trigger update
        unified_model._update_from_underlying_model()

        assert unified_model.rowCount() == 1
        assert unified_model.shots[0].show == "prev_show"

    def test_refresh_method(self, unified_model, mock_previous_model) -> None:
        """Test refresh method delegates to underlying model."""
        unified_model.refresh()
        mock_previous_model.refresh_shots.assert_called_once()

    def test_get_underlying_model(self, unified_model, mock_previous_model) -> None:
        """Test get_underlying_model returns correct model."""
        result = unified_model.get_underlying_model()
        assert result == mock_previous_model


class TestUnifiedItemModelCrossType:
    """Test unified model behavior across different types."""

    @pytest.fixture
    def cache_manager(self):
        """Create a mock cache manager."""
        return MockCacheManager()

    def test_item_type_isolation(self, cache_manager) -> None:
        """Test that different types don't interfere with each other."""
        shot_model = UnifiedItemModel(UnifiedItemType.SHOT, cache_manager)
        threede_model = UnifiedItemModel(UnifiedItemType.THREEDE, cache_manager)

        try:
            # ThreeDe features should not work on shot model
            assert not shot_model.is_loading
            shot_model.set_loading_state(True)  # Should be ignored
            assert not shot_model.is_loading

            # Shot features should not interfere with ThreeDe model
            assert not threede_model.is_loading
            threede_model.set_loading_state(True)
            assert threede_model.is_loading
        finally:
            shot_model.cleanup()
            shot_model.deleteLater()
            threede_model.cleanup()
            threede_model.deleteLater()

    def test_signal_routing(self, cache_manager) -> None:
        """Test that signals are routed correctly based on type."""
        shot_model = UnifiedItemModel(UnifiedItemType.SHOT, cache_manager)
        threede_model = UnifiedItemModel(UnifiedItemType.THREEDE, cache_manager)

        try:
            # Track signal emissions
            shot_signals = []
            scene_signals = []

            shot_model.shots_updated.connect(lambda: shot_signals.append("shots"))
            shot_model.scenes_updated.connect(lambda: shot_signals.append("scenes"))
            threede_model.shots_updated.connect(lambda: scene_signals.append("shots"))
            threede_model.scenes_updated.connect(lambda: scene_signals.append("scenes"))

            # Trigger updates
            shot_model.items_updated.emit()
            threede_model.items_updated.emit()

            # Verify correct signal routing
            assert "shots" in shot_signals
            assert "scenes" not in shot_signals
            assert "scenes" in scene_signals
            assert "shots" not in scene_signals
        finally:
            shot_model.cleanup()
            shot_model.deleteLater()
            threede_model.cleanup()
            threede_model.deleteLater()

    def test_cleanup_consistency(self, cache_manager) -> None:
        """Test that cleanup works consistently across all types."""
        models = [
            UnifiedItemModel(UnifiedItemType.SHOT, cache_manager),
            UnifiedItemModel(UnifiedItemType.THREEDE, cache_manager),
            UnifiedItemModel(UnifiedItemType.PREVIOUS, cache_manager),
        ]

        try:
            for model in models:
                # Test cleanup doesn't raise errors
                model.cleanup()

                # Test deleteLater works
                model.deleteLater()
        except Exception:
            # Clean up any remaining models on error
            for model in models:
                try:
                    model.cleanup()
                    model.deleteLater()
                except Exception:
                    pass
            raise


class TestBackwardCompatibility:
    """Test that unified model maintains exact API compatibility."""

    @pytest.fixture
    def cache_manager(self):
        """Create a mock cache manager."""
        return MockCacheManager()

    def test_all_original_methods_exist(self, cache_manager) -> None:
        """Test that all methods from original models exist in unified model."""
        # Test Shot model compatibility
        shot_model = create_shot_item_model(cache_manager)
        threede_model = create_threede_item_model(cache_manager)

        try:
            # Methods from ShotItemModel
            assert hasattr(shot_model, "set_shots")
            assert hasattr(shot_model, "refresh_shots")
            assert hasattr(shot_model, "get_shot_at_index")
            assert hasattr(shot_model, "_find_shot_by_full_name")
            assert hasattr(shot_model, "set_show_filter")

            # Methods from ThreeDEItemModel
            assert hasattr(threede_model, "set_scenes")
            assert hasattr(threede_model, "get_scene")
            assert hasattr(threede_model, "set_selected")
            assert hasattr(threede_model, "set_loading_state")
            assert hasattr(threede_model, "update_loading_progress")
            assert hasattr(threede_model, "is_loading")
            assert hasattr(threede_model, "cleanup")
        finally:
            shot_model.cleanup()
            shot_model.deleteLater()
            threede_model.cleanup()
            threede_model.deleteLater()

    def test_signal_compatibility(self, cache_manager) -> None:
        """Test that all signals from original models exist."""
        shot_model = create_shot_item_model(cache_manager)
        threede_model = create_threede_item_model(cache_manager)

        try:
            # Common signals
            for model in [shot_model, threede_model]:
                assert hasattr(model, "items_updated")
                assert hasattr(model, "thumbnail_loaded")
                assert hasattr(model, "selection_changed")
                assert hasattr(model, "show_filter_changed")

            # Type-specific signals
            assert hasattr(shot_model, "shots_updated")
            assert hasattr(threede_model, "scenes_updated")
            assert hasattr(threede_model, "loading_started")
            assert hasattr(threede_model, "loading_progress")
            assert hasattr(threede_model, "loading_finished")
        finally:
            shot_model.cleanup()
            shot_model.deleteLater()
            threede_model.cleanup()
            threede_model.deleteLater()

    def test_property_compatibility(self, cache_manager) -> None:
        """Test that all properties from original models exist."""
        shot_model = create_shot_item_model(cache_manager)
        threede_model = create_threede_item_model(cache_manager)

        try:
            # Properties that should exist
            assert hasattr(shot_model, "shots")
            assert hasattr(threede_model, "scenes")
            assert hasattr(threede_model, "is_loading")

            # Test property access doesn't raise errors
            _ = shot_model.shots
            _ = threede_model.scenes
            _ = threede_model.is_loading
        finally:
            shot_model.cleanup()
            shot_model.deleteLater()
            threede_model.cleanup()
            threede_model.deleteLater()
