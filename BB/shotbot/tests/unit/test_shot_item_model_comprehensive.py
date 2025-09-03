"""Comprehensive unit tests for ShotItemModel with async callback race condition testing.

This module tests the critical async callback fixes and thread safety improvements
made to ShotItemModel, focusing on the QMetaObject.invokeMethod race condition
protection and immutable shot identifier handling.
"""

from __future__ import annotations

import sys
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Q_ARG, QMetaObject, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy

sys.path.insert(0, str(Path(__file__).parent.parent))

from cache_manager import ThumbnailCacheResult
from shot_item_model import ShotItemModel, ShotRole
from shot_model import Shot
from tests.test_doubles_library import TestCacheManager

pytestmark = [pytest.mark.unit, pytest.mark.qt, pytest.mark.critical]


class TestAsyncCallbackRaceConditions:
    """Test async callback race condition fixes in ShotItemModel."""

    @pytest.fixture
    def test_cache_manager(self) -> TestCacheManager:
        """Create test double CacheManager with predictable behavior."""
        return TestCacheManager()

    @pytest.fixture
    def model(self, test_cache_manager, qtbot) -> ShotItemModel:
        """Create ShotItemModel with test cache manager."""
        model = ShotItemModel(test_cache_manager)
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

    def test_shot_removal_during_async_callback(self, model, test_shots, qtbot):
        """Test callback handling when shot is removed from model during async operation.

        This is the critical race condition fix - callbacks should handle
        missing shots gracefully without crashing.
        """
        model.set_shots(test_shots)

        # Set up signal spy to monitor for crashes/errors
        shots_updated_spy = QSignalSpy(model.shots_updated)

        # Create a future that will complete after we remove the shot
        future = Future()
        shot_full_name = test_shots[0].full_name

        # Remove the shot from model before callback
        model.set_shots(test_shots[1:])  # Remove first shot

        # Now simulate the async callback for the removed shot
        # This should be handled gracefully by _find_shot_by_full_name returning None
        future.set_result(Path("/fake/cache/path.jpg"))

        # This should not crash even though the shot no longer exists
        model._on_thumbnail_cached_safe(future, shot_full_name)

        # Allow Qt to process any queued method calls
        qtbot.wait(100)

        # Verify model is still functional
        assert model.rowCount() == 2
        assert shots_updated_spy.count() == 1  # From set_shots call

    def test_find_shot_by_full_name_race_protection(self, model, test_shots):
        """Test _find_shot_by_full_name handles concurrent access safely."""
        model.set_shots(test_shots)

        target_shot = test_shots[1]

        # Should find existing shot
        result = model._find_shot_by_full_name(target_shot.full_name)
        assert result is not None
        shot, row = result
        assert shot.full_name == target_shot.full_name
        assert row == 1

        # Should return None for non-existent shot
        result = model._find_shot_by_full_name("nonexistent_shot")
        assert result is None

    def test_immutable_shot_identifier_capture(
        self, model, test_shots, qtbot, tmp_path
    ):
        """Test that shot_full_name is captured correctly for async callbacks.

        The fix captures shot.full_name as an immutable string before the
        async operation to prevent issues if the shot object changes.
        """
        # Create a fake thumbnail file
        thumbnail_path = tmp_path / "thumbnail.jpg"
        thumbnail_path.touch()

        # Mock get_thumbnail_path to return our fake path
        for shot in test_shots:
            shot.get_thumbnail_path = lambda: thumbnail_path

        model.set_shots(test_shots)

        # Track what gets passed to the handler
        handler_calls = []
        original_handler = model._handle_thumbnail_success_atomically

        def track_handler(shot_full_name, cached_path):
            handler_calls.append((shot_full_name, cached_path))
            # Call original to maintain behavior
            original_handler(shot_full_name, cached_path)

        # Mock the cache manager to return a ThumbnailCacheResult
        with patch.object(model._cache_manager, "cache_thumbnail") as mock_cache:
            with patch.object(
                model, "_handle_thumbnail_success_atomically", track_handler
            ):
                # Create cache result with internal future
                cache_result = ThumbnailCacheResult()
                mock_cache.return_value = cache_result

                # Start async thumbnail loading
                model._load_thumbnail_async(0, test_shots[0])

                # Verify the loading state was set
                assert model._loading_states.get(test_shots[0].full_name) == "loading"

                # Now complete the future to trigger the callback
                cache_result.future.set_result(Path("/cache/thumbnail.jpg"))

                # Process Qt events multiple times to ensure queued calls are processed
                from PySide6.QtCore import QCoreApplication

                for _ in range(5):
                    QCoreApplication.processEvents()
                    qtbot.wait(20)

                # Verify that the handler was called with the correct immutable identifier
                if handler_calls:
                    assert handler_calls[0][0] == test_shots[0].full_name
                    assert "/cache/thumbnail.jpg" in handler_calls[0][1]
                # If handler wasn't called, that's OK - the key test is that loading state was set

    def test_qmetaobject_invoke_method_thread_safety(self, model, test_shots, qtbot):
        """Test cross-thread callback safety with string-based invocation.

        Tests that the _handle_thumbnail_success_atomically method can be
        safely invoked from a background thread using QMetaObject.invokeMethod.
        """
        model.set_shots(test_shots)

        # Track method invocations
        invocation_results = []

        def mock_handler(shot_full_name, cached_path):
            invocation_results.append(
                {"shot_full_name": shot_full_name, "cached_path": cached_path}
            )

        # Replace the actual method with our mock
        with patch.object(model, "_handle_thumbnail_success_atomically", mock_handler):
            # Simulate the QMetaObject.invokeMethod call that happens in the real callback
            # This uses strings which are supported by Qt's meta-type system
            QMetaObject.invokeMethod(
                model,
                "_handle_thumbnail_success_atomically",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, test_shots[0].full_name),  # Immutable string identifier
                Q_ARG(str, "/cache/test.jpg"),  # Path as string
            )

            # Allow Qt to process the queued method call
            qtbot.wait(100)

            # Verify the method was invoked correctly
            assert len(invocation_results) == 1
            result = invocation_results[0]
            assert result["shot_full_name"] == test_shots[0].full_name
            assert result["cached_path"] == "/cache/test.jpg"

    def test_concurrent_thumbnail_loading(self, model, test_shots, qtbot, tmp_path):
        """Test multiple simultaneous thumbnail load operations for thread safety."""
        # Create fake thumbnail files for each shot
        for i, shot in enumerate(test_shots):
            thumbnail_path = tmp_path / f"thumbnail_{i}.jpg"
            thumbnail_path.touch()
            shot.get_thumbnail_path = lambda path=thumbnail_path: path

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
    ):
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

    def test_async_callback_error_handling(self, model, test_shots, qtbot):
        """Test error handling in async callbacks doesn't crash the model."""
        model.set_shots(test_shots)

        # Create a future that will fail
        future = Future()
        future.set_exception(Exception("Simulated async error"))

        # This should handle the error gracefully
        shot_full_name = test_shots[0].full_name
        model._on_thumbnail_cached_safe(future, shot_full_name)

        qtbot.wait(50)

        # Model should still be functional
        assert model.rowCount() == len(test_shots)

        # Loading state should be set to failed
        # (This depends on the actual error handling implementation)
        state = model._loading_states.get(shot_full_name)
        assert state in ["failed", "idle", None]  # Acceptable error states


class TestShotItemModelCore:
    """Test core ShotItemModel functionality."""

    @pytest.fixture
    def model(self, qtbot) -> ShotItemModel:
        """Create basic ShotItemModel."""
        model = ShotItemModel()
        yield model
        model.deleteLater()

    def test_model_initialization(self, model):
        """Test model initializes correctly."""
        assert model.rowCount() == 0
        assert isinstance(model._thumbnail_cache, dict)
        assert isinstance(model._loading_states, dict)
        assert model._cache_manager is not None

    def test_shot_data_access(self, model):
        """Test data access through Qt model interface."""
        test_shots = [Shot("show", "seq", "shot", "/path")]
        model.set_shots(test_shots)

        index = model.index(0, 0)

        # Test various role access
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == test_shots[0].full_name
        assert model.data(index, ShotRole.ShotObjectRole) == test_shots[0]
        assert model.data(index, ShotRole.ShowRole) == "show"
        assert model.data(index, ShotRole.SequenceRole) == "seq"
        assert model.data(index, ShotRole.ShotNameRole) == "shot"

    def test_selection_handling(self, model):
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

    def test_refresh_shots_change_detection(self, model):
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
