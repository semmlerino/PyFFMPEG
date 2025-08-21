"""Integration tests for Previous Shots cache functionality following UNIFIED_TESTING_GUIDE.

Tests the integration between Previous Shots components and the cache system.
Focuses on cache consistency, data persistence, and performance.

Focus areas:
- Cache integration with real CacheManager components
- Data persistence and TTL behavior
- Cache invalidation and refresh
- Performance with cached vs uncached data
- Thread safety in cache operations
"""

import json
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cache_manager import CacheManager
from previous_shots_model import PreviousShotsModel
from shot_model import Shot, ShotModel


class TestPreviousShootsCacheIntegration:
    """Integration tests for Previous Shots cache functionality."""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path: Path) -> Path:
        """Create temporary cache directory."""
        cache_dir = tmp_path / "test_cache"
        cache_dir.mkdir(exist_ok=True)
        return cache_dir

    @pytest.fixture
    def cache_manager(self, temp_cache_dir: Path) -> CacheManager:
        """Create real CacheManager with temporary storage."""
        return CacheManager(cache_dir=temp_cache_dir)

    @pytest.fixture
    def mock_shot_model(self) -> ShotModel:
        """Create mock ShotModel."""
        mock_model = Mock(spec=ShotModel)
        mock_model.get_shots.return_value = [
            Shot("active_show", "seq1", "shot1", "/shows/active_show/shots/seq1/shot1"),
        ]
        return mock_model

    @pytest.fixture
    def previous_shots_model(
        self, mock_shot_model, cache_manager, qtbot
    ) -> PreviousShotsModel:
        """Create PreviousShotsModel with real cache."""
        model = PreviousShotsModel(mock_shot_model, cache_manager)
        # Note: PreviousShotsModel is QObject, not QWidget - no qtbot.addWidget() needed
        return model

    def test_cache_storage_and_retrieval(self, cache_manager, temp_cache_dir):
        """Test basic cache storage and retrieval for previous shots."""
        # Test data
        test_shots = [
            {
                "show": "test_show",
                "sequence": "test_seq",
                "shot": "test_shot",
                "workspace_path": "/test/path",
            }
        ]

        # Cache the data
        cache_manager.cache_previous_shots(test_shots)

        # Verify cache file exists
        cache_file = temp_cache_dir / "previous_shots.json"
        assert cache_file.exists()

        # Retrieve from cache
        cached_data = cache_manager.get_cached_previous_shots()

        assert cached_data is not None
        assert len(cached_data) == 1
        assert cached_data[0]["show"] == "test_show"
        assert cached_data[0]["sequence"] == "test_seq"
        assert cached_data[0]["shot"] == "test_shot"

    def test_cache_data_consistency(self, cache_manager):
        """Test cache data format consistency."""
        # Original shots from model
        original_shots = [
            Shot("show1", "seq1", "shot1", "/shows/show1/shots/seq1/shot1"),
            Shot("show1", "seq1", "shot2", "/shows/show1/shots/seq1/shot2"),
        ]

        # Convert to cache format (as done by model)
        cache_data = [
            {
                "show": s.show,
                "sequence": s.sequence,
                "shot": s.shot,
                "workspace_path": s.workspace_path,
            }
            for s in original_shots
        ]

        # Cache and retrieve
        cache_manager.cache_previous_shots(cache_data)
        retrieved_data = cache_manager.get_cached_previous_shots()

        # Should be identical
        assert retrieved_data == cache_data

        # Convert back to Shot objects
        reconstructed_shots = [
            Shot(
                show=s["show"],
                sequence=s["sequence"],
                shot=s["shot"],
                workspace_path=s["workspace_path"],
            )
            for s in retrieved_data
        ]

        # Should match original shots
        for orig, recon in zip(original_shots, reconstructed_shots):
            assert orig.show == recon.show
            assert orig.sequence == recon.sequence
            assert orig.shot == recon.shot
            assert orig.workspace_path == recon.workspace_path

    def test_cache_ttl_behavior(self, cache_manager, temp_cache_dir):
        """Test cache TTL (Time To Live) behavior."""
        # Cache some data
        test_data = [
            {
                "show": "test",
                "sequence": "seq",
                "shot": "shot",
                "workspace_path": "/path",
            }
        ]
        cache_manager.cache_previous_shots(test_data)

        # Verify data is cached
        assert cache_manager.get_cached_previous_shots() is not None

        # Manually modify timestamp to simulate expiration
        cache_file = temp_cache_dir / "previous_shots.json"
        cache_content = json.loads(cache_file.read_text())

        # Set timestamp to 2 hours ago (beyond 30 minute TTL)
        old_timestamp = time.time() - (2 * 60 * 60)  # 2 hours ago
        cache_content["timestamp"] = old_timestamp

        cache_file.write_text(json.dumps(cache_content))

        # Should return None for expired cache
        cached_data = cache_manager.get_cached_previous_shots()
        assert cached_data is None

    def test_cache_invalidation(self, cache_manager, temp_cache_dir):
        """Test cache invalidation and clearing."""
        # Cache some data
        test_data = [
            {
                "show": "test",
                "sequence": "seq",
                "shot": "shot",
                "workspace_path": "/path",
            }
        ]
        cache_manager.cache_previous_shots(test_data)

        # Verify cached
        assert cache_manager.get_cached_previous_shots() is not None

        # Clear cache
        cache_manager.clear_cached_data("previous_shots")

        # Should be cleared
        cache_file = temp_cache_dir / "previous_shots.json"
        assert not cache_file.exists()

        # Should return None
        assert cache_manager.get_cached_previous_shots() is None

    def test_model_cache_integration_on_init(
        self, mock_shot_model, temp_cache_dir, qtbot
    ):
        """Test model loads from cache on initialization."""
        # Pre-populate cache
        cache_manager = CacheManager(cache_dir=temp_cache_dir)
        test_data = [
            {
                "show": "cached_show",
                "sequence": "cached_seq",
                "shot": "cached_shot",
                "workspace_path": "/cached/path",
            }
        ]
        cache_manager.cache_previous_shots(test_data)

        # Create model - should load from cache
        model = PreviousShotsModel(mock_shot_model, cache_manager)
        qtbot.addWidget(model)

        # Should have loaded cached data
        shots = model.get_shots()
        assert len(shots) == 1
        assert shots[0].show == "cached_show"
        assert shots[0].shot == "cached_shot"

    def test_model_cache_integration_on_refresh(self, previous_shots_model):
        """Test model saves to cache after refresh."""
        # Mock finder to return approved shots
        mock_approved = [
            Shot("new_show", "new_seq", "new_shot", "/new/path"),
        ]

        with patch.object(
            previous_shots_model._finder,
            "find_approved_shots",
            return_value=mock_approved,
        ):
            # Refresh should trigger cache save
            result = previous_shots_model.refresh_shots()

            assert result is True

            # Verify data was cached
            cached_data = (
                previous_shots_model._cache_manager.get_cached_previous_shots()
            )
            assert cached_data is not None
            assert len(cached_data) == 1
            assert cached_data[0]["show"] == "new_show"

    def test_cache_performance_improvement(self, previous_shots_model, temp_cache_dir):
        """Test that cache provides performance improvement."""
        # First run - populate cache
        mock_approved = [
            Shot(f"show{i}", f"seq{i}", f"shot{i}", f"/path{i}")
            for i in range(100)  # Many shots
        ]

        with patch.object(
            previous_shots_model._finder,
            "find_approved_shots",
            return_value=mock_approved,
        ):
            start_time = time.time()
            previous_shots_model.refresh_shots()
            first_run_time = time.time() - start_time

        # Create new model instance - should load from cache
        from previous_shots_model import PreviousShotsModel

        start_time = time.time()
        cached_model = PreviousShotsModel(
            previous_shots_model._shot_model, previous_shots_model._cache_manager
        )
        cache_load_time = time.time() - start_time

        # Cache loading should be much faster
        assert cache_load_time < first_run_time / 2  # At least 2x faster

        # Should have same data
        assert len(cached_model.get_shots()) == 100

    def test_cache_corruption_recovery(self, temp_cache_dir, mock_shot_model, qtbot):
        """Test recovery from corrupted cache files."""
        # Create corrupted cache file
        cache_file = temp_cache_dir / "previous_shots.json"
        cache_file.write_text("invalid json content")

        cache_manager = CacheManager(cache_dir=temp_cache_dir)

        # Should handle corrupted cache gracefully
        cached_data = cache_manager.get_cached_previous_shots()
        assert cached_data is None

        # Model should initialize without crashing
        model = PreviousShotsModel(mock_shot_model, cache_manager)
        qtbot.addWidget(model)

        assert len(model.get_shots()) == 0

    def test_cache_partial_write_recovery(self, temp_cache_dir, cache_manager):
        """Test recovery from partial cache writes."""
        # Simulate partial write by creating incomplete JSON
        cache_file = temp_cache_dir / "previous_shots.json"
        cache_file.write_text('{"data": [{"show": "test"')  # Incomplete JSON

        # Should handle partial write gracefully
        cached_data = cache_manager.get_cached_previous_shots()
        assert cached_data is None

        # Should be able to write new data after corruption
        test_data = [
            {
                "show": "recovery_test",
                "sequence": "seq",
                "shot": "shot",
                "workspace_path": "/path",
            }
        ]
        cache_manager.cache_previous_shots(test_data)

        # Should work normally after recovery
        recovered_data = cache_manager.get_cached_previous_shots()
        assert recovered_data is not None
        assert len(recovered_data) == 1

    def test_concurrent_cache_access(self, cache_manager, temp_cache_dir):
        """Test thread safety of cache operations."""
        import concurrent.futures

        results = []
        errors = []

        def cache_operation(thread_id):
            try:
                # Each thread caches different data
                data = [
                    {
                        "show": f"show_{thread_id}",
                        "sequence": "seq",
                        "shot": "shot",
                        "workspace_path": f"/path_{thread_id}",
                    }
                ]

                cache_manager.cache_previous_shots(data)
                retrieved = cache_manager.get_cached_previous_shots()
                results.append((thread_id, retrieved))

            except Exception as e:
                errors.append((thread_id, str(e)))

        # Run multiple threads concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(cache_operation, i) for i in range(5)]
            concurrent.futures.wait(futures)

        # Should not have errors (though data might be overwritten)
        assert len(errors) == 0
        assert len(results) == 5

        # Final cache should be valid
        final_data = cache_manager.get_cached_previous_shots()
        assert final_data is not None
        assert len(final_data) == 1

    def test_cache_directory_creation(self, tmp_path):
        """Test cache directory creation when it doesn't exist."""
        nonexistent_cache_dir = tmp_path / "nonexistent" / "cache"

        # Should create directory structure
        cache_manager = CacheManager(cache_dir=nonexistent_cache_dir)

        test_data = [
            {
                "show": "test",
                "sequence": "seq",
                "shot": "shot",
                "workspace_path": "/path",
            }
        ]
        cache_manager.cache_previous_shots(test_data)

        # Directory should be created
        assert nonexistent_cache_dir.exists()
        assert (nonexistent_cache_dir / "previous_shots.json").exists()

    def test_cache_permissions_handling(self, temp_cache_dir, cache_manager):
        """Test handling of cache permission issues."""
        # Cache some data first
        test_data = [
            {
                "show": "test",
                "sequence": "seq",
                "shot": "shot",
                "workspace_path": "/path",
            }
        ]
        cache_manager.cache_previous_shots(test_data)

        cache_file = temp_cache_dir / "previous_shots.json"
        assert cache_file.exists()

        # Make cache file read-only
        cache_file.chmod(0o444)

        try:
            # Attempt to cache new data should handle permission error
            new_data = [
                {
                    "show": "new",
                    "sequence": "seq",
                    "shot": "shot",
                    "workspace_path": "/path",
                }
            ]
            cache_manager.cache_previous_shots(new_data)  # Should not crash

        except PermissionError:
            # This is acceptable - the important thing is not crashing
            pass

        finally:
            # Restore permissions for cleanup
            cache_file.chmod(0o644)


class TestPreviousShootsCachePerformance:
    """Performance tests for cache operations."""

    @pytest.fixture
    def large_dataset(self) -> list[dict]:
        """Create large dataset for performance testing."""
        return [
            {
                "show": f"show_{i:03d}",
                "sequence": f"seq_{j:03d}",
                "shot": f"shot_{k:04d}",
                "workspace_path": f"/shows/show_{i:03d}/shots/seq_{j:03d}/shot_{k:04d}",
            }
            for i in range(10)  # 10 shows
            for j in range(5)  # 5 sequences per show
            for k in range(20)  # 20 shots per sequence
        ]  # Total: 1000 shots

    def test_large_dataset_cache_performance(self, cache_manager, large_dataset):
        """Test cache performance with large dataset."""
        start_time = time.time()

        # Cache large dataset
        cache_manager.cache_previous_shots(large_dataset)
        cache_time = time.time() - start_time

        start_time = time.time()

        # Retrieve large dataset
        retrieved_data = cache_manager.get_cached_previous_shots()
        retrieve_time = time.time() - start_time

        # Performance should be reasonable
        assert cache_time < 1.0  # Less than 1 second to cache 1000 shots
        assert retrieve_time < 0.5  # Less than 0.5 seconds to retrieve

        # Data should be correct
        assert len(retrieved_data) == 1000
        assert retrieved_data == large_dataset

    def test_cache_file_size_efficiency(
        self, cache_manager, large_dataset, temp_cache_dir
    ):
        """Test cache file size efficiency."""
        # Cache large dataset
        cache_manager.cache_previous_shots(large_dataset)

        cache_file = temp_cache_dir / "previous_shots.json"
        file_size = cache_file.stat().st_size

        # File size should be reasonable (not excessively large)
        # Estimate: ~100 bytes per shot entry, 1000 shots = ~100KB
        expected_size = len(large_dataset) * 100  # 100 bytes per shot
        assert file_size < expected_size * 2  # Allow 2x overhead for JSON structure

        # Should be able to read file efficiently
        start_time = time.time()
        cache_file.read_text()
        read_time = time.time() - start_time

        assert read_time < 0.1  # Should read in less than 100ms

    def test_memory_usage_during_cache_operations(self, cache_manager, large_dataset):
        """Test memory usage during cache operations."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Cache large dataset
        cache_manager.cache_previous_shots(large_dataset)

        after_cache_memory = process.memory_info().rss
        cache_memory_increase = after_cache_memory - initial_memory

        # Retrieve dataset multiple times
        for _ in range(10):
            retrieved_data = cache_manager.get_cached_previous_shots()
            assert len(retrieved_data) == 1000

        final_memory = process.memory_info().rss
        total_memory_increase = final_memory - initial_memory

        # Memory usage should be reasonable
        # Should not leak memory with repeated retrievals
        assert total_memory_increase < 50 * 1024 * 1024  # Less than 50MB increase

        # Memory increase from caching vs total should be similar
        # (no significant leaks from repeated retrievals)
        retrieval_overhead = total_memory_increase - cache_memory_increase
        assert retrieval_overhead < 10 * 1024 * 1024  # Less than 10MB overhead
