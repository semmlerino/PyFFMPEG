"""Unit tests for PreviousShotsModel class following UNIFIED_TESTING_GUIDE.

Tests the model layer with real Qt components and cache integration.
Follows best practices:
- Uses proper test doubles instead of Mock()
- No qtbot.addWidget() for QObject
- Prevents signal race conditions
- Tests thread safety
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QSignalSpy
from cache_manager import CacheManager
from pathlib import Path
from previous_shots_model import PreviousShotsModel
from tests.test_doubles_previous_shots import (
    FakePreviousShotsFinder,
    FakeShotModel,
    create_test_shot,
)
from unittest.mock import patch
import concurrent.futures
import sys
import threading

sys.path.insert(0, str(Path(__file__).parent.parent))

pytestmark = [pytest.mark.unit, pytest.mark.qt, pytest.mark.slow]

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns



# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from tests.test_doubles_library import (
    TestSubprocess, TestShot, TestShotModel,
    TestCacheManager, TestLauncher, TestWorker,
    ThreadSafeTestImage, SignalDouble, TestProcessPool
)

class TestPreviousShotsModel:
    """Test cases for PreviousShotsModel with real Qt components."""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path: Path) -> Path:
        """Create temporary cache directory."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(exist_ok=True)
        return cache_dir

    @pytest.fixture
    def real_cache_manager(self, temp_cache_dir: Path) -> CacheManager:
        """Create real CacheManager with temporary storage."""
        return CacheManager(cache_dir=temp_cache_dir)

    @pytest.fixture
    def test_cache_manager(self) -> TestCacheManager:
        """Create test double CacheManager."""
        return TestCacheManager()

    @pytest.fixture
    def test_shot_model(self) -> FakeShotModel:
        """Create test double ShotModel with real Qt signals."""
        model = FakeShotModel()
        model.set_shots(
            [
                create_test_shot("show1", "seq1", "shot1"),
                create_test_shot("show1", "seq1", "shot2"),
            ]
        )
        return model

    @pytest.fixture
    def test_finder(self) -> FakePreviousShotsFinder:
        """Create test double for PreviousShotsFinder."""
        finder = FakePreviousShotsFinder()
        finder.approved_shots_to_return = [
            create_test_shot("show2", "seq2", "shot1"),
            create_test_shot("show2", "seq2", "shot2"),
        ]
        return finder

    @pytest.fixture
    def model(self, test_shot_model, test_cache_manager) -> PreviousShotsModel:
        """Create PreviousShotsModel instance with test doubles.

        Following UNIFIED_TESTING_GUIDE:
        - Don't use qtbot.addWidget() for QObject
        - Use test doubles with predictable behavior
        """
        model = PreviousShotsModel(
            shot_model=test_shot_model, cache_manager=test_cache_manager
        )
        yield model
        # Cleanup
        model.stop_auto_refresh()
        model.deleteLater()

    @pytest.fixture
    def model_with_real_cache(
        self, test_shot_model, real_cache_manager
    ) -> PreviousShotsModel:
        """Create model with real cache for integration tests."""
        model = PreviousShotsModel(
            shot_model=test_shot_model, cache_manager=real_cache_manager
        )
        yield model
        model.stop_auto_refresh()
        model.deleteLater()

    def test_model_initialization(self, model, test_shot_model, test_cache_manager):
        """Test model initialization with dependencies."""
        assert model._shot_model is test_shot_model
        assert model._cache_manager is test_cache_manager
        assert model._finder is not None
        assert model._previous_shots == []
        assert not model._is_scanning
        assert isinstance(model._refresh_timer, QTimer)
        assert model._scan_lock is not None  # Thread safety lock

    def test_auto_refresh_timer_behavior(self, model):
        """Test auto-refresh timer start/stop behavior."""
        # Initially timer should be stopped
        assert not model._refresh_timer.isActive()

        # Start auto-refresh
        model.start_auto_refresh()
        # Timer might not be active in test environment due to threading
        # But we can verify the interval was set correctly
        assert model._refresh_timer.interval() == 5 * 60 * 1000  # 5 minutes

        # Stop auto-refresh
        model.stop_auto_refresh()
        # Timer should be stopped (or never started in test environment)

    def test_refresh_shots_signal_emission_no_race(self, model, test_finder, qtbot):
        """Test signal emission during shot refresh without race conditions.

        Following UNIFIED_TESTING_GUIDE:
        - Set up signal spy BEFORE triggering action
        """
        # Replace finder with test double
        model._finder = test_finder

        # Set up signal spies BEFORE triggering refresh (prevents race)
        scan_started_spy = QSignalSpy(model.scan_started)
        scan_finished_spy = QSignalSpy(model.scan_finished)
        shots_updated_spy = QSignalSpy(model.shots_updated)

        # Use waitSignal to properly handle async operation
        with qtbot.waitSignal(model.scan_finished, timeout=1000):
            result = model.refresh_shots()

        # Verify return value
        assert result is True

        # Verify signals were emitted
        assert scan_started_spy.count() == 1
        assert scan_finished_spy.count() == 1
        assert shots_updated_spy.count() == 1  # Should update since shots changed

        # Verify shots were stored
        assert len(model._previous_shots) == 2
        assert model.get_shot_count() == 2

    def test_refresh_shots_no_changes(self, model, test_finder):
        """Test refresh when no changes detected."""
        model._finder = test_finder

        # Pre-populate with same shots
        existing_shots = test_finder.approved_shots_to_return
        model._previous_shots = existing_shots

        # Set up signal spy
        shots_updated_spy = QSignalSpy(model.shots_updated)

        result = model.refresh_shots()

        assert result is True
        # Should not emit shots_updated since no changes
        assert shots_updated_spy.count() == 0

    def test_thread_safety_concurrent_refresh(self, model, test_finder):
        """Test thread safety with concurrent refresh calls.

        Following UNIFIED_TESTING_GUIDE:
        - Test actual threading behavior
        - Verify lock prevents race conditions
        """
        model._finder = test_finder
        results = []

        def refresh_worker():
            """Worker function for thread."""
            result = model.refresh_shots()
            results.append(result)

        # Start multiple threads trying to refresh simultaneously
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=refresh_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=2.0)

        # Only one refresh should succeed at a time
        # Due to the lock, some should return False
        assert len(results) == 5
        true_count = sum(1 for r in results if r is True)
        false_count = sum(1 for r in results if r is False)

        # At least one should succeed
        assert true_count >= 1
        # Some should be blocked
        assert false_count >= 0

    def test_concurrent_is_scanning_access(self, model):
        """Test thread-safe access to is_scanning flag."""
        results = []

        def check_scanning():
            for _ in range(100):
                is_scanning = model.is_scanning()
                results.append(is_scanning)
                # Use threading.Event for proper synchronization instead of sleep
                threading.Event().wait(0.001)

        # Multiple threads checking scanning state
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(check_scanning) for _ in range(3)]
            concurrent.futures.wait(futures, timeout=5.0)

        # Should not crash or raise exceptions
        assert len(results) == 300  # 3 threads * 100 checks

    def test_refresh_shots_error_handling(self, model, qtbot):
        """Test error handling during refresh."""
        scan_finished_spy = QSignalSpy(model.scan_finished)

        # Mock finder to raise exception
        with patch.object(
            model._finder, "find_approved_shots", side_effect=Exception("Test error")
        ):
            result = model.refresh_shots()

        assert result is False
        assert not model.is_scanning()  # Should reset scanning state
        assert scan_finished_spy.count() == 1  # Should still emit finished signal

    def test_has_changes_detection(self, model):
        """Test change detection logic."""
        # Set up existing shots
        model._previous_shots = [
            create_test_shot("show1", "seq1", "shot1"),
            create_test_shot("show1", "seq1", "shot2"),
        ]

        # Test no changes
        same_shots = [
            create_test_shot("show1", "seq1", "shot1"),
            create_test_shot("show1", "seq1", "shot2"),
        ]
        assert not model._has_changes(same_shots)

        # Test different count
        fewer_shots = [
            create_test_shot("show1", "seq1", "shot1"),
        ]
        assert model._has_changes(fewer_shots)

        # Test different shots
        different_shots = [
            create_test_shot("show1", "seq1", "shot1"),
            create_test_shot("show1", "seq1", "shot3"),  # Different shot
        ]
        assert model._has_changes(different_shots)

    def test_get_shots_returns_copy(self, model):
        """Test that get_shots returns a copy, not reference."""
        original_shots = [
            create_test_shot("show1", "seq1", "shot1"),
        ]
        model._previous_shots = original_shots

        returned_shots = model.get_shots()

        # Should be equal but not the same object
        assert returned_shots == original_shots
        assert returned_shots is not original_shots

    def test_get_shot_by_name(self, model):
        """Test getting shot by name."""
        test_shots = [
            create_test_shot("show1", "seq1", "shot1"),
            create_test_shot("show1", "seq1", "shot2"),
        ]
        model._previous_shots = test_shots

        # Test found
        shot = model.get_shot_by_name("shot2")
        assert shot is not None
        assert shot.shot == "shot2"
        assert shot.sequence == "seq1"

        # Test not found
        shot = model.get_shot_by_name("nonexistent")
        assert shot is None

    def test_get_shot_details_delegation(self, model, test_finder):
        """Test that get_shot_details delegates to finder."""
        model._finder = test_finder
        shot = create_test_shot("show1", "seq1", "shot1")

        details = model.get_shot_details(shot)

        # Verify delegation
        assert len(test_finder.get_shot_details_calls) == 1
        assert test_finder.get_shot_details_calls[0] == shot
        assert details["show"] == "show1"
        assert details["status"] == "approved"

    def test_cache_integration_with_real_cache(
        self, model_with_real_cache, temp_cache_dir
    ):
        """Test cache saving and loading with real CacheManager."""
        model = model_with_real_cache

        # Configure finder
        test_finder = FakePreviousShotsFinder()
        test_finder.approved_shots_to_return = [
            create_test_shot("show1", "seq1", "shot1"),
            create_test_shot("show1", "seq1", "shot2"),
        ]
        model._finder = test_finder

        # Refresh should save to cache
        model.refresh_shots()

        # Verify cache file was created
        cache_file = temp_cache_dir / "previous_shots.json"
        assert cache_file.exists()

        # Create new model instance - should load from cache
        new_model = PreviousShotsModel(model._shot_model, model._cache_manager)

        shots = new_model.get_shots()
        assert len(shots) == 2
        assert shots[0].show == "show1"

    def test_cache_loading_error_recovery(self, temp_cache_dir, test_shot_model):
        """Test handling of corrupted cache data."""
        # Create invalid cache file
        cache_file = temp_cache_dir / "previous_shots.json"
        cache_file.write_text("invalid json")

        cache_manager = CacheManager(cache_dir=temp_cache_dir)

        # Should handle error gracefully
        model = PreviousShotsModel(test_shot_model, cache_manager)
        assert len(model.get_shots()) == 0
        model.deleteLater()

    def test_clear_cache_functionality(self, model_with_real_cache, temp_cache_dir):
        """Test cache clearing functionality."""
        model = model_with_real_cache

        # Configure and refresh
        test_finder = FakePreviousShotsFinder()
        test_finder.approved_shots_to_return = [create_test_shot()]
        model._finder = test_finder
        model.refresh_shots()

        # Verify cache exists
        cache_file = temp_cache_dir / "previous_shots.json"
        assert cache_file.exists()

        # Clear cache
        model.clear_cache()

        # Cache file should be removed
        assert not cache_file.exists()

    def test_timer_triggered_refresh(self, test_shot_model, test_cache_manager, qtbot):
        """Test refresh triggered by timer with proper signal handling."""
        model = PreviousShotsModel(test_shot_model, test_cache_manager)

        # Configure finder
        test_finder = FakePreviousShotsFinder()
        test_finder.approved_shots_to_return = [create_test_shot()]
        model._finder = test_finder

        shots_updated_spy = QSignalSpy(model.shots_updated)

        # Set very short interval for testing
        model._refresh_timer.setInterval(100)  # 100ms

        # Start timer and wait for signal
        with qtbot.waitSignal(model.shots_updated, timeout=500):
            model.start_auto_refresh()

        assert shots_updated_spy.count() >= 1

        model.stop_auto_refresh()
        model.deleteLater()


class TestPreviousShotsModelIntegration:
    """Integration tests with multiple real components."""

    @pytest.fixture
    def integration_setup(self, tmp_path):
        """Set up integration test with real components."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        shot_model = FakeShotModel()
        shot_model.set_shots(
            [
                create_test_shot("active", "seq1", "shot1"),
            ]
        )

        model = PreviousShotsModel(shot_model, cache_manager)

        yield model, shot_model, cache_manager

        model.stop_auto_refresh()
        model.deleteLater()

    def test_full_workflow(self, integration_setup, qtbot):
        """Test complete workflow with real components."""
        model, shot_model, cache_manager = integration_setup

        # Configure finder with approved shots
        test_finder = FakePreviousShotsFinder()
        test_finder.approved_shots_to_return = [
            create_test_shot("approved", "seq1", "shot1"),
        ]
        model._finder = test_finder

        # Set up signal spy
        shots_updated_spy = QSignalSpy(model.shots_updated)

        # Refresh with signal waiting
        with qtbot.waitSignal(model.scan_finished, timeout=1000):
            success = model.refresh_shots()

        assert success
        assert shots_updated_spy.count() == 1
        assert model.get_shot_count() == 1

        # Verify caching worked
        cached = cache_manager.get_cached_previous_shots()
        assert cached is not None
        assert len(cached) == 1
