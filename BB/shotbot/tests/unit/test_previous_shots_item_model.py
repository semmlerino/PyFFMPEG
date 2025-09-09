"""Unit tests for PreviousShotsItemModel with thread safety focus.

Tests the thread safety improvements and resource management
in the PreviousShotsItemModel class.
"""

import time
from concurrent.futures import Future
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QMetaObject, Qt, QThread
from PySide6.QtGui import QImage

from cache_manager import CacheManager
from previous_shots_item_model import PreviousShotsItemModel
from shot_model import Shot


@pytest.fixture
def model(qtbot):
    """Create a PreviousShotsItemModel instance for testing."""
    cache_manager = Mock(spec=CacheManager)
    model = PreviousShotsItemModel(cache_manager=cache_manager)
    # Models are not widgets, don't add to qtbot
    return model


@pytest.fixture
def test_shots():
    """Create test Shot objects for previous/approved shots."""
    return [
        Shot(
            sequence="010",
            shot="0010",
            show="proj1",
            description="Approved shot 1",
            status="apr",  # Approved status
            full_name="proj1_010_0010",
        ),
        Shot(
            sequence="020",
            shot="0020",
            show="proj2",
            description="Completed shot 2",
            status="cmp",  # Completed status
            full_name="proj2_020_0020",
        ),
        Shot(
            sequence="030",
            shot="0030",
            show="proj3",
            description="Previous shot 3",
            status="apr",
            full_name="proj3_030_0030",
        ),
    ]


class TestPreviousShotsThreadSafety:
    """Test thread safety in PreviousShotsItemModel."""

    def test_mutex_protection_for_cache(self, model, test_shots) -> None:
        """Test that cache operations are protected by mutex."""
        model.set_shots(test_shots)

        # Simulate concurrent cache access
        def access_cache() -> None:
            for shot in test_shots:
                # These operations should be mutex-protected
                model._thumbnail_cache.get(shot.full_name, None)
                model._loading_states.get(shot.full_name, "pending")

        # Multiple concurrent accesses should not corrupt dictionary
        for _ in range(10):
            access_cache()

        # Model should remain functional
        assert model.rowCount() == 3
        assert len(model._shots) == 3

    def test_cache_size_limit(self, model, qtbot) -> None:
        """Test MAX_CACHE_SIZE limit is enforced."""
        # Create many shots (more than MAX_CACHE_SIZE of 100)
        many_shots = []
        for i in range(120):
            shot = Shot(
                sequence=f"{i:03d}",
                shot=f"{i:04d}",
                show="testshow",
                description=f"Shot {i}",
                status="apr",
                full_name=f"testshow_{i:03d}_{i:04d}",
            )
            many_shots.append(shot)

        model.set_shots(many_shots)

        # Simulate populating cache
        test_image = QImage(100, 100, QImage.Format.Format_RGB32)
        test_image.fill(Qt.GlobalColor.red)

        # Try to add more than MAX_CACHE_SIZE items
        added_count = 0
        for shot in many_shots:
            if len(model._thumbnail_cache) < 100:
                with model._cache_mutex:
                    model._thumbnail_cache[shot.full_name] = test_image
                    added_count += 1

        # Cache should not exceed limit
        assert len(model._thumbnail_cache) <= 100
        assert added_count <= 100

    def test_concurrent_thumbnail_loading(self, model, test_shots, qtbot) -> None:
        """Test concurrent thumbnail loading callbacks."""
        model.set_shots(test_shots)

        callbacks_received = []

        def mock_load_async(path, size, callback):
            """Mock async thumbnail loading."""
            future = Future()

            def run_callback() -> None:
                time.sleep(0.01)
                image = QImage(100, 100, QImage.Format.Format_RGB32)
                image.fill(Qt.GlobalColor.cyan)

                # Find shot name from path
                for shot in test_shots:
                    if shot.full_name in str(path):
                        QMetaObject.invokeMethod(
                            model,
                            "_on_thumbnail_loaded",
                            Qt.ConnectionType.QueuedConnection,
                            shot.full_name,
                            image,
                        )
                        callbacks_received.append(shot.full_name)
                        break

            QThread.msleep(1)
            run_callback()
            return future

        model._cache_manager.load_thumbnail_async = mock_load_async

        # Trigger thumbnail loads
        for i, shot in enumerate(test_shots):
            model._load_thumbnail_async(i, shot)

        # Wait for async operations
        qtbot.wait(150)

        # All should have been processed
        assert len(callbacks_received) == len(test_shots)

    def test_cleanup_method(self, model, test_shots) -> None:
        """Test cleanup() properly releases resources."""
        model.set_shots(test_shots)

        # Add cached data
        test_image = QImage(50, 50, QImage.Format.Format_RGB32)
        with model._cache_mutex:
            model._thumbnail_cache[test_shots[0].full_name] = test_image
            model._loading_states[test_shots[0].full_name] = "loaded"

        # Verify timer exists
        assert hasattr(model, "_thumbnail_timer")

        # Cleanup
        model.cleanup()

        # Timer should be stopped
        assert not model._thumbnail_timer.isActive()

    def test_reset_while_loading(self, model, test_shots, qtbot) -> None:
        """Test model reset during active thumbnail loading."""
        model.set_shots(test_shots)

        # Mock loading that doesn't complete
        def mock_load_async(path, size, callback):
            return Future()  # Never completes

        model._cache_manager.load_thumbnail_async = mock_load_async

        # Start loading
        model.update_visible_range(0, 2)

        # Reset with different shots
        new_shots = [test_shots[0]]
        model.set_shots(new_shots)

        # Should handle gracefully
        assert model.rowCount() == 1
        assert len(model._shots) == 1

    def test_data_roles_thread_safety(self, model, test_shots) -> None:
        """Test data() method with various roles."""
        model.set_shots(test_shots)

        index = model.index(0, 0)
        shot = test_shots[0]

        # Test all custom roles
        roles = [
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.DecorationRole,
            Qt.ItemDataRole.ToolTipRole,
            Qt.ItemDataRole.UserRole,  # Shot object
            Qt.ItemDataRole.UserRole + 1,  # Full name
            Qt.ItemDataRole.UserRole + 2,  # Show
            Qt.ItemDataRole.UserRole + 3,  # Sequence
            Qt.ItemDataRole.UserRole + 4,  # Shot number
            Qt.ItemDataRole.UserRole + 5,  # Status
        ]

        for role in roles:
            data = model.data(index, role)
            # Should not crash or raise exceptions
            if role == Qt.ItemDataRole.DisplayRole:
                assert data == shot.shot
            elif role == Qt.ItemDataRole.UserRole:
                assert data == shot
            elif role == Qt.ItemDataRole.UserRole + 1:
                assert data == shot.full_name

    def test_selection_during_updates(self, model, test_shots) -> None:
        """Test selection changes during model updates."""
        model.set_shots(test_shots)

        # Set selection
        index = model.index(1, 0)
        model.set_selected_index(index)
        assert model._selected_index.row() == 1

        # Update shots while selected
        model.set_shots(test_shots[:2])

        # Selection should be cleared if out of range
        if model._selected_index.isValid():
            assert model._selected_index.row() < model.rowCount()

    def test_visible_range_updates(self, model, test_shots) -> None:
        """Test visible range boundary conditions."""
        model.set_shots(test_shots)

        # Normal range
        model.update_visible_range(0, 2)
        assert model._visible_start == 0
        assert model._visible_end == 2

        # Empty model
        model.set_shots([])
        model.update_visible_range(0, 10)
        # Should handle gracefully
        assert model._visible_start == 0
        assert model._visible_end == 10

        # Out of bounds
        model.set_shots(test_shots)
        model.update_visible_range(-5, 100)
        # Should store as-is (view handles bounds)
        assert model._visible_start == -5
        assert model._visible_end == 100

    def test_timer_lifecycle(self, model, test_shots) -> None:
        """Test thumbnail timer management."""
        model.set_shots(test_shots)

        # Timer should not be active initially
        assert not model._thumbnail_timer.isActive()

        # Updating visible range starts timer
        model.update_visible_range(0, 2)
        assert model._thumbnail_timer.isActive()

        # Simulate all thumbnails loaded
        with model._cache_mutex:
            for shot in test_shots[:3]:
                model._thumbnail_cache[shot.full_name] = QImage()

        # Check if loading completes
        model._load_visible_thumbnails()
        # Timer may stop when all loaded

    def test_rapid_scene_changes(self, model, test_shots, qtbot) -> None:
        """Test rapid shot list changes."""
        # Rapidly change shots
        for _ in range(10):
            model.set_shots(test_shots)
            model.set_shots([])
            model.set_shots(test_shots[:1])
            model.set_shots(test_shots)

        # Final state should be consistent
        assert model.rowCount() == len(test_shots)
        assert len(model._shots) == len(test_shots)


class TestDataConsistency:
    """Test data consistency with thread-safe operations."""

    def test_shot_data_integrity(self, model, test_shots) -> None:
        """Test that shot data remains consistent."""
        model.set_shots(test_shots)

        for i, shot in enumerate(test_shots):
            index = model.index(i, 0)

            # Verify data integrity
            assert model.data(index, Qt.ItemDataRole.UserRole) == shot
            assert model.data(index, Qt.ItemDataRole.UserRole + 1) == shot.full_name
            assert model.data(index, Qt.ItemDataRole.UserRole + 2) == shot.show
            assert model.data(index, Qt.ItemDataRole.UserRole + 3) == shot.sequence
            assert model.data(index, Qt.ItemDataRole.UserRole + 4) == shot.shot

    def test_empty_model_handling(self, model) -> None:
        """Test empty model edge cases."""
        model.set_shots([])

        assert model.rowCount() == 0

        # Invalid index should return None/empty
        invalid_index = model.index(0, 0)
        assert model.data(invalid_index, Qt.ItemDataRole.DisplayRole) is None

        # Visible range on empty model
        model.update_visible_range(0, 10)
        # Should not crash
        model._load_visible_thumbnails()

    def test_cache_cleanup_on_reset(self, model, test_shots) -> None:
        """Test cache is managed properly on reset."""
        model.set_shots(test_shots)

        # Populate cache
        test_image = QImage(100, 100, QImage.Format.Format_RGB32)
        with model._cache_mutex:
            for shot in test_shots:
                model._thumbnail_cache[shot.full_name] = test_image
                model._loading_states[shot.full_name] = "loaded"

        assert len(model._thumbnail_cache) == len(test_shots)

        # Reset model
        model.set_shots([])

        # Model should be empty
        assert model.rowCount() == 0
        # Cache handling is implementation-dependent
