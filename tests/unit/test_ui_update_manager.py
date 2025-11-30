#!/usr/bin/env python3
"""
Unit tests for UIUpdateManager class
Tests UI update batching, adaptive timers, and dirty marking
"""

import time
from unittest.mock import patch

import pytest

from ui_update_manager import UIUpdateManager


@pytest.fixture
def qtapp(qapp):
    """Use the qapp fixture from conftest for Qt app context"""
    return qapp


class TestUIUpdateManager:
    """Test suite for UIUpdateManager class"""

    def setup_method(self, qtapp):
        """Create UIUpdateManager instance for each test"""
        self.manager = UIUpdateManager()
        # Connect to signal to capture emitted updates
        self.emitted_updates = []
        self.manager.update_ui.connect(
            lambda updates: self.emitted_updates.append(updates)
        )

    def test_init(self):
        """Test manager initialization"""
        assert hasattr(self.manager, "dirty_flags")
        assert hasattr(self.manager, "pending_updates")
        assert hasattr(self.manager, "update_timer")
        assert self.manager.base_interval == 100
        assert self.manager.current_interval == 100

    def test_mark_dirty(self):
        """Test marking components as dirty"""
        test_data = {"progress": 50}

        self.manager.mark_dirty("progress_bar", test_data)

        assert self.manager.dirty_flags["progress_bar"] is True
        assert self.manager.pending_updates["progress_bar"] == test_data

    def test_mark_dirty_without_data(self):
        """Test marking dirty without data"""
        self.manager.mark_dirty("status_label")

        assert self.manager.dirty_flags["status_label"] is True
        assert "status_label" not in self.manager.pending_updates

    def test_is_dirty(self):
        """Test checking if component is dirty"""
        assert self.manager.is_dirty("progress_bar") is False

        self.manager.mark_dirty("progress_bar")
        assert self.manager.is_dirty("progress_bar") is True

    def test_process_updates_emits_signal(self):
        """Test that process updates emits signal with dirty components"""
        self.manager.mark_dirty("progress_bar", {"value": 75})
        self.manager.mark_dirty("status_label", {"text": "Running"})

        # Force immediate processing
        self.manager.last_frame_time = 0
        self.manager._process_updates()

        assert len(self.emitted_updates) == 1
        updates = self.emitted_updates[0]
        assert "progress_bar" in updates
        assert "status_label" in updates
        assert updates["progress_bar"] == {"value": 75}

    def test_process_updates_clears_dirty_flags(self):
        """Test that processing clears dirty flags"""
        self.manager.mark_dirty("progress_bar", {"value": 50})

        # Force processing
        self.manager.last_frame_time = 0
        self.manager._process_updates()

        assert self.manager.dirty_flags["progress_bar"] is False
        assert "progress_bar" not in self.manager.pending_updates

    def test_frame_time_throttling(self):
        """Test that updates respect frame time throttling"""
        self.manager.mark_dirty("progress_bar", {"value": 50})

        # Set last frame time to very recent
        self.manager.last_frame_time = time.time() - 0.001  # 1ms ago
        self.manager._process_updates()

        # Should not emit due to frame time throttling
        assert len(self.emitted_updates) == 0
        assert self.manager.dirty_flags["progress_bar"] is True  # Still dirty

    def test_component_priorities(self):
        """Test that components are processed by priority"""
        # Mark multiple components dirty
        self.manager.mark_dirty("log_display", {"text": "log"})
        self.manager.mark_dirty("progress_bar", {"value": 50})
        self.manager.mark_dirty("eta_display", {"eta": "5:00"})

        # Process should respect priorities
        self.manager.last_frame_time = 0
        self.manager._process_updates()

        # All should be processed in one batch
        assert len(self.emitted_updates) == 1
        updates = self.emitted_updates[0]
        assert "progress_bar" in updates  # Priority 1
        assert "eta_display" in updates  # Priority 4
        assert "log_display" in updates  # Priority 5

    def test_component_interval_throttling(self):
        """Test component-specific update intervals"""
        # Mark progress_bar dirty twice quickly
        self.manager.mark_dirty("progress_bar", {"value": 50})
        self.manager.last_frame_time = 0
        self.manager._process_updates()

        # Clear emitted updates
        self.emitted_updates.clear()

        # Mark dirty again immediately
        self.manager.mark_dirty("progress_bar", {"value": 60})
        self.manager.last_frame_time = 0
        self.manager._process_updates()

        # Should not update due to component interval (100ms)
        assert len(self.emitted_updates) == 0

    def test_adjust_update_interval(self):
        """Test adaptive timer interval adjustment"""
        # High activity - many dirty flags
        for i in range(10):
            self.manager.mark_dirty(f"component_{i}")

        self.manager._adjust_update_interval()

        # Should use minimum interval for high activity
        assert self.manager.current_interval == self.manager.min_interval

    def test_adjust_update_interval_low_activity(self):
        """Test timer slows down with low activity"""
        # Simulate low activity
        self.manager.last_activity_time = time.time() - 5  # 5 seconds ago
        self.manager.dirty_flags.clear()  # No dirty components

        self.manager._adjust_update_interval()

        # Should use maximum interval for low activity
        assert self.manager.current_interval == self.manager.max_interval

    def test_batch_update(self):
        """Test batch updating multiple components"""
        updates = {
            "progress_bar": {"value": 80},
            "status_label": {"text": "Processing"},
            "fps_display": {"fps": 30},
        }

        self.manager.batch_update(updates)

        assert self.manager.dirty_flags["progress_bar"] is True
        assert self.manager.dirty_flags["status_label"] is True
        assert self.manager.dirty_flags["fps_display"] is True
        assert self.manager.pending_updates["progress_bar"] == {"value": 80}

    def test_force_update_specific_component(self):
        """Test forcing update of specific component"""
        self.manager.mark_dirty("progress_bar", {"value": 90})

        # Set last update time to recent (would normally throttle)
        self.manager.last_update_time["progress_bar"] = time.time()

        # Force update
        self.manager.force_update("progress_bar")

        assert len(self.emitted_updates) == 1
        assert "progress_bar" in self.emitted_updates[0]

    def test_force_update_all(self):
        """Test forcing update of all dirty components"""
        self.manager.mark_dirty("progress_bar", {"value": 100})
        self.manager.mark_dirty("status_label", {"text": "Done"})

        # Set recent update times
        current_time = time.time()
        self.manager.last_update_time["progress_bar"] = current_time
        self.manager.last_update_time["status_label"] = current_time

        # Force all
        self.manager.force_update()

        assert len(self.emitted_updates) == 1
        updates = self.emitted_updates[0]
        assert "progress_bar" in updates
        assert "status_label" in updates

    def test_get_update_stats(self):
        """Test getting update statistics"""
        self.manager.mark_dirty("progress_bar")
        self.manager.last_update_time["progress_bar"] = time.time() - 2  # 2 seconds ago

        stats = self.manager.get_update_stats()

        assert "progress_bar" in stats
        assert stats["progress_bar"]["is_dirty"] is True
        assert stats["progress_bar"]["min_interval"] == 0.1
        assert 1.9 < stats["progress_bar"]["last_update_ago"] < 2.1

    def test_timer_start_stop(self):
        """Test timer lifecycle"""
        with patch.object(self.manager.update_timer, "start") as mock_start, \
                patch.object(self.manager.update_timer, "stop") as mock_stop:
            self.manager.start()
            mock_start.assert_called_once_with(self.manager.current_interval)

            self.manager.stop()
            mock_stop.assert_called_once()

    def test_timer_interval_change(self):
        """Test that timer interval is updated when activity changes"""
        with patch.object(self.manager.update_timer, "isActive", return_value=True), \
                patch.object(self.manager.update_timer, "setInterval") as mock_set:
            # Start with base interval
            assert self.manager.current_interval == self.manager.base_interval

            # Create high activity
            for i in range(10):
                self.manager.mark_dirty(f"component_{i}")

            self.manager._adjust_update_interval()

            # Should change to minimum interval
            assert self.manager.current_interval == self.manager.min_interval
            mock_set.assert_called_with(self.manager.min_interval)


class TestSmartBufferMode:
    """Test smart buffer mode for performance optimization"""

    def setup_method(self):
        """Create UIUpdateManager instance for each test"""
        self.manager = UIUpdateManager()

    def test_smart_buffer_disabled_by_default(self):
        """Test that smart buffer is disabled by default"""
        assert self.manager.smart_buffer_enabled is False
        assert self.manager.base_interval == 100
        assert self.manager.max_interval == 1000

    def test_enable_smart_buffer(self):
        """Test enabling smart buffer mode increases intervals"""
        self.manager.set_smart_buffer(True)

        assert self.manager.smart_buffer_enabled is True
        assert self.manager.base_interval == 200  # Doubled
        assert self.manager.max_interval == 2000  # Doubled

    def test_disable_smart_buffer(self):
        """Test disabling smart buffer mode restores intervals"""
        # Enable first
        self.manager.set_smart_buffer(True)
        assert self.manager.base_interval == 200

        # Then disable
        self.manager.set_smart_buffer(False)

        assert self.manager.smart_buffer_enabled is False
        assert self.manager.base_interval == 100
        assert self.manager.max_interval == 1000

    def test_smart_buffer_toggle_triggers_adjustment(self):
        """Test that toggling smart buffer triggers interval adjustment"""
        with patch.object(self.manager, "_adjust_update_interval") as mock_adjust:
            self.manager.set_smart_buffer(True)
            mock_adjust.assert_called_once()

            mock_adjust.reset_mock()
            self.manager.set_smart_buffer(False)
            mock_adjust.assert_called_once()

    def test_smart_buffer_affects_low_activity_interval(self):
        """Test smart buffer affects the low activity interval"""
        # Simulate low activity
        self.manager.last_activity_time = time.time() - 5
        self.manager.dirty_flags.clear()

        # Without smart buffer
        self.manager.set_smart_buffer(False)
        self.manager._adjust_update_interval()
        normal_interval = self.manager.current_interval

        # With smart buffer
        self.manager.set_smart_buffer(True)
        self.manager._adjust_update_interval()
        smart_interval = self.manager.current_interval

        assert smart_interval > normal_interval

    def test_smart_buffer_preserves_high_activity_behavior(self):
        """Test smart buffer doesn't affect minimum interval during high activity"""
        # Create high activity
        for i in range(10):
            self.manager.mark_dirty(f"component_{i}")

        # With smart buffer enabled
        self.manager.set_smart_buffer(True)
        self.manager._adjust_update_interval()

        # Should still use min_interval for responsiveness
        assert self.manager.current_interval == self.manager.min_interval


class TestUIUpdateManagerEdgeCases:
    """Test edge cases and error conditions"""

    def setup_method(self):
        """Create UIUpdateManager instance for each test"""
        self.manager = UIUpdateManager()

    def test_empty_updates_not_emitted(self):
        """Test that no signal is emitted when nothing is dirty"""
        emitted = []
        self.manager.update_ui.connect(lambda u: emitted.append(u))

        # Process with nothing dirty
        self.manager.last_frame_time = 0
        self.manager._process_updates()

        assert len(emitted) == 0

    def test_mark_dirty_updates_activity_time(self):
        """Test that marking dirty updates the activity timestamp"""
        old_time = self.manager.last_activity_time

        time.sleep(0.01)  # Small delay
        self.manager.mark_dirty("test_component")

        assert self.manager.last_activity_time > old_time

    def test_unknown_component_priority(self):
        """Test unknown components get default priority"""
        self.manager.mark_dirty("unknown_component_xyz", {"data": "test"})

        # Should not crash and component should be marked dirty
        assert self.manager.dirty_flags["unknown_component_xyz"] is True

        # Force process
        self.manager.last_frame_time = 0
        self.manager._process_updates()

        # Should be cleared after processing
        assert self.manager.dirty_flags["unknown_component_xyz"] is False

    def test_update_stats_empty_component(self):
        """Test update stats for component that was never updated"""
        self.manager.mark_dirty("new_component")

        stats = self.manager.get_update_stats()

        assert "new_component" in stats
        assert stats["new_component"]["last_update_ago"] == -1  # Never updated

    def test_force_update_non_dirty_component(self):
        """Test forcing update on non-dirty component does nothing"""
        emitted = []
        self.manager.update_ui.connect(lambda u: emitted.append(u))

        self.manager.force_update("non_existent_component")

        assert len(emitted) == 0

    def test_batch_update_empty_dict(self):
        """Test batch update with empty dictionary"""
        self.manager.batch_update({})

        assert len(self.manager.dirty_flags) == 0
        assert len(self.manager.pending_updates) == 0

    def test_get_component_interval_unknown(self):
        """Test getting interval for unknown component returns default"""
        interval = self.manager._get_component_interval("unknown_xyz")
        assert interval == 1.0  # Default interval

    def test_get_component_interval_known(self):
        """Test getting interval for known components"""
        assert self.manager._get_component_interval("progress_bar") == 0.1
        assert self.manager._get_component_interval("fps_display") == 0.5
        assert self.manager._get_component_interval("eta_display") == 1.0


class TestUIUpdateManagerConcurrency:
    """Test thread safety and concurrent access patterns"""

    def setup_method(self):
        """Create UIUpdateManager instance for each test"""
        self.manager = UIUpdateManager()

    def test_rapid_dirty_marking(self):
        """Test rapid marking of components as dirty"""
        # Simulate rapid updates
        for i in range(100):
            self.manager.mark_dirty("progress_bar", {"value": i})

        # Should have last value
        assert self.manager.pending_updates["progress_bar"] == {"value": 99}
        assert self.manager.dirty_flags["progress_bar"] is True

    def test_interleaved_mark_and_process(self):
        """Test interleaved marking and processing"""
        emitted = []
        self.manager.update_ui.connect(lambda u: emitted.append(u.copy()))

        for i in range(5):
            self.manager.mark_dirty("progress_bar", {"value": i * 20})
            self.manager.last_frame_time = 0
            self.manager.last_update_time["progress_bar"] = 0
            self.manager._process_updates()

        # Should have emitted multiple updates
        assert len(emitted) == 5
        # Last update should have value 80
        assert emitted[-1]["progress_bar"]["value"] == 80
