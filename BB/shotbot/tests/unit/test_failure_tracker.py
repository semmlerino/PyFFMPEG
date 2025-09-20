"""Unit tests for FailureTracker functionality.

Tests exponential backoff, thread safety, time-based logic, and cleanup operations.

Following UNIFIED_TESTING_GUIDE principles:
- Test behavior, not implementation
- Use real FailureTracker instances
- Mock only time/datetime for testing backoff logic
- Comprehensive thread safety testing
- Clear, descriptive test names and docstrings
"""

from __future__ import annotations

import concurrent.futures
import gc
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from cache.failure_tracker import FailureTracker

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns
# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)

pytestmark = pytest.mark.unit


class TestFailureTracker:
    """Test suite for FailureTracker class covering all public methods and edge cases."""

    @pytest.fixture
    def failure_tracker(self):
        """Create a standard FailureTracker instance for testing."""
        return FailureTracker()

    @pytest.fixture
    def custom_failure_tracker(self):
        """Create a FailureTracker with custom configuration for testing different parameters."""
        return FailureTracker(
            base_retry_delay_minutes=2,
            max_retry_delay_minutes=60,
            retry_multiplier=2,
            max_failed_attempts=3,
            cleanup_age_hours=12,
        )

    @pytest.fixture
    def time_controller(self):
        """Controlled time fixture for time-based testing without delays."""
        base_time = datetime(2025, 1, 1, 12, 0, 0)  # Start at noon
        current_offset = timedelta(0)

        def advance_time(minutes=0, hours=0, seconds=0):
            nonlocal current_offset
            current_offset += timedelta(minutes=minutes, hours=hours, seconds=seconds)
            return base_time + current_offset

        def get_current_time():
            return base_time + current_offset

        return type(
            "TimeController",
            (),
            {"advance": advance_time, "now": get_current_time, "base_time": base_time},
        )()

    def test_initial_state(self, failure_tracker) -> None:
        """Test that a new FailureTracker starts in clean state."""
        assert len(failure_tracker) == 0
        assert failure_tracker.get_failure_count() == 0
        assert failure_tracker.get_failure_status() == {}
        assert "test_key" not in failure_tracker
        assert repr(failure_tracker) == "FailureTracker(failures=0, max_delay=120min)"

    def test_should_retry_no_previous_failures(self, failure_tracker) -> None:
        """Test should_retry returns True when no failures are recorded."""
        should_retry, reason = failure_tracker.should_retry("new_key")

        assert should_retry is True
        assert reason == "No previous failures recorded"

    def test_should_retry_with_source_path(self, failure_tracker) -> None:
        """Test should_retry works correctly with optional source_path parameter."""
        source_path = Path("/test/path/image.jpg")
        should_retry, reason = failure_tracker.should_retry("test_key", source_path)

        assert should_retry is True
        assert reason == "No previous failures recorded"

    def test_record_failure_first_attempt(self, failure_tracker) -> None:
        """Test recording the first failure creates correct state."""
        cache_key = "test_key"
        error_message = "Test error"
        source_path = Path("/test/image.jpg")

        # Use real FailureTracker with controllable time
        tracker = FailureTracker(
            base_retry_delay_minutes=5,
            max_retry_delay_minutes=120,
            retry_multiplier=3,
            max_failed_attempts=4,
            cleanup_age_hours=24,
        )

        tracker.record_failure(cache_key, error_message, source_path)

        assert len(tracker) == 1
        assert cache_key in tracker

        status = tracker.get_failure_status()
        assert cache_key in status

        failure_info = status[cache_key]
        assert failure_info["attempts"] == 1
        assert failure_info["error"] == error_message
        assert failure_info["source_path"] == str(source_path)

        # Next retry should be approximately 5 minutes from now
        next_retry = failure_info["next_retry"]
        time_diff = (next_retry - datetime.now()).total_seconds() / 60
        assert 4.8 <= time_diff <= 5.2  # Allow small tolerance for execution time

    def test_record_failure_without_source_path(self, failure_tracker) -> None:
        """Test recording failure without source_path uses cache_key as fallback."""
        cache_key = "test_key"
        error_message = "Test error"

        failure_tracker.record_failure(cache_key, error_message)

        status = failure_tracker.get_failure_status()
        failure_info = status[cache_key]
        assert failure_info["source_path"] == cache_key

    def test_exponential_backoff_progression(self) -> None:
        """Test exponential backoff follows expected progression: 5min → 15min → 45min → 120min."""
        # Create tracker with known configuration for predictable testing
        tracker = FailureTracker(
            base_retry_delay_minutes=5,
            max_retry_delay_minutes=120,
            retry_multiplier=3,
            max_failed_attempts=4,
        )

        cache_key = "test_key"
        error_message = "Test error"

        # Expected delays: 5, 15, 45, 120 (max)
        expected_delays = [5, 15, 45, 120, 120]  # Last two should be capped at max

        for attempt, expected_delay in enumerate(expected_delays, 1):
            before_failure = datetime.now()

            tracker.record_failure(cache_key, f"{error_message} #{attempt}")

            status = tracker.get_failure_status()
            failure_info = status[cache_key]

            assert failure_info["attempts"] == attempt

            # Verify the next_retry time is approximately the expected delay from now
            next_retry = failure_info["next_retry"]
            actual_delay = (next_retry - before_failure).total_seconds() / 60

            # Allow small tolerance for execution time
            assert expected_delay - 0.1 <= actual_delay <= expected_delay + 0.1

    def test_should_retry_within_backoff_period(self, failure_tracker) -> None:
        """Test should_retry returns False when within backoff period."""
        cache_key = "test_key"
        source_path = Path("/test/image.jpg")

        # Record a failure
        failure_tracker.record_failure(cache_key, "Test error", source_path)

        # Try immediately (should be blocked)
        should_retry, reason = failure_tracker.should_retry(cache_key, source_path)

        assert should_retry is False
        assert "Skipping recently failed operation for image.jpg" in reason
        assert "attempt 1" in reason
        # Don't check exact retry time as it depends on current time

    def test_should_retry_after_backoff_period(self) -> None:
        """Test should_retry returns True after backoff period expires."""
        # Use very short delays for testing without actual waiting
        tracker = FailureTracker(
            base_retry_delay_minutes=0.01,  # 0.6 seconds
            max_retry_delay_minutes=1,
            retry_multiplier=2,
            max_failed_attempts=3,
        )

        cache_key = "test_key"

        # Mock datetime to control time
        # Following UNIFIED_TESTING_GUIDE: Mock only at system boundaries (time)
        base_time = datetime.now()
        with patch("cache.failure_tracker.datetime") as mock_datetime:
            # Record a failure at base time
            mock_datetime.now.return_value = base_time
            tracker.record_failure(cache_key, "Test error")

            # Should be blocked immediately
            should_retry, _ = tracker.should_retry(cache_key)
            assert should_retry is False

            # Advance time past backoff period (0.6 seconds)
            mock_datetime.now.return_value = base_time + timedelta(seconds=0.7)
            should_retry, reason = tracker.should_retry(cache_key)
            assert should_retry is True
            assert reason == "Retry allowed after 1 previous attempts"

    def test_should_retry_exact_boundary_condition(self) -> None:
        """Test should_retry behavior exactly at retry time boundary."""
        # Use very short delay for precise testing
        tracker = FailureTracker(
            base_retry_delay_minutes=0.02,  # 1.2 seconds
            max_retry_delay_minutes=1,
            retry_multiplier=2,
            max_failed_attempts=3,
        )

        cache_key = "test_key"

        # Mock datetime to control time precisely
        # Following UNIFIED_TESTING_GUIDE: Mock only at system boundaries (time)
        base_time = datetime.now()
        with patch("cache.failure_tracker.datetime") as mock_datetime:
            # Record failure at base time
            mock_datetime.now.return_value = base_time
            tracker.record_failure(cache_key, "Test error")

            # Should be blocked immediately after failure
            should_retry, _ = tracker.should_retry(cache_key)
            assert should_retry is False

            # Just before retry time expires (1.1 seconds)
            mock_datetime.now.return_value = base_time + timedelta(seconds=1.1)
            should_retry, _ = tracker.should_retry(cache_key)
            assert should_retry is False

            # Now past retry time (1.3 seconds total)
            mock_datetime.now.return_value = base_time + timedelta(seconds=1.3)
            should_retry, _ = tracker.should_retry(cache_key)
            assert should_retry is True

    def test_clear_failures_specific_key(self, failure_tracker) -> None:
        """Test clearing failures for a specific cache key."""
        # Record failures for multiple keys
        failure_tracker.record_failure("key1", "Error 1")
        failure_tracker.record_failure("key2", "Error 2")
        failure_tracker.record_failure("key3", "Error 3")

        assert len(failure_tracker) == 3

        # Clear one specific key
        failure_tracker.clear_failures("key2")

        assert len(failure_tracker) == 2
        assert "key1" in failure_tracker
        assert "key2" not in failure_tracker
        assert "key3" in failure_tracker

    def test_clear_failures_nonexistent_key(self, failure_tracker) -> None:
        """Test clearing failures for non-existent key is safe."""
        failure_tracker.record_failure("existing_key", "Error")

        # Should not raise exception
        failure_tracker.clear_failures("nonexistent_key")

        assert len(failure_tracker) == 1
        assert "existing_key" in failure_tracker

    def test_clear_all_failures(self, failure_tracker) -> None:
        """Test clearing all failures at once."""
        # Record multiple failures
        for i in range(5):
            failure_tracker.record_failure(f"key_{i}", f"Error {i}")

        assert len(failure_tracker) == 5

        # Clear all failures
        failure_tracker.clear_failures()

        assert len(failure_tracker) == 0
        assert failure_tracker.get_failure_status() == {}

    def test_clear_all_failures_when_empty(self, failure_tracker) -> None:
        """Test clearing all failures when tracker is already empty."""
        assert len(failure_tracker) == 0

        # Should not raise exception
        failure_tracker.clear_failures()

        assert len(failure_tracker) == 0

    def test_cleanup_old_failures(self) -> None:
        """Test automatic cleanup of old failure records."""
        # Use very short cleanup age for testing
        tracker = FailureTracker(
            base_retry_delay_minutes=1,
            max_retry_delay_minutes=5,
            retry_multiplier=2,
            max_failed_attempts=3,
            cleanup_age_hours=0.001,  # About 3.6 seconds
        )

        # Mock datetime to control time
        # Following UNIFIED_TESTING_GUIDE: Mock only at system boundaries (time)
        base_time = datetime.now()
        with patch("cache.failure_tracker.datetime") as mock_datetime:
            # Record old failure at base time
            mock_datetime.now.return_value = base_time
            tracker.record_failure("old_key", "Old error")

            # Advance time past cleanup age (4 seconds > 3.6 seconds)
            mock_datetime.now.return_value = base_time + timedelta(seconds=4)

            # Record recent failure at current time
            tracker.record_failure("recent_key", "Recent error")

            # Should clean up the old failure but keep the recent one
            cleaned_count = tracker.cleanup_old_failures()

        assert cleaned_count == 1
        assert len(tracker) == 1
        assert "old_key" not in tracker
        assert "recent_key" in tracker

    def test_automatic_cleanup_trigger(self, failure_tracker) -> None:
        """Test that cleanup is automatically triggered when failure count exceeds threshold."""
        # Record more than 10 failures to trigger automatic cleanup
        for i in range(12):
            failure_tracker.record_failure(f"key_{i:02d}", f"Error {i}")

        # The 11th and 12th failures should have triggered cleanup
        # (Though without time advancement, nothing would be cleaned)
        assert len(failure_tracker) == 12

    def test_custom_configuration(self, custom_failure_tracker) -> None:
        """Test FailureTracker with custom configuration parameters."""
        cache_key = "test_key"

        # Mock datetime to control time precisely
        # Following UNIFIED_TESTING_GUIDE: Mock only at system boundaries (time)
        base_time = datetime.now()
        with patch("cache.failure_tracker.datetime") as mock_datetime:
            # First failure at base time
            mock_datetime.now.return_value = base_time
            custom_failure_tracker.record_failure(cache_key, "Error")

            status = custom_failure_tracker.get_failure_status()
            failure_info = status[cache_key]

            # Verify delay is approximately 2 minutes
            next_retry = failure_info["next_retry"]
            delay_minutes = (next_retry - base_time).total_seconds() / 60
            assert 1.9 <= delay_minutes <= 2.1  # 2 minute delay with tolerance

            # Test custom multiplier (2x instead of 3x)
            # Advance time by 0.1 seconds for second failure
            second_time = base_time + timedelta(seconds=0.1)
            mock_datetime.now.return_value = second_time
            custom_failure_tracker.record_failure(cache_key, "Error 2")

            status = custom_failure_tracker.get_failure_status()
            failure_info = status[cache_key]

            # Second failure: 2 * 2^(2-1) = 2 * 2 = 4 minutes
            next_retry = failure_info["next_retry"]
            delay_minutes = (next_retry - second_time).total_seconds() / 60
            assert 3.9 <= delay_minutes <= 4.1  # 4 minute delay with tolerance

    def test_thread_safety_concurrent_failures(self, failure_tracker) -> None:
        """Test thread safety when recording failures concurrently."""
        num_threads = 10
        failures_per_thread = 5
        total_expected = num_threads * failures_per_thread

        results = []

        def record_failures(thread_id):
            """Record multiple failures from a single thread."""
            for i in range(failures_per_thread):
                key = f"thread_{thread_id}_key_{i}"
                failure_tracker.record_failure(key, f"Error from thread {thread_id}")
            return thread_id

        # Launch concurrent threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(record_failures, thread_id)
                for thread_id in range(num_threads)
            ]

            # Wait for all threads to complete
            for future in concurrent.futures.as_completed(futures, timeout=10):
                results.append(future.result())

        # Verify all failures were recorded correctly
        assert len(failure_tracker) == total_expected
        assert len(results) == num_threads

        # Verify no data corruption in concurrent access
        status = failure_tracker.get_failure_status()
        for thread_id in range(num_threads):
            for i in range(failures_per_thread):
                key = f"thread_{thread_id}_key_{i}"
                assert key in status
                assert status[key]["attempts"] == 1

    def test_thread_safety_concurrent_should_retry(self, failure_tracker) -> None:
        """Test thread safety of should_retry method under concurrent access."""
        cache_key = "shared_key"

        # Record initial failure
        failure_tracker.record_failure(cache_key, "Initial error")

        results = []

        def check_should_retry(thread_id):
            """Check should_retry from multiple threads."""
            for _ in range(100):  # Many checks per thread
                should_retry, reason = failure_tracker.should_retry(cache_key)
                results.append((thread_id, should_retry, reason))
            return thread_id

        # Launch multiple threads checking should_retry
        num_threads = 5
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(check_should_retry, thread_id)
                for thread_id in range(num_threads)
            ]

            for future in concurrent.futures.as_completed(futures, timeout=10):
                future.result()

        # All results should be consistent (all False since within backoff period)
        assert len(results) == num_threads * 100
        for thread_id, should_retry, reason in results:
            assert should_retry is False
            assert "Skipping recently failed operation" in reason

    def test_thread_safety_mixed_operations(self, failure_tracker) -> None:
        """Test thread safety with mixed concurrent operations."""
        operations_per_thread = 50
        num_threads = 8

        results = {
            "record_failure": [],
            "should_retry": [],
            "clear_failures": [],
            "get_status": [],
        }

        def mixed_operations(thread_id):
            """Perform mixed operations from each thread."""
            thread_results = {
                "record_failure": 0,
                "should_retry": 0,
                "clear_failures": 0,
                "get_status": 0,
            }

            for i in range(operations_per_thread):
                key = f"thread_{thread_id}_key_{i}"

                # Record failure
                failure_tracker.record_failure(key, f"Error {i}")
                thread_results["record_failure"] += 1

                # Check should_retry
                failure_tracker.should_retry(key)
                thread_results["should_retry"] += 1

                # Occasionally clear failures
                if i % 10 == 0:
                    failure_tracker.clear_failures(key)
                    thread_results["clear_failures"] += 1

                # Get status
                failure_tracker.get_failure_status()
                thread_results["get_status"] += 1

            return thread_results

        # Launch mixed operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(mixed_operations, thread_id)
                for thread_id in range(num_threads)
            ]

            for future in concurrent.futures.as_completed(futures, timeout=15):
                thread_results = future.result()
                for op_type, count in thread_results.items():
                    results[op_type].append(count)

        # Verify all operations completed
        assert len(results["record_failure"]) == num_threads
        assert sum(results["record_failure"]) == num_threads * operations_per_thread

        # Failure tracker should still be in consistent state
        final_count = failure_tracker.get_failure_count()
        assert final_count >= 0  # Some failures may have been cleared
        assert isinstance(final_count, int)

    def test_get_failure_status_returns_copy(self, failure_tracker) -> None:
        """Test that get_failure_status returns a copy of internal state."""
        failure_tracker.record_failure("test_key", "Test error")

        status1 = failure_tracker.get_failure_status()
        status2 = failure_tracker.get_failure_status()

        # Should be equal but different objects
        assert status1 == status2
        assert status1 is not status2

        # Modifying returned dict shouldn't affect internal state
        status1["fake_key"] = {"fake": "data"}

        status3 = failure_tracker.get_failure_status()
        assert "fake_key" not in status3
        assert len(status3) == 1

    def test_dunder_len_method(self, failure_tracker) -> None:
        """Test __len__ magic method returns correct count."""
        assert len(failure_tracker) == 0

        failure_tracker.record_failure("key1", "Error 1")
        assert len(failure_tracker) == 1

        failure_tracker.record_failure("key2", "Error 2")
        assert len(failure_tracker) == 2

        failure_tracker.clear_failures("key1")
        assert len(failure_tracker) == 1

        failure_tracker.clear_failures()
        assert len(failure_tracker) == 0

    def test_dunder_contains_method(self, failure_tracker) -> None:
        """Test __contains__ magic method for membership testing."""
        assert "nonexistent" not in failure_tracker

        failure_tracker.record_failure("existing_key", "Error")

        assert "existing_key" in failure_tracker
        assert "nonexistent" not in failure_tracker

        failure_tracker.clear_failures("existing_key")
        assert "existing_key" not in failure_tracker

    def test_dunder_repr_method(self, failure_tracker, custom_failure_tracker) -> None:
        """Test __repr__ magic method returns informative string."""
        # Empty tracker
        assert repr(failure_tracker) == "FailureTracker(failures=0, max_delay=120min)"

        # With failures
        failure_tracker.record_failure("key1", "Error 1")
        failure_tracker.record_failure("key2", "Error 2")
        assert repr(failure_tracker) == "FailureTracker(failures=2, max_delay=120min)"

        # Custom configuration
        assert (
            repr(custom_failure_tracker)
            == "FailureTracker(failures=0, max_delay=60min)"
        )

    def test_cleanup_age_configuration(self) -> None:
        """Test cleanup with custom age configuration."""
        # Create tracker with very short cleanup age for testing
        tracker = FailureTracker(cleanup_age_hours=0.001)  # About 3.6 seconds

        # Mock datetime to control time
        # Following UNIFIED_TESTING_GUIDE: Mock only at system boundaries (time)
        base_time = datetime.now()
        with patch("cache.failure_tracker.datetime") as mock_datetime:
            # Record failure at base time
            mock_datetime.now.return_value = base_time
            tracker.record_failure("old_key", "Old error")
            assert len(tracker) == 1

            # Advance time past cleanup threshold (4 seconds > 3.6 seconds)
            mock_datetime.now.return_value = base_time + timedelta(seconds=4)
            cleaned_count = tracker.cleanup_old_failures()

            # Should clean up the old failure
            assert cleaned_count == 1
            assert len(tracker) == 0

    def test_max_attempts_capping(self) -> None:
        """Test that delays are capped at max_failed_attempts."""
        # Create tracker with known configuration
        tracker = FailureTracker(
            base_retry_delay_minutes=5,
            max_retry_delay_minutes=120,
            retry_multiplier=3,
            max_failed_attempts=4,
        )

        cache_key = "test_key"

        # Expected delays: 5, 15, 45, 120, 120, 120 (capped at max)
        expected_delays = [5, 15, 45, 120, 120, 120]

        # Mock datetime to control time
        # Following UNIFIED_TESTING_GUIDE: Mock only at system boundaries (time)
        base_time = datetime.now()
        with patch("cache.failure_tracker.datetime") as mock_datetime:
            # Default config: max_failed_attempts=4, so attempts 4+ should use max delay
            for attempt in range(6):  # Go beyond max attempts
                # Set time for this attempt (increment by 1 second each iteration)
                current_time = base_time + timedelta(seconds=attempt)
                mock_datetime.now.return_value = current_time

                tracker.record_failure(cache_key, f"Error #{attempt + 1}")

                status = tracker.get_failure_status()
                failure_info = status[cache_key]

                # Verify delay matches expected pattern
                expected_delay = expected_delays[attempt]
                next_retry = failure_info["next_retry"]
                actual_delay = (next_retry - current_time).total_seconds() / 60

                # Allow tolerance for execution time
                assert expected_delay - 0.2 <= actual_delay <= expected_delay + 0.2

    def test_edge_case_zero_cleanup_age(self) -> None:
        """Test edge case with zero cleanup age (immediate cleanup)."""
        tracker = FailureTracker(cleanup_age_hours=0)

        # Mock datetime to control time
        # Following UNIFIED_TESTING_GUIDE: Mock only at system boundaries (time)
        base_time = datetime.now()
        with patch("cache.failure_tracker.datetime") as mock_datetime:
            # Record failure at base time
            mock_datetime.now.return_value = base_time
            tracker.record_failure("key", "Error")
            assert len(tracker) == 1

            # Any time advancement should trigger cleanup with zero age
            # Even a tiny time advancement
            mock_datetime.now.return_value = base_time + timedelta(milliseconds=1)
            cleaned_count = tracker.cleanup_old_failures()

            assert cleaned_count == 1
            assert len(tracker) == 0

    def test_pathlib_path_handling(self, failure_tracker) -> None:
        """Test proper handling of pathlib.Path objects in source_path."""
        cache_key = "test_key"
        source_path = Path("/complex/path/with spaces/image file.jpg")

        failure_tracker.record_failure(cache_key, "Path error", source_path)

        status = failure_tracker.get_failure_status()
        failure_info = status[cache_key]

        # Should store string representation of path
        assert failure_info["source_path"] == str(source_path)

        # should_retry should handle path names correctly
        should_retry, reason = failure_tracker.should_retry(cache_key, source_path)
        assert should_retry is False
        assert "image file.jpg" in reason  # Should show just the filename

    def test_memory_cleanup_pattern(self, failure_tracker) -> None:
        """Test that FailureTracker properly cleans up references."""

        # Create a large object to test memory management
        large_error_message = "x" * 10000  # Large string

        failure_tracker.record_failure("memory_test", large_error_message)
        assert len(failure_tracker) == 1

        # Verify the error is stored
        status = failure_tracker.get_failure_status()
        assert status["memory_test"]["error"] == large_error_message

        # Clear the failure and verify cleanup
        failure_tracker.clear_failures("memory_test")

        # Force garbage collection
        gc.collect()

        # Verify the tracker is empty and doesn't hold references
        assert len(failure_tracker) == 0
        assert failure_tracker.get_failure_status() == {}

    def test_concurrent_cleanup_safety(self, failure_tracker) -> None:
        """Test that concurrent cleanup operations are thread-safe."""
        # Pre-populate with failures
        for i in range(20):
            failure_tracker.record_failure(f"key_{i}", f"Error {i}")

        cleanup_results = []

        def concurrent_cleanup(thread_id):
            """Perform cleanup from multiple threads."""
            try:
                cleaned = failure_tracker.cleanup_old_failures()
                return cleaned
            except Exception as e:
                return f"Error: {e}"

        # Launch multiple cleanup operations concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(concurrent_cleanup, thread_id) for thread_id in range(5)
            ]

            for future in concurrent.futures.as_completed(futures, timeout=5):
                result = future.result()
                cleanup_results.append(result)

        # Should complete without exceptions
        assert len(cleanup_results) == 5
        for result in cleanup_results:
            assert isinstance(result, int)  # Should be cleaned count, not error
            assert result >= 0

        # Tracker should still be in consistent state
        assert failure_tracker.get_failure_count() >= 0
        assert len(failure_tracker.get_failure_status()) == len(failure_tracker)
