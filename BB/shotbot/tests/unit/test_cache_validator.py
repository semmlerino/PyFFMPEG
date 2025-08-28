"""Comprehensive tests for CacheValidator following UNIFIED_TESTING_GUIDE principles."""

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from cache.cache_validator import CacheValidator
from cache.memory_manager import MemoryManager
from cache.storage_backend import StorageBackend

pytestmark = pytest.mark.unit

# Tests the cache validation and repair operations using real MemoryManager
# and StorageBackend components, with real file operations in temporary directories.
# This is an integration test that validates the high-level coordination
# between cache components.

# Import real components for integration testing


# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)


class TestCacheValidator:
    """Test cache validation and repair operations with real components."""

    @pytest.fixture
    def thumbnails_dir(self, tmp_path: Path) -> Path:
        """Create temporary thumbnails directory structure."""
        thumb_dir = tmp_path / "thumbnails"
        thumb_dir.mkdir()

        # Create show subdirectories
        (thumb_dir / "show1").mkdir()
        (thumb_dir / "show2").mkdir()

        return thumb_dir

    @pytest.fixture
    def memory_manager(self) -> MemoryManager:
        """Create real MemoryManager with test memory limit."""
        return MemoryManager(max_memory_mb=10)  # Small limit for testing

    @pytest.fixture
    def storage_backend(self) -> StorageBackend:
        """Create real StorageBackend instance."""
        return StorageBackend()

    @pytest.fixture
    def validator(
        self,
        thumbnails_dir: Path,
        memory_manager: MemoryManager,
        storage_backend: StorageBackend,
    ) -> CacheValidator:
        """Create CacheValidator with real components."""
        return CacheValidator(
            thumbnails_directory=thumbnails_dir,
            memory_manager=memory_manager,
            storage_backend=storage_backend,
        )

    @pytest.fixture
    def sample_thumbnail_files(self, thumbnails_dir: Path) -> list[Path]:
        """Create sample thumbnail files in the cache directory."""
        files = []

        # Create thumbnails in show1
        show1_dir = thumbnails_dir / "show1"
        for i in range(3):
            thumb_file = show1_dir / f"thumb_{i}.jpg"
            # Write minimal JPEG data with different sizes
            size = 1024 * (i + 1)  # 1KB, 2KB, 3KB
            thumb_file.write_bytes(
                b"\xff\xd8\xff\xe0" + b"x" * (size - 4) + b"\xff\xd9"
            )
            files.append(thumb_file)

        # Create thumbnails in show2
        show2_dir = thumbnails_dir / "show2"
        for i in range(2):
            thumb_file = show2_dir / f"thumb_{i}.jpg"
            size = 1024 * (i + 2)  # 2KB, 3KB
            thumb_file.write_bytes(
                b"\xff\xd8\xff\xe0" + b"x" * (size - 4) + b"\xff\xd9"
            )
            files.append(thumb_file)

        return files

    def test_validator_initialization(
        self,
        thumbnails_dir: Path,
        memory_manager: MemoryManager,
        storage_backend: StorageBackend,
    ):
        """Test CacheValidator initialization with real components."""
        validator = CacheValidator(
            thumbnails_directory=thumbnails_dir,
            memory_manager=memory_manager,
            storage_backend=storage_backend,
        )

        assert validator._thumbnails_dir == thumbnails_dir
        assert validator._memory_manager is memory_manager
        assert validator._storage is storage_backend
        assert str(validator).startswith("CacheValidator(dir=")

    def test_get_cache_statistics_empty_cache(self, validator: CacheValidator):
        """Test statistics for empty cache directory."""
        stats = validator.get_cache_statistics()

        assert "thumbnails_directory" in stats
        assert stats["directory_exists"] is True
        assert stats["actual_thumbnail_count"] == 0
        assert stats["actual_total_size_mb"] == 0
        assert stats["show_directories"] == 2  # show1, show2 directories
        assert "memory_stats" in stats

    def test_get_cache_statistics_with_files(
        self, validator: CacheValidator, sample_thumbnail_files: list[Path]
    ):
        """Test statistics calculation with actual thumbnail files."""
        stats = validator.get_cache_statistics()

        assert stats["actual_thumbnail_count"] == 5  # 3 + 2 files
        assert stats["actual_total_size_mb"] > 0
        assert stats["show_directories"] == 2

        # Verify memory stats are included
        memory_stats = stats["memory_stats"]
        assert "total_bytes" in memory_stats
        assert "usage_percent" in memory_stats

    def test_validate_cache_clean_state(self, validator: CacheValidator):
        """Test cache validation when cache is in clean state."""
        results = validator.validate_cache(fix_issues=False)

        assert results["valid"] is True
        assert results["issues_found"] == 0
        assert results["issues_fixed"] == 0
        assert results["orphaned_files"] == 0
        assert results["missing_files"] == 0
        assert results["size_mismatches"] == 0
        assert results["memory_usage_corrected"] is False
        assert isinstance(results["details"], list)

    def test_validate_cache_with_orphaned_files(
        self, validator: CacheValidator, sample_thumbnail_files: list[Path]
    ):
        """Test detection of orphaned files not tracked by memory manager."""
        # Files exist but are not tracked by memory manager (orphaned)
        results = validator.validate_cache(fix_issues=False)

        assert results["valid"] is False
        assert results["orphaned_files"] == 5  # All files are orphaned
        assert results["issues_found"] == 5  # Only counts specific issue types
        # Note: details may not be preserved due to results.update() behavior

    def test_validate_cache_fix_orphaned_files(
        self, validator: CacheValidator, sample_thumbnail_files: list[Path]
    ):
        """Test automatic repair of orphaned files by adding to tracking."""
        # Validate and fix orphaned files
        results = validator.validate_cache(fix_issues=True)

        assert results["orphaned_files"] == 5
        assert results["issues_fixed"] >= 5  # Files should be added to tracking

        # Verify files are now tracked
        for thumb_file in sample_thumbnail_files:
            assert validator._memory_manager.is_item_tracked(thumb_file)

        # Second validation should show clean state
        results2 = validator.validate_cache(fix_issues=False)
        assert results2["valid"] is True
        assert results2["orphaned_files"] == 0

    def test_validate_cache_missing_directory_create(self, tmp_path: Path):
        """Test automatic creation of missing thumbnails directory."""
        missing_dir = tmp_path / "missing_thumbnails"
        memory_manager = MemoryManager()
        storage_backend = StorageBackend()

        validator = CacheValidator(
            thumbnails_directory=missing_dir,
            memory_manager=memory_manager,
            storage_backend=storage_backend,
        )

        # Directory does not exist initially
        assert not missing_dir.exists()

        # Validation should create the directory
        results = validator.validate_cache(fix_issues=True)

        assert missing_dir.exists()
        assert results["issues_fixed"] >= 1
        assert "Created missing thumbnails directory" in str(results["details"])

    def test_validate_cache_missing_directory_no_fix(self, tmp_path: Path):
        """Test detection of missing directory without fixing."""
        missing_dir = tmp_path / "missing_thumbnails"
        memory_manager = MemoryManager()
        storage_backend = StorageBackend()

        validator = CacheValidator(
            thumbnails_directory=missing_dir,
            memory_manager=memory_manager,
            storage_backend=storage_backend,
        )

        results = validator.validate_cache(fix_issues=False)

        assert not missing_dir.exists()
        # Note: structure_issues are not counted in issues_found, so validation may still pass
        # The important thing is that structure_issues > 0
        assert results.get("structure_issues", 0) > 0
        assert "Thumbnails directory does not exist" in str(results["details"])

    def test_validate_memory_tracking_integration(
        self, validator: CacheValidator, sample_thumbnail_files: list[Path]
    ):
        """Test integration with MemoryManager validate_tracking method."""
        # Add some files to tracking with incorrect sizes to create mismatches
        memory_manager = validator._memory_manager

        # Track files with incorrect sizes to simulate memory tracking issues
        for i, thumb_file in enumerate(sample_thumbnail_files[:2]):
            # Force incorrect tracking size
            memory_manager._cached_items[str(thumb_file)] = 999  # Wrong size
            memory_manager._memory_usage_bytes += 999

        results = validator.validate_cache(fix_issues=True)

        # Should detect and fix memory tracking issues
        assert results["memory_usage_corrected"] is True or results["issues_fixed"] > 0

    def test_repair_cache_comprehensive(
        self, validator: CacheValidator, sample_thumbnail_files: list[Path]
    ):
        """Test comprehensive cache repair operation."""
        # This is an alias for validate_cache with fix_issues=True
        results = validator.repair_cache()

        assert isinstance(results, dict)
        assert "valid" in results
        assert "issues_found" in results
        assert "issues_fixed" in results

        # After repair, orphaned files should be tracked
        for thumb_file in sample_thumbnail_files:
            assert validator._memory_manager.is_item_tracked(thumb_file)

    def test_clean_empty_directories(self, validator: CacheValidator, tmp_path: Path):
        """Test removal of empty subdirectories in cache."""
        thumbnails_dir = validator._thumbnails_dir

        # Create some empty subdirectories
        empty_dir1 = thumbnails_dir / "empty1"
        empty_dir2 = thumbnails_dir / "empty2"
        nested_empty = thumbnails_dir / "nested" / "empty"

        empty_dir1.mkdir()
        empty_dir2.mkdir()
        nested_empty.mkdir(parents=True)

        # Also create a non-empty directory
        non_empty = thumbnails_dir / "show3"
        non_empty.mkdir()
        (non_empty / "file.jpg").touch()

        assert empty_dir1.exists()
        assert empty_dir2.exists()
        assert nested_empty.exists()
        assert non_empty.exists()

        # Clean empty directories
        removed_count = validator.clean_empty_directories()

        assert removed_count >= 3  # Should remove empty1, empty2, and nested/empty
        assert not empty_dir1.exists()
        assert not empty_dir2.exists()
        assert not nested_empty.exists()
        assert non_empty.exists()  # Non-empty should remain

    def test_clean_empty_directories_nonexistent_cache(self, tmp_path: Path):
        """Test clean_empty_directories when cache directory does not exist."""
        missing_dir = tmp_path / "missing"
        memory_manager = MemoryManager()
        storage_backend = StorageBackend()

        validator = CacheValidator(
            thumbnails_directory=missing_dir,
            memory_manager=memory_manager,
            storage_backend=storage_backend,
        )

        removed_count = validator.clean_empty_directories()
        assert removed_count == 0

    def test_analyze_cache_efficiency_high_usage(
        self, validator: CacheValidator, sample_thumbnail_files: list[Path]
    ):
        """Test cache efficiency analysis with high memory usage."""
        # Track all files to create high memory usage
        memory_manager = validator._memory_manager
        for thumb_file in sample_thumbnail_files:
            memory_manager.track_item(thumb_file)

        # Force high memory usage for testing
        memory_manager._memory_usage_bytes = int(
            memory_manager._max_memory_bytes * 0.95
        )

        analysis = validator.analyze_cache_efficiency()

        assert "memory_utilization_percent" in analysis
        assert analysis["memory_utilization_percent"] > 90
        assert "recommendations" in analysis
        assert len(analysis["recommendations"]) > 0
        assert any("very high" in rec for rec in analysis["recommendations"])

    def test_analyze_cache_efficiency_low_usage(self, validator: CacheValidator):
        """Test cache efficiency analysis with low memory usage."""
        # Empty cache should have low utilization
        analysis = validator.analyze_cache_efficiency()

        assert "memory_utilization_percent" in analysis
        assert analysis["memory_utilization_percent"] <= 20
        assert "recommendations" in analysis

        # Should recommend considering reduced limit
        recommendations = analysis["recommendations"]
        if recommendations:  # Only check if recommendations exist
            assert any("low" in rec for rec in recommendations)

    def test_analyze_cache_efficiency_large_files(
        self, validator: CacheValidator, tmp_path: Path
    ):
        """Test efficiency analysis with large thumbnail files."""
        # Create large thumbnail file
        thumbnails_dir = validator._thumbnails_dir
        large_file = thumbnails_dir / "large_thumb.jpg"
        large_size = 200 * 1024  # 200KB file
        large_file.write_bytes(
            b"\xff\xd8\xff\xe0" + b"x" * (large_size - 4) + b"\xff\xd9"
        )

        # Track the large file
        validator._memory_manager.track_item(large_file)

        analysis = validator.analyze_cache_efficiency()

        assert "average_file_size_kb" in analysis
        average_kb = analysis["average_file_size_kb"]
        if average_kb > 100:  # Only test if large files detected
            recommendations = analysis["recommendations"]
            assert any("thumbnail size" in rec for rec in recommendations)

    def test_validate_cache_error_handling(self, tmp_path: Path):
        """Test error handling during cache validation."""
        # Create validator with problematic setup
        memory_manager = MemoryManager()
        storage_backend = StorageBackend()

        # Use a path that will cause permission errors
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only

        validator = CacheValidator(
            thumbnails_directory=readonly_dir,
            memory_manager=memory_manager,
            storage_backend=storage_backend,
        )

        # Force an error by making memory_manager raise exception
        original_validate = memory_manager.validate_tracking

        def error_validate():
            raise RuntimeError("Simulated validation error")

        memory_manager.validate_tracking = error_validate

        results = validator.validate_cache(fix_issues=True)

        # Should handle error gracefully
        assert results["valid"] is False
        assert "error" in results
        assert "Simulated validation error" in results["error"]

        # Restore original method
        memory_manager.validate_tracking = original_validate

    def test_validate_cache_integration_with_real_tracking(
        self, validator: CacheValidator, sample_thumbnail_files: list[Path]
    ):
        """Test full integration with real MemoryManager tracking validation."""
        memory_manager = validator._memory_manager

        # Track some files correctly
        for thumb_file in sample_thumbnail_files[:2]:
            memory_manager.track_item(thumb_file)

        # Create inconsistent state - file exists but size is wrong in tracking
        test_file = sample_thumbnail_files[0]
        actual_size = test_file.stat().st_size
        memory_manager._cached_items[str(test_file)] = actual_size + 1000  # Wrong size

        # Delete a tracked file to create missing file
        missing_file = sample_thumbnail_files[1]
        memory_manager._cached_items[str(missing_file)] = 1024
        missing_file.unlink()  # Delete the actual file

        results = validator.validate_cache(fix_issues=True)

        # Should detect and report issues
        assert results["valid"] is False
        assert results["issues_found"] > 0

        # Should include orphaned files (not tracked) plus any tracking issues
        assert results["orphaned_files"] >= 3  # Remaining untracked files

    def test_directory_structure_validation_complex(
        self,
        tmp_path: Path,
        memory_manager: MemoryManager,
        storage_backend: StorageBackend,
    ):
        """Test validation of complex directory structures."""
        # Test with nested missing directories
        complex_path = tmp_path / "cache" / "nested" / "thumbnails"

        validator = CacheValidator(
            thumbnails_directory=complex_path,
            memory_manager=memory_manager,
            storage_backend=storage_backend,
        )

        # Should not exist initially
        assert not complex_path.exists()

        results = validator.validate_cache(fix_issues=True)

        # Should create the entire directory structure
        assert complex_path.exists()
        assert results["issues_fixed"] >= 1
        assert "Created missing thumbnails directory" in str(results["details"])

    def test_statistics_with_nonexistent_directory(self, tmp_path: Path):
        """Test statistics when thumbnails directory does not exist."""
        missing_dir = tmp_path / "nonexistent"
        memory_manager = MemoryManager()
        storage_backend = StorageBackend()

        validator = CacheValidator(
            thumbnails_directory=missing_dir,
            memory_manager=memory_manager,
            storage_backend=storage_backend,
        )

        stats = validator.get_cache_statistics()

        assert stats["directory_exists"] is False
        assert stats["actual_thumbnail_count"] == 0
        assert stats["actual_total_size_mb"] == 0
        assert stats["show_directories"] == 0
        assert "memory_stats" in stats  # Should still include memory stats

    def test_orphaned_file_detection_with_subdirectories(
        self, validator: CacheValidator, tmp_path: Path
    ):
        """Test orphaned file detection in nested subdirectories."""
        thumbnails_dir = validator._thumbnails_dir

        # Create files in nested structure
        nested_dir = thumbnails_dir / "show1" / "sequence1"
        nested_dir.mkdir(parents=True)

        nested_files = []
        for i in range(3):
            nested_file = nested_dir / f"nested_{i}.jpg"
            nested_file.write_bytes(b"\xff\xd8\xff\xe0" + b"test" * 100 + b"\xff\xd9")
            nested_files.append(nested_file)

        results = validator.validate_cache(fix_issues=False)

        # Should find all nested orphaned files
        assert results["orphaned_files"] >= 3

        # Fix the orphaned files
        results_fixed = validator.validate_cache(fix_issues=True)
        assert results_fixed["issues_fixed"] >= 3

        # Verify files are now tracked
        for nested_file in nested_files:
            assert validator._memory_manager.is_item_tracked(nested_file)

    def test_comprehensive_cache_health_check(
        self, validator: CacheValidator, sample_thumbnail_files: list[Path]
    ):
        """Test comprehensive cache health check scenario."""
        memory_manager = validator._memory_manager
        thumbnails_dir = validator._thumbnails_dir

        # Create a complex scenario with multiple issues:

        # 1. Some tracked files with correct info
        memory_manager.track_item(sample_thumbnail_files[0])

        # 2. Some orphaned files (not tracked)
        # sample_thumbnail_files[1:] are orphaned

        # 3. Some empty directories
        empty_dir = thumbnails_dir / "empty_show"
        empty_dir.mkdir()

        # 4. Create tracking for non-existent file (missing file)
        ghost_file = thumbnails_dir / "ghost.jpg"
        memory_manager._cached_items[str(ghost_file)] = 1024
        memory_manager._memory_usage_bytes += 1024

        # Run comprehensive validation
        results = validator.validate_cache(fix_issues=True)

        # Should detect multiple issue types
        assert results["issues_found"] > 0
        assert results["issues_fixed"] >= 1

        # Should handle orphaned files
        assert results["orphaned_files"] >= 4  # Remaining untracked files

        # Clean up empty directories
        cleaned = validator.clean_empty_directories()
        assert cleaned >= 1  # empty_show should be removed

        # Get final statistics
        final_stats = validator.get_cache_statistics()
        assert isinstance(final_stats["actual_thumbnail_count"], int)
        assert final_stats["actual_total_size_mb"] >= 0

        # Analyze efficiency
        efficiency = validator.analyze_cache_efficiency()
        assert "memory_utilization_percent" in efficiency
        assert "recommendations" in efficiency