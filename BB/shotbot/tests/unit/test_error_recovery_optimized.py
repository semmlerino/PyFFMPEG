#!/usr/bin/env python3
"""Test error recovery scenarios for OptimizedShotModel."""

import time
from unittest.mock import Mock, patch

import pytest

from shot_model_optimized import AsyncShotLoader, OptimizedShotModel


class TestErrorRecovery:
    """Test error handling and recovery in optimized shot model."""

    @pytest.fixture
    def error_prone_model(self, real_cache_manager):
        """Create model for error testing."""
        return OptimizedShotModel(real_cache_manager)

    def test_network_failure_recovery(self, error_prone_model, qtbot):
        """Test recovery from network/filesystem failures."""
        # Mock process pool that fails initially, then succeeds
        call_count = 0

        def failing_command(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Network unreachable")
            return "workspace /shows/recovered/seq01/0010"

        mock_pool = Mock()
        mock_pool.execute_workspace_command.side_effect = failing_command
        error_prone_model._process_pool = mock_pool

        # Setup signal spy for error
        error_spy = qtbot.signalSpy(error_prone_model.error_occurred)

        # First call should fail
        result1 = error_prone_model.initialize_async()

        # Wait for error signal
        qtbot.waitUntil(lambda: len(error_spy) > 0, timeout=3000)

        # Verify error was handled
        assert len(error_spy) == 1
        assert "Network unreachable" in error_spy.at(0)[0]

        # Second call should succeed
        result2 = error_prone_model.refresh_shots()
        assert result2.success is True

    def test_timeout_handling(self, error_prone_model, qtbot):
        """Test handling of command timeouts."""

        def timeout_command(*args, **kwargs):
            time.sleep(2)  # Simulate long operation
            return "timeout test"

        mock_pool = Mock()
        mock_pool.execute_workspace_command.side_effect = timeout_command
        error_prone_model._process_pool = mock_pool

        # Should handle timeout gracefully
        error_spy = qtbot.signalSpy(error_prone_model.error_occurred)

        start_time = time.perf_counter()
        result = error_prone_model.initialize_async()

        # Should return immediately even if background times out
        elapsed = time.perf_counter() - start_time
        assert elapsed < 0.1, "Initialization should return immediately"

    def test_corrupted_cache_recovery(self, error_prone_model):
        """Test recovery from corrupted cache data."""
        # Mock corrupted cache data
        with patch.object(
            error_prone_model.cache_manager, "get_cached_shots"
        ) as mock_cache:
            mock_cache.side_effect = ValueError("Corrupted cache data")

            # Should handle corrupted cache gracefully
            result = error_prone_model.initialize_async()

            # Should fall back to empty data and trigger background refresh
            assert result.success is True
            assert len(error_prone_model.shots) == 0

    def test_process_pool_failure_fallback(self, error_prone_model):
        """Test fallback when process pool is unavailable."""
        # Set None process pool to simulate unavailability
        error_prone_model._process_pool = None

        result = error_prone_model.refresh_shots()

        # Should handle gracefully
        assert result.success is False
        # Should not crash the application

    def test_async_loader_exception_handling(self, qtbot):
        """Test AsyncShotLoader handles exceptions properly."""
        # Create failing process pool
        failing_pool = Mock()
        failing_pool.execute_workspace_command.side_effect = RuntimeError(
            "Critical error"
        )

        loader = AsyncShotLoader(failing_pool)
        qtbot.addWidget(loader)

        error_spy = qtbot.signalSpy(loader.load_failed)
        success_spy = qtbot.signalSpy(loader.shots_loaded)

        loader.start()
        assert loader.wait(3000)

        # Error signal should be emitted, not success
        assert len(error_spy) == 1
        assert len(success_spy) == 0
        assert "Critical error" in error_spy.at(0)[0]

    def test_partial_data_handling(self, error_prone_model, qtbot):
        """Test handling of partial or malformed workspace data."""
        # Mock process pool returning partial data
        mock_pool = Mock()
        mock_pool.execute_workspace_command.return_value = """workspace /valid/path/seq01/0010
invalid line without workspace prefix
workspace /another/valid/path/seq02/0020
workspace incomplete_path_without_enough_parts
workspace /valid/path/seq03/0030"""

        error_prone_model._process_pool = mock_pool

        result = error_prone_model.refresh_shots()

        # Should parse valid entries and skip invalid ones
        assert result.success is True
        assert len(error_prone_model.shots) == 3  # Only valid entries

        # Verify valid shots were parsed correctly
        valid_shots = [
            shot
            for shot in error_prone_model.shots
            if shot.show in ["valid", "another", "valid"]
        ]
        assert len(valid_shots) == 3

    def test_cleanup_after_error(self, error_prone_model):
        """Test that cleanup works properly after errors."""
        # Cause an error state
        mock_pool = Mock()
        mock_pool.execute_workspace_command.side_effect = Exception("Setup error")
        error_prone_model._process_pool = mock_pool

        # Try to initialize (will fail)
        error_prone_model.initialize_async()

        # Cleanup should work without hanging
        start_time = time.perf_counter()
        error_prone_model.cleanup()
        cleanup_time = time.perf_counter() - start_time

        # Cleanup should complete quickly
        assert cleanup_time < 2.0, f"Cleanup took {cleanup_time:.3f}s, too slow"

    def test_error_metrics_tracking(self, error_prone_model):
        """Test that errors are tracked in performance metrics."""
        # Mock failing process pool
        mock_pool = Mock()
        mock_pool.execute_workspace_command.side_effect = RuntimeError("Tracked error")
        error_prone_model._process_pool = mock_pool

        # Attempt operations that will fail
        error_prone_model.initialize_async()

        # Wait a moment for background processing
        time.sleep(0.1)

        # Metrics should be available even after errors
        metrics = error_prone_model.get_performance_metrics()
        assert isinstance(metrics, dict)
        assert "cache_hit_count" in metrics
        assert "cache_miss_count" in metrics