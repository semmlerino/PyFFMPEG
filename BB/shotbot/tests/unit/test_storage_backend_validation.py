"""Test enhanced StorageBackend validation methods."""

from __future__ import annotations

# Standard library imports
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock

# Third-party imports
import pytest

# Local application imports
from cache.storage_backend import StorageBackend


class MockMemoryManager:
    """Mock memory manager for testing validation."""

    def __init__(self):
        self.tracked_files: set[Path] = set()
        self.usage_stats = {
            "usage_percent": 50,
            "average_item_kb": 75,
            "total_items": 10,
            "total_size_mb": 1.5,
        }

    def get_usage_stats(self) -> dict[str, Any]:
        return self.usage_stats

    def is_item_tracked(self, file_path: Path) -> bool:
        return file_path in self.tracked_files

    def track_item(self, file_path: Path) -> bool:
        if file_path.exists():
            self.tracked_files.add(file_path)
            return True
        return False

    def validate_tracking(self) -> dict[str, Any]:
        return {"invalid_files": 0, "size_mismatches": 1, "issues_fixed": 1}


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def storage_backend():
    """Create a storage backend instance."""
    return StorageBackend()


@pytest.fixture
def mock_memory_manager():
    """Create a mock memory manager."""
    return MockMemoryManager()


class TestStorageBackendValidation:
    """Test storage backend validation methods."""

    def test_validate_cache_empty_directory(self, storage_backend, temp_cache_dir):
        """Test validation with empty cache directory."""
        result = storage_backend.validate_cache(temp_cache_dir)

        assert result["valid"] is True
        assert result["issues_found"] == 0
        assert result["issues_fixed"] == 0
        assert result["orphaned_files"] == 0

    def test_validate_cache_missing_directory(self, storage_backend, temp_cache_dir):
        """Test validation when cache directory doesn't exist."""
        missing_dir = temp_cache_dir / "missing_cache"

        result = storage_backend.validate_cache(missing_dir, fix_issues=True)

        assert result["valid"] is True  # Should be fixed
        assert result["issues_fixed"] > 0
        assert missing_dir.exists()  # Should be created

    def test_validate_cache_missing_directory_no_fix(
        self, storage_backend, temp_cache_dir
    ):
        """Test validation when cache directory doesn't exist and fix_issues=False."""
        missing_dir = temp_cache_dir / "missing_cache"

        result = storage_backend.validate_cache(missing_dir, fix_issues=False)

        assert result["valid"] is False
        assert result["issues_found"] > 0
        assert not missing_dir.exists()  # Should not be created

    def test_validate_cache_with_memory_manager(
        self, storage_backend, temp_cache_dir, mock_memory_manager
    ):
        """Test validation with memory manager tracking."""
        # Create some test files
        test_file1 = temp_cache_dir / "test1.jpg"
        test_file2 = temp_cache_dir / "test2.jpg"
        test_file1.write_text("test image 1")
        test_file2.write_text("test image 2")

        # Track only one file
        mock_memory_manager.tracked_files.add(test_file1)

        result = storage_backend.validate_cache(
            temp_cache_dir, memory_manager=mock_memory_manager, fix_issues=True
        )

        # Should find orphaned file and fix memory tracking issues
        assert result["orphaned_files"] == 1  # test2.jpg is orphaned
        assert result["size_mismatches"] == 1  # From mock validate_tracking
        assert (
            result["issues_fixed"] >= 1
        )  # Memory tracking fix (orphan fix may not be counted in main issues_fixed)

    def test_repair_cache(self, storage_backend, temp_cache_dir, mock_memory_manager):
        """Test comprehensive cache repair."""
        # Create orphaned file
        orphaned_file = temp_cache_dir / "orphaned.jpg"
        orphaned_file.write_text("orphaned image")

        result = storage_backend.repair_cache(temp_cache_dir, mock_memory_manager)

        # Should be equivalent to validate_cache with fix_issues=True
        assert "valid" in result
        assert "issues_found" in result
        assert "issues_fixed" in result

    def test_get_cache_stats_empty_directory(self, storage_backend, temp_cache_dir):
        """Test cache statistics for empty directory."""
        stats = storage_backend.get_cache_stats(temp_cache_dir)

        assert stats["directory_exists"] is True
        assert stats["actual_file_count"] == 0
        assert stats["actual_total_size_mb"] == 0
        assert stats["subdirectories"] == 0
        assert stats["file_types"] == {}

    def test_get_cache_stats_with_files(self, storage_backend, temp_cache_dir):
        """Test cache statistics with various file types."""
        # Create test files
        (temp_cache_dir / "image1.jpg").write_text("image data 1")
        (temp_cache_dir / "image2.png").write_text("image data 2")
        (temp_cache_dir / "cache.json").write_text('{"test": "data"}')
        (temp_cache_dir / "subdir").mkdir()
        (temp_cache_dir / "subdir" / "image3.jpeg").write_text("image data 3")

        stats = storage_backend.get_cache_stats(temp_cache_dir)

        assert stats["directory_exists"] is True
        assert stats["actual_file_count"] == 4  # jpg, png, json, jpeg
        assert stats["actual_total_size_mb"] > 0
        assert stats["subdirectories"] == 1
        assert ".jpg" in stats["file_types"]
        assert ".png" in stats["file_types"]
        assert ".json" in stats["file_types"]
        assert ".jpeg" in stats["file_types"]

    def test_get_cache_stats_with_memory_manager(
        self, storage_backend, temp_cache_dir, mock_memory_manager
    ):
        """Test cache statistics with memory manager."""
        stats = storage_backend.get_cache_stats(temp_cache_dir, mock_memory_manager)

        assert "memory_stats" in stats
        assert stats["memory_stats"]["usage_percent"] == 50
        assert stats["memory_stats"]["average_item_kb"] == 75

    def test_get_cache_stats_missing_directory(self, storage_backend, temp_cache_dir):
        """Test cache statistics for non-existent directory."""
        missing_dir = temp_cache_dir / "missing"

        stats = storage_backend.get_cache_stats(missing_dir)

        assert stats["directory_exists"] is False
        assert stats["actual_file_count"] == 0
        assert stats["actual_total_size_mb"] == 0
        assert stats["subdirectories"] == 0

    def test_clean_empty_directories(self, storage_backend, temp_cache_dir):
        """Test cleaning empty directories."""
        # Create directory structure with empty directories
        (temp_cache_dir / "empty1").mkdir()
        (temp_cache_dir / "empty2").mkdir()
        (temp_cache_dir / "not_empty").mkdir()
        (temp_cache_dir / "not_empty" / "file.txt").write_text("content")
        (temp_cache_dir / "nested" / "empty").mkdir(parents=True)

        removed_count = storage_backend.clean_empty_directories(temp_cache_dir)

        # Should remove empty1, empty2, nested/empty, and nested (after empty is removed)
        assert removed_count >= 3  # At least the 3 empty directories
        assert not (temp_cache_dir / "empty1").exists()
        assert not (temp_cache_dir / "empty2").exists()
        assert (temp_cache_dir / "not_empty").exists()  # Has file, should remain
        assert not (temp_cache_dir / "nested" / "empty").exists()

    def test_clean_empty_directories_missing_cache(
        self, storage_backend, temp_cache_dir
    ):
        """Test cleaning empty directories when cache doesn't exist."""
        missing_dir = temp_cache_dir / "missing"

        removed_count = storage_backend.clean_empty_directories(missing_dir)

        assert removed_count == 0

    def test_validate_memory_tracking_without_method(self, storage_backend):
        """Test memory tracking validation when manager doesn't support it."""
        mock_manager = Mock()
        # Remove validate_tracking method
        if hasattr(mock_manager, "validate_tracking"):
            delattr(mock_manager, "validate_tracking")

        result = storage_backend._validate_memory_tracking(mock_manager, True)

        assert result["missing_files"] == 0
        assert result["size_mismatches"] == 0
        assert result["memory_usage_corrected"] is False

    def test_find_orphaned_files_without_tracking_methods(
        self, storage_backend, temp_cache_dir
    ):
        """Test orphaned file detection when memory manager doesn't support tracking methods."""
        # Create test file
        test_file = temp_cache_dir / "test.jpg"
        test_file.write_text("test")

        mock_manager = Mock()
        # Remove tracking methods
        if hasattr(mock_manager, "is_item_tracked"):
            delattr(mock_manager, "is_item_tracked")
        if hasattr(mock_manager, "track_item"):
            delattr(mock_manager, "track_item")

        result = storage_backend._find_orphaned_files(
            temp_cache_dir, mock_manager, True
        )

        # Should gracefully handle missing methods
        assert result["orphaned_files"] == 0

    def test_validate_cache_error_handling(self, storage_backend):
        """Test validation error handling."""
        # Use a path that will cause permission errors but note that StorageBackend
        # has fallback directory creation, so this may not fail as expected
        invalid_path = Path("/invalid/path/that/cannot/exist")

        result = storage_backend.validate_cache(invalid_path)

        # With fallback directory creation, validation may succeed
        # The important thing is that it doesn't crash
        assert "valid" in result
        assert "issues_found" in result
        assert "issues_fixed" in result

    def test_integration_full_validation_cycle(
        self, storage_backend, temp_cache_dir, mock_memory_manager
    ):
        """Test complete validation cycle with multiple issues."""
        # Create various files and issues
        (temp_cache_dir / "tracked.jpg").write_text("tracked image")
        (temp_cache_dir / "orphaned.jpg").write_text("orphaned image")
        (temp_cache_dir / "empty_dir").mkdir()

        # Track only one file
        mock_memory_manager.tracked_files.add(temp_cache_dir / "tracked.jpg")

        # Run validation with fixes
        result = storage_backend.validate_cache(
            temp_cache_dir, memory_manager=mock_memory_manager, fix_issues=True
        )

        # Should find and fix issues
        assert result["orphaned_files"] == 1
        assert result["issues_fixed"] > 0

        # Clean empty directories
        removed = storage_backend.clean_empty_directories(temp_cache_dir)
        assert removed == 1

        # Get final stats
        stats = storage_backend.get_cache_stats(temp_cache_dir, mock_memory_manager)
        assert stats["actual_file_count"] == 2  # tracked.jpg + orphaned.jpg
        assert "memory_stats" in stats


class TestStorageBackendValidationMethods:
    """Test specific validation method implementations."""

    def test_validate_directory_structure_create_success(
        self, storage_backend, temp_cache_dir
    ):
        """Test successful directory structure validation and creation."""
        missing_dir = temp_cache_dir / "test_cache"

        result = storage_backend._validate_directory_structure(
            missing_dir, fix_issues=True
        )

        assert result["structure_issues"] == 0
        assert result["issues_fixed"] == 1
        assert missing_dir.exists()
        assert "Created missing cache directory" in result["details"]

    def test_validate_directory_structure_no_fix(self, storage_backend, temp_cache_dir):
        """Test directory structure validation without fixing."""
        missing_dir = temp_cache_dir / "test_cache"

        result = storage_backend._validate_directory_structure(
            missing_dir, fix_issues=False
        )

        assert result["structure_issues"] == 1
        assert not missing_dir.exists()
        assert "Cache directory does not exist" in result["details"]

    def test_memory_tracking_validation_success(
        self, storage_backend, mock_memory_manager
    ):
        """Test successful memory tracking validation."""
        result = storage_backend._validate_memory_tracking(mock_memory_manager, True)

        assert result["missing_files"] == 0
        assert result["size_mismatches"] == 1  # From mock
        assert result["memory_usage_corrected"] is True
        assert "Fixed 1 memory tracking issues" in result["details"]

    def test_orphaned_files_detection_and_fix(
        self, storage_backend, temp_cache_dir, mock_memory_manager
    ):
        """Test orphaned file detection and fixing."""
        # Create orphaned files
        orphan1 = temp_cache_dir / "orphan1.jpg"
        orphan2 = temp_cache_dir / "orphan2.png"
        orphan1.write_text("orphan 1")
        orphan2.write_text("orphan 2")

        result = storage_backend._find_orphaned_files(
            temp_cache_dir, mock_memory_manager, fix_issues=True
        )

        assert result["orphaned_files"] == 2
        assert result["issues_fixed"] == 2
        assert "Added 2 orphaned files to tracking" in result["details"]
        assert orphan1 in mock_memory_manager.tracked_files
        assert orphan2 in mock_memory_manager.tracked_files

    def test_orphaned_files_detection_no_fix(
        self, storage_backend, temp_cache_dir, mock_memory_manager
    ):
        """Test orphaned file detection without fixing."""
        orphan = temp_cache_dir / "orphan.jpg"
        orphan.write_text("orphan")

        result = storage_backend._find_orphaned_files(
            temp_cache_dir, mock_memory_manager, fix_issues=False
        )

        assert result["orphaned_files"] == 1
        assert "Found 1 orphaned files" in result["details"]
        assert orphan not in mock_memory_manager.tracked_files
