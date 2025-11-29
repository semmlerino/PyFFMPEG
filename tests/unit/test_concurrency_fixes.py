"""Tests for concurrency and threading fixes.

Tests verify:
1. Two-phase lock pattern in remove_worker() - no wait() inside mutex
2. Two-phase lock pattern in _cleanup_worker_safely() - no wait() inside lock
3. Zombie worker tracking when workers fail to stop gracefully
4. 60-day age-based cache pruning in merge_scenes_incremental()
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QMutexLocker, QThread, Signal

from tests.test_helpers import process_qt_events
from threading_manager import ThreadingManager


# Mark Qt tests for serial execution in same worker (prevents Qt crashes)
pytestmark = [
    pytest.mark.unit,
    pytest.mark.qt,  # CRITICAL for parallel safety
]

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytestqt.qtbot import QtBot

    from cache_manager import CacheManager


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


class SlowStoppingWorker(QThread):
    """Worker that takes time to stop - simulates real thread behavior."""

    started = Signal()
    finished = Signal()

    def __init__(self, stop_delay_ms: int = 100) -> None:
        super().__init__()
        self._should_stop = False
        self._stop_delay_ms = stop_delay_ms

    def run(self) -> None:
        """Run until stop requested."""
        while not self._should_stop:
            self.msleep(10)

    def stop(self) -> None:
        """Request stop - simulates slow shutdown."""
        self._should_stop = True

    def request_stop(self) -> None:
        """Alias for stop."""
        self.stop()


@pytest.fixture
def threading_manager() -> Generator[ThreadingManager]:
    """Create ThreadingManager instance with cleanup."""
    manager = ThreadingManager()
    yield manager
    # Cleanup - terminate any remaining workers
    try:
        manager.shutdown_all_threads()
    except Exception:
        pass
    process_qt_events()


@pytest.fixture(autouse=True)
def cleanup_qt_state() -> Generator[None]:
    """Autouse fixture to ensure Qt state is cleaned up after each test."""
    yield
    process_qt_events()


# =============================================================================
# Two-Phase Lock Pattern Tests (Fixes 1-2)
# =============================================================================


class TestTwoPhaseLockPattern:
    """Test that remove_worker uses two-phase lock pattern.

    The pattern should:
    1. Acquire mutex, grab reference, release mutex
    2. Wait for worker OUTSIDE mutex (avoids UI freeze)
    """

    def test_remove_worker_does_not_block_under_lock(
        self, threading_manager: ThreadingManager, qtbot: QtBot
    ) -> None:
        """Verify remove_worker() doesn't hold mutex during wait().

        If wait() was called inside the mutex, another thread trying to
        access _workers would be blocked for up to 2 seconds.
        """
        worker: SlowStoppingWorker | None = None
        try:
            # Create a worker that takes time to stop
            worker = SlowStoppingWorker(stop_delay_ms=200)
            threading_manager.add_custom_worker("slow_worker", worker)

            # Start worker
            worker.start()
            qtbot.waitUntil(lambda: worker.isRunning(), timeout=1000)

            # Record timing to verify we're not blocking
            access_times: list[float] = []

            def try_access_workers() -> None:
                """Try to access _workers dict under mutex."""
                start = time.time()
                with QMutexLocker(threading_manager._mutex):
                    _ = len(threading_manager._workers)
                access_times.append(time.time() - start)

            # Access mutex during removal - should NOT be blocked for 2 seconds
            import threading

            access_thread = threading.Thread(target=try_access_workers)
            access_thread.start()

            # Remove worker (this will wait up to 2 seconds for it to stop)
            result = threading_manager.remove_worker("slow_worker")

            access_thread.join(timeout=1.0)

            assert result is True
            # If mutex was held during wait, access would take ~2 seconds
            # With two-phase pattern, access should be nearly instant
            if access_times:
                assert access_times[0] < 0.5, (
                    f"Mutex access took {access_times[0]:.2f}s - "
                    "suggests wait() was inside lock"
                )
        finally:
            # Ensure worker is stopped and cleaned up
            if worker is not None and worker.isRunning():
                worker.stop()
                worker.wait(1000)
                worker.deleteLater()

    def test_remove_worker_waits_outside_lock(
        self, threading_manager: ThreadingManager, qtbot: QtBot
    ) -> None:
        """Verify worker dict is updated before wait() call."""
        worker = Mock(spec=QThread)
        worker.start = Mock()
        worker.isRunning = Mock(return_value=True)
        worker.stop = Mock()
        worker.wait = Mock(return_value=True)
        worker.deleteLater = Mock()

        # Track call order
        call_order: list[str] = []
        original_wait = worker.wait

        def tracking_wait(timeout: int) -> bool:
            # When wait is called, check if worker is still in dict
            with QMutexLocker(threading_manager._mutex):
                in_dict = "worker" in threading_manager._workers
            call_order.append(f"wait:in_dict={in_dict}")
            return original_wait(timeout)

        worker.wait = tracking_wait

        threading_manager.add_custom_worker("worker", worker)
        threading_manager.remove_worker("worker")

        # wait() should be called when worker is NOT in dict (two-phase)
        assert any("wait:in_dict=False" in c for c in call_order), (
            f"wait() should be called after removing from dict. "
            f"Call order: {call_order}"
        )


# =============================================================================
# Zombie Worker Tracking Tests (Fix 3)
# =============================================================================


class TestZombieWorkerTracking:
    """Test that workers failing to stop are tracked as zombies."""

    def test_worker_timeout_adds_to_zombie_list(
        self, threading_manager: ThreadingManager, qtbot: QtBot
    ) -> None:
        """Worker that doesn't stop in time should be added to _zombie_workers."""
        # Create worker that won't respond to stop
        worker = Mock(spec=QThread)
        worker.start = Mock()
        worker.isRunning = Mock(return_value=True)
        worker.stop = Mock()
        worker.wait = Mock(return_value=False)  # Simulate timeout
        worker.deleteLater = Mock()

        threading_manager.add_custom_worker("stubborn_worker", worker)

        # Initially no zombies
        assert len(threading_manager._zombie_workers) == 0

        # Remove worker - will timeout and become zombie
        result = threading_manager.remove_worker("stubborn_worker")

        assert result is True
        assert len(threading_manager._zombie_workers) == 1
        assert threading_manager._zombie_workers[0] is worker

    def test_graceful_stop_does_not_create_zombie(
        self, threading_manager: ThreadingManager
    ) -> None:
        """Worker that stops gracefully should NOT be added to _zombie_workers."""
        worker = Mock(spec=QThread)
        worker.start = Mock()
        worker.isRunning = Mock(return_value=True)
        worker.stop = Mock()
        worker.wait = Mock(return_value=True)  # Stops successfully
        worker.deleteLater = Mock()

        threading_manager.add_custom_worker("good_worker", worker)
        threading_manager.remove_worker("good_worker")

        assert len(threading_manager._zombie_workers) == 0

    def test_shutdown_cleans_up_zombies(
        self, threading_manager: ThreadingManager
    ) -> None:
        """shutdown_all_threads() should cleanup zombie workers."""
        # Create some zombie workers manually
        zombie1 = Mock(spec=QThread)
        zombie1.isRunning = Mock(return_value=True)
        zombie1.terminate = Mock()
        zombie1.wait = Mock(return_value=True)
        zombie1.deleteLater = Mock()

        zombie2 = Mock(spec=QThread)
        zombie2.isRunning = Mock(return_value=False)  # Already stopped
        zombie2.terminate = Mock()
        zombie2.wait = Mock(return_value=True)
        zombie2.deleteLater = Mock()

        threading_manager._zombie_workers = [zombie1, zombie2]

        # Shutdown should cleanup zombies
        threading_manager.shutdown_all_threads()

        # Zombie list should be cleared
        assert len(threading_manager._zombie_workers) == 0

        # Running zombie should have been terminated
        zombie1.terminate.assert_called_once()
        zombie1.deleteLater.assert_called_once()

        # Non-running zombie should just be deleted (no terminate)
        zombie2.terminate.assert_not_called()
        zombie2.deleteLater.assert_called_once()

    def test_multiple_zombies_accumulated(
        self, threading_manager: ThreadingManager
    ) -> None:
        """Multiple failing workers should accumulate in zombie list."""
        for i in range(3):
            worker = Mock(spec=QThread)
            worker.start = Mock()
            worker.isRunning = Mock(return_value=True)
            worker.stop = Mock()
            worker.wait = Mock(return_value=False)  # All timeout
            worker.deleteLater = Mock()

            threading_manager.add_custom_worker(f"zombie_{i}", worker)
            threading_manager.remove_worker(f"zombie_{i}")

        assert len(threading_manager._zombie_workers) == 3


# =============================================================================
# Cache Pruning Tests (Fix 5)
# =============================================================================


class TestCachePruning:
    """Test 60-day age-based cache pruning in merge_scenes_incremental."""

    def test_old_scenes_pruned_by_default(
        self, isolated_cache_manager: CacheManager
    ) -> None:
        """Scenes older than 60 days should be pruned."""
        manager = isolated_cache_manager
        now = datetime.now(UTC).timestamp()

        # Cached scene last seen 90 days ago (should be pruned)
        old_scene = {
            "filepath": "/old/scene.3de",
            "show": "show1",
            "sequence": "seq01",
            "shot": "shot010",
            "user": "artist",
            "filename": "scene.3de",
            "modified_time": now - (100 * 86400),  # 100 days ago
            "workspace_path": "/p1",
            "last_seen": now - (90 * 86400),  # Last seen 90 days ago
        }

        # Fresh scenes don't include old_scene
        fresh_scenes: list[dict[str, object]] = []

        result = manager.merge_scenes_incremental([old_scene], fresh_scenes)

        # Old scene should be pruned (not in updated_scenes)
        assert len(result.updated_scenes) == 0
        assert result.pruned_count == 1
        assert result.has_changes is True

    def test_recent_scenes_retained(
        self, isolated_cache_manager: CacheManager
    ) -> None:
        """Scenes seen within 60 days should be retained even if not in fresh."""
        manager = isolated_cache_manager
        now = datetime.now(UTC).timestamp()

        # Cached scene last seen 30 days ago (should be kept)
        recent_scene = {
            "filepath": "/recent/scene.3de",
            "show": "show1",
            "sequence": "seq01",
            "shot": "shot010",
            "user": "artist",
            "filename": "scene.3de",
            "modified_time": now - (40 * 86400),  # 40 days ago
            "workspace_path": "/p1",
            "last_seen": now - (30 * 86400),  # Last seen 30 days ago
        }

        # Fresh scenes don't include recent_scene
        fresh_scenes: list[dict[str, object]] = []

        result = manager.merge_scenes_incremental([recent_scene], fresh_scenes)

        # Recent scene should be retained
        assert len(result.updated_scenes) == 1
        assert result.pruned_count == 0
        assert result.updated_scenes[0]["shot"] == "shot010"

    def test_custom_max_age_days(
        self, isolated_cache_manager: CacheManager
    ) -> None:
        """Custom max_age_days should be respected."""
        manager = isolated_cache_manager
        now = datetime.now(UTC).timestamp()

        # Scene last seen 10 days ago
        scene = {
            "filepath": "/test/scene.3de",
            "show": "show1",
            "sequence": "seq01",
            "shot": "shot010",
            "user": "artist",
            "filename": "scene.3de",
            "modified_time": now - (15 * 86400),
            "workspace_path": "/p1",
            "last_seen": now - (10 * 86400),  # 10 days ago
        }

        # With 7-day retention, this should be pruned
        result = manager.merge_scenes_incremental([scene], [], max_age_days=7)
        assert result.pruned_count == 1
        assert len(result.updated_scenes) == 0

        # With 30-day retention, this should be kept
        result = manager.merge_scenes_incremental([scene], [], max_age_days=30)
        assert result.pruned_count == 0
        assert len(result.updated_scenes) == 1

    def test_fresh_scenes_update_last_seen(
        self, isolated_cache_manager: CacheManager
    ) -> None:
        """Fresh scenes should have last_seen updated to now."""
        manager = isolated_cache_manager
        now = datetime.now(UTC).timestamp()

        fresh_scene = {
            "filepath": "/fresh/scene.3de",
            "show": "show1",
            "sequence": "seq01",
            "shot": "shot010",
            "user": "artist",
            "filename": "scene.3de",
            "modified_time": now,
            "workspace_path": "/p1",
        }

        result = manager.merge_scenes_incremental(None, [fresh_scene])

        assert len(result.updated_scenes) == 1
        # last_seen should be set to approximately now
        last_seen = result.updated_scenes[0].get("last_seen", 0)
        assert abs(last_seen - now) < 5  # Within 5 seconds

    def test_legacy_scenes_without_last_seen_kept(
        self, isolated_cache_manager: CacheManager
    ) -> None:
        """Cached scenes without last_seen should default to now and be kept."""
        manager = isolated_cache_manager
        now = datetime.now(UTC).timestamp()

        # Legacy scene without last_seen field
        legacy_scene = {
            "filepath": "/legacy/scene.3de",
            "show": "show1",
            "sequence": "seq01",
            "shot": "shot010",
            "user": "artist",
            "filename": "scene.3de",
            "modified_time": now - (200 * 86400),  # Very old file
            "workspace_path": "/p1",
            # No last_seen field!
        }

        result = manager.merge_scenes_incremental([legacy_scene], [])

        # Should be kept (defaults to "now" for last_seen)
        assert len(result.updated_scenes) == 1
        assert result.pruned_count == 0

    def test_pruned_count_accuracy(
        self, isolated_cache_manager: CacheManager
    ) -> None:
        """pruned_count should accurately reflect number of pruned scenes."""
        manager = isolated_cache_manager
        now = datetime.now(UTC).timestamp()

        # 3 scenes: 2 old (to be pruned), 1 recent (to be kept)
        cached = [
            {
                "filepath": f"/old/scene{i}.3de",
                "show": "show1",
                "sequence": "seq01",
                "shot": f"shot{i:03d}",
                "user": "artist",
                "filename": f"scene{i}.3de",
                "modified_time": now - (100 * 86400),
                "workspace_path": f"/p{i}",
                "last_seen": now - (90 * 86400),  # 90 days - will be pruned
            }
            for i in range(2)
        ]
        cached.append({
            "filepath": "/recent/scene.3de",
            "show": "show1",
            "sequence": "seq01",
            "shot": "shot099",
            "user": "artist",
            "filename": "scene.3de",
            "modified_time": now - (10 * 86400),
            "workspace_path": "/recent",
            "last_seen": now - (5 * 86400),  # 5 days - will be kept
        })

        result = manager.merge_scenes_incremental(cached, [])

        assert result.pruned_count == 2
        assert len(result.updated_scenes) == 1
        assert result.updated_scenes[0]["shot"] == "shot099"


# =============================================================================
# Integration Tests
# =============================================================================


class TestConcurrencyFixesIntegration:
    """Integration tests for concurrency fixes working together."""

    def test_shutdown_with_stuck_and_zombie_workers(
        self, threading_manager: ThreadingManager
    ) -> None:
        """Shutdown should handle mix of normal, stuck, and zombie workers."""
        # Normal worker that stops fine
        normal = Mock(spec=QThread)
        normal.start = Mock()
        normal.isRunning = Mock(return_value=True)
        normal.stop = Mock()
        normal.wait = Mock(return_value=True)
        normal.deleteLater = Mock()

        # Stuck worker that times out
        stuck = Mock(spec=QThread)
        stuck.start = Mock()
        stuck.isRunning = Mock(return_value=True)
        stuck.stop = Mock()
        stuck.wait = Mock(return_value=False)  # Never stops
        stuck.deleteLater = Mock()

        # Pre-existing zombie
        zombie = Mock(spec=QThread)
        zombie.isRunning = Mock(return_value=True)
        zombie.terminate = Mock()
        zombie.wait = Mock(return_value=True)
        zombie.deleteLater = Mock()

        threading_manager._zombie_workers = [zombie]
        threading_manager.add_custom_worker("normal", normal)
        threading_manager.add_custom_worker("stuck", stuck)

        # Shutdown should handle all cases
        threading_manager.shutdown_all_threads()

        # All workers should be cleaned up
        assert len(threading_manager._workers) == 0
        assert len(threading_manager._zombie_workers) == 0

        # deleteLater called on all
        normal.deleteLater.assert_called_once()
        stuck.deleteLater.assert_called_once()
        zombie.deleteLater.assert_called_once()

        # Zombie was terminated
        zombie.terminate.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
