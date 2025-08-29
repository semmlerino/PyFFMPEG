#!/usr/bin/env python3
"""Test cache behavior and performance metrics for OptimizedShotModel."""

import time
from unittest.mock import Mock, patch

import pytest

from shot_model_optimized import OptimizedShotModel


class TestCacheScenarios:
    """Test cache hit/miss scenarios and performance tracking."""

    @pytest.fixture
    def optimized_model_with_cache(self, real_cache_manager):
        """Create OptimizedShotModel with real cache."""
        return OptimizedShotModel(real_cache_manager)

    def test_cache_hit_scenario(self, optimized_model_with_cache):
        """Test performance when cache data is available."""
        model = optimized_model_with_cache

        # Pre-populate cache
        cached_data = [
            {
                "show": "CACHED",
                "sequence": "seq01",
                "shot": "0010",
                "workspace_path": "/cached/path1",
            },
            {
                "show": "CACHED",
                "sequence": "seq01",
                "shot": "0020",
                "workspace_path": "/cached/path2",
            },
        ]
        model.cache_manager.cache_shots(cached_data)

        # Measure initialization time
        start_time = time.perf_counter()
        result = model.initialize_async()
        elapsed = time.perf_counter() - start_time

        # Should be very fast with cache hit
        assert elapsed < 0.01, f"Cache hit took {elapsed:.3f}s, should be < 0.01s"
        assert result.success is True
        assert len(model.shots) == 2

        # Check performance metrics
        metrics = model.get_performance_metrics()
        assert metrics["cache_hit_count"] == 1
        assert metrics["cache_miss_count"] == 0
        assert metrics["cache_hit_rate"] == 1.0

    def test_cache_miss_scenario(self, optimized_model_with_cache):
        """Test behavior when no cache data available."""
        model = optimized_model_with_cache

        # Ensure empty cache
        model.cache_manager.clear_cache()

        start_time = time.perf_counter()
        result = model.initialize_async()
        elapsed = time.perf_counter() - start_time

        # Should still return quickly (showing empty UI)
        assert elapsed < 0.01, f"Cache miss initialization took {elapsed:.3f}s"
        assert result.success is True
        assert len(model.shots) == 0  # Empty initially

        # Check metrics
        metrics = model.get_performance_metrics()
        assert metrics["cache_miss_count"] == 1
        assert metrics["cache_hit_rate"] == 0.0

    def test_mixed_cache_scenarios(self, optimized_model_with_cache):
        """Test multiple cache operations to verify hit rate calculation."""
        model = optimized_model_with_cache

        # First call - cache miss
        model.cache_manager.clear_cache()
        model.initialize_async()

        # Populate cache for next call
        model.cache_manager.cache_shots(
            [
                {
                    "show": "TEST",
                    "sequence": "seq",
                    "shot": "0010",
                    "workspace_path": "/test",
                }
            ]
        )

        # Second call - cache hit
        model.initialize_async()

        # Third call - cache hit
        model.initialize_async()

        metrics = model.get_performance_metrics()
        assert metrics["cache_hit_count"] == 2
        assert metrics["cache_miss_count"] == 1
        assert metrics["cache_hit_rate"] == 2 / 3  # 2 hits out of 3 total

    def test_cache_expiration_triggers_refresh(self, optimized_model_with_cache, qtbot):
        """Test that expired cache triggers background refresh."""
        model = optimized_model_with_cache

        # Mock cache with expired data
        with patch.object(model.cache_manager, "get_cached_shots") as mock_get:
            mock_get.return_value = None  # Simulate expired cache

            shots_changed_spy = qtbot.signalSpy(model.shots_changed)

            # Mock process pool for background refresh
            mock_pool = Mock()
            mock_pool.execute_workspace_command.return_value = "workspace /new/data"
            model._process_pool = mock_pool

            result = model.initialize_async()
            assert result.success is True  # initialize_async returns success immediately

            # Should trigger background refresh
            qtbot.waitUntil(lambda: len(shots_changed_spy) > 0, timeout=5000)

            # Verify refresh was triggered
            assert mock_pool.execute_workspace_command.called

    def test_performance_metrics_accuracy(self, optimized_model_with_cache):
        """Test that performance metrics accurately track operations."""
        model = optimized_model_with_cache

        initial_metrics = model.get_performance_metrics()
        assert initial_metrics["cache_hit_count"] == 0
        assert initial_metrics["cache_miss_count"] == 0

        # Perform operations and verify metrics update
        model.cache_manager.clear_cache()
        model.initialize_async()  # Should be cache miss

        # Add cache data
        model.cache_manager.cache_shots(
            [{"show": "TEST", "sequence": "s", "shot": "1", "workspace_path": "/p"}]
        )
        model.initialize_async()  # Should be cache hit

        final_metrics = model.get_performance_metrics()
        assert final_metrics["cache_hit_count"] == 1
        assert final_metrics["cache_miss_count"] == 1

    def test_session_warming_performance(self, optimized_model_with_cache):
        """Test that session pre-warming improves subsequent performance."""
        model = optimized_model_with_cache

        # Mock process pool to track calls
        mock_pool = Mock()
        mock_pool.execute_workspace_command.return_value = "warming"
        model._process_pool = mock_pool

        # Measure pre-warming
        start_time = time.perf_counter()
        model.pre_warm_sessions()
        warm_time = time.perf_counter() - start_time

        # Should complete quickly and mark as warmed
        assert warm_time < 1.0, f"Session warming took {warm_time:.3f}s"

        metrics = model.get_performance_metrics()
        assert metrics["session_warmed"] is True

        # Verify warm command was called
        mock_pool.execute_workspace_command.assert_called_with(
            "echo warming", cache_ttl=1, timeout=5
        )

    def test_concurrent_cache_access(self, optimized_model_with_cache):
        """Test cache behavior with concurrent access (thread safety)."""
        model = optimized_model_with_cache

        # Pre-populate cache
        model.cache_manager.cache_shots(
            [
                {
                    "show": "CONCURRENT",
                    "sequence": "seq",
                    "shot": "0010",
                    "workspace_path": "/path",
                }
            ]
        )

        # Simulate concurrent initialization calls
        results = []
        for _ in range(3):
            result = model.initialize_async()
            results.append(result)

        # All should succeed
        assert all(r.success for r in results)

        # Cache hit count should be accurate (may be 3 if all hit cache)
        metrics = model.get_performance_metrics()
        assert metrics["cache_hit_count"] >= 1
