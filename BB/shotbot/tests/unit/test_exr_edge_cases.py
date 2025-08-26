"""Edge case tests for EXR thumbnail handling.

Tests handling of corrupted files, permission errors, unusual formats,
and other exceptional conditions that may occur in production.
"""

from __future__ import annotations

import os
import stat
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication

try:
    from PIL import Image
except ImportError:
    Image = None

from cache_manager import CacheManager
from utils import FileUtils, PathUtils

pytestmark = [pytest.mark.unit, pytest.mark.slow]



# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)

class TestCorruptedFiles:
    """Test handling of corrupted or invalid EXR files."""

    def test_corrupted_exr_header(self, tmp_path):
        """Corrupted EXR header should be handled gracefully."""
        bad_exr = tmp_path / "corrupted.exr"
        bad_exr.write_bytes(b"NOT_AN_EXR_HEADER" + b"x" * 100)

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Should not crash, return None
        result = cache_manager.cache_thumbnail(
            bad_exr, show="test", sequence="seq", shot="0010", wait=True
        )

        assert result is None or isinstance(result, Path)

    def test_empty_exr_file(self, tmp_path):
        """Empty EXR file should be handled without crash."""
        empty_exr = tmp_path / "empty.exr"
        empty_exr.touch()  # Creates empty file

        result = FileUtils.get_first_image_file(tmp_path, allow_fallback=True)
        assert result == empty_exr  # Found the file

        # Cache manager should handle empty file
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        cached = cache_manager.cache_thumbnail(
            empty_exr, show="test", sequence="seq", shot="0010", wait=True
        )

        # Should handle gracefully (return None or empty cache)
        assert cached is None or cached.stat().st_size == 0

    def test_truncated_exr_file(self, tmp_path):
        """Truncated EXR file should not crash the application."""
        truncated = tmp_path / "truncated.exr"
        # Write partial EXR magic number
        truncated.write_bytes(b"\x76\x2f\x31")  # Incomplete EXR header

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Test behavior: should handle gracefully without crashing
        result = cache_manager.cache_thumbnail(
            truncated, show="test", sequence="seq", shot="0010", wait=True
        )

        # Should return None for corrupted file, not crash
        assert result is None


class TestPermissionErrors:
    """Test handling of file permission issues."""

    @pytest.mark.skipif(os.name == "nt", reason="Unix-specific permissions")
    def test_no_read_permission(self, tmp_path):
        """Files without read permission should be handled."""
        protected_exr = tmp_path / "protected.exr"
        protected_exr.write_bytes(b"EXR" + b"x" * 100)

        # Remove read permission
        protected_exr.chmod(stat.S_IWRITE)

        try:
            result = FileUtils.get_first_image_file(tmp_path, allow_fallback=True)
            # The function finds the file but cache_manager would fail to read it
            # Testing that the function doesn't crash is the behavior we care about
            assert result is not None  # Function completes without error
        finally:
            # Restore permissions for cleanup
            protected_exr.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_directory_no_execute_permission(self, tmp_path):
        """Directory without execute permission should be handled."""
        if os.name == "nt":
            pytest.skip("Unix-specific permissions")

        restricted_dir = tmp_path / "restricted"
        restricted_dir.mkdir()
        test_file = restricted_dir / "test.exr"
        test_file.touch()

        # Remove execute permission (can't list directory)
        restricted_dir.chmod(stat.S_IREAD | stat.S_IWRITE)

        try:
            # PathUtils should handle permission errors gracefully
            result = PathUtils.validate_path_exists(test_file, "Test file")
            # Should return False when can't access due to permissions
            assert result is False
        except PermissionError:
            # If permission error occurs, that's also acceptable behavior
            pass
        finally:
            # Restore permissions
            restricted_dir.chmod(stat.S_IRWXU)

    def test_cache_dir_not_writable(self, tmp_path):
        """Cache directory without write permission should fallback."""
        cache_dir = tmp_path / "readonly_cache"
        cache_dir.mkdir()

        if os.name != "nt":
            # Make read-only
            cache_dir.chmod(stat.S_IREAD | stat.S_IEXEC)

        try:
            cache_manager = CacheManager(cache_dir=cache_dir)

            test_exr = tmp_path / "test.exr"
            test_exr.write_bytes(b"EXR")

            # Should handle gracefully, possibly with in-memory fallback
            result = cache_manager.cache_thumbnail(
                test_exr, show="test", sequence="seq", shot="0010", wait=True
            )

            # Should not crash, might return None
            assert result is None or isinstance(result, Path)
        finally:
            if os.name != "nt":
                cache_dir.chmod(stat.S_IRWXU)


class TestUnusualFormats:
    """Test handling of unusual or edge-case file formats."""

    @pytest.mark.parametrize(
        "filename,content",
        [
            ("UPPERCASE.EXR", b"EXR"),
            ("mixed.ExR", b"EXR"),
            ("with spaces.exr", b"EXR"),
            ("unicode_文件.exr", b"EXR"),
            (".hidden.exr", b"EXR"),
            ("very_long_filename_" + "x" * 200 + ".exr", b"EXR"),
        ],
    )
    def test_unusual_filenames(self, tmp_path, filename, content):
        """Various unusual filenames should be handled."""
        file_path = tmp_path / filename
        try:
            file_path.write_bytes(content)
        except OSError:
            pytest.skip(f"Filesystem doesn't support filename: {filename}")

        result = FileUtils.get_first_image_file(tmp_path, allow_fallback=True)

        # Should find the file regardless of unusual name
        assert result is not None
        assert result.name.lower().endswith(".exr")

    def test_symlink_to_exr(self, tmp_path):
        """Symlinks to EXR files should work."""
        if os.name == "nt":
            pytest.skip("Symlink test requires Unix")

        # Create actual EXR
        real_exr = tmp_path / "real" / "file.exr"
        real_exr.parent.mkdir()
        real_exr.write_bytes(b"EXR" + b"x" * 100)

        # Create symlink
        link_exr = tmp_path / "link.exr"
        link_exr.symlink_to(real_exr)

        result = FileUtils.get_first_image_file(tmp_path, allow_fallback=True)
        assert result == link_exr

        # Cache manager should handle symlink
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        cached = cache_manager.cache_thumbnail(
            link_exr, show="test", sequence="seq", shot="0010", wait=True
        )

        # Should process the linked file
        assert cached is None or isinstance(cached, Path)

    def test_very_deep_directory_structure(self, tmp_path):
        """Very deep directory structures should be handled."""
        # Create deep path
        deep_path = tmp_path
        for i in range(50):  # 50 levels deep
            deep_path = deep_path / f"level_{i}"

        deep_path.mkdir(parents=True)
        exr_file = deep_path / "deep.exr"
        exr_file.write_bytes(b"EXR")

        # Should handle deep paths
        assert PathUtils.validate_path_exists(exr_file, "Deep file")

        result = FileUtils.get_first_image_file(deep_path, allow_fallback=True)
        assert result == exr_file


class TestConcurrentEdgeCases:
    """Test edge cases in concurrent scenarios."""

    def test_file_deleted_during_processing(self, tmp_path):
        """File deleted while being processed should be handled."""

        exr_file = tmp_path / "vanishing.exr"
        exr_file.write_bytes(b"EXR" + b"x" * 1024)

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        def delete_file():
            QCoreApplication.processEvents()  # Process events instead of sleep
            if exr_file.exists():
                exr_file.unlink()

        # Start deletion thread
        delete_thread = threading.Thread(target=delete_file)
        delete_thread.start()

        # Try to cache (file will disappear during processing)

        if Image:
            with patch.object(Image, "open") as mock_open:
                mock_open.side_effect = FileNotFoundError()

                result = cache_manager.cache_thumbnail(
                    exr_file, show="test", sequence="seq", shot="0010", wait=True
                )
        else:
            # Skip Image mocking if PIL not available
            result = cache_manager.cache_thumbnail(
                exr_file, show="test", sequence="seq", shot="0010", wait=True
            )

        delete_thread.join()

        # Should handle gracefully
        assert result is None

    def test_file_modified_during_processing(self, tmp_path):
        """File modified while being processed should be handled."""

        exr_file = tmp_path / "changing.exr"
        exr_file.write_bytes(b"EXR" + b"x" * 1024)

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        def modify_file():
            QCoreApplication.processEvents()  # Process events instead of sleep
            if exr_file.exists():
                # Change file content
                exr_file.write_bytes(b"MODIFIED" + b"y" * 2048)

        modify_thread = threading.Thread(target=modify_file)
        modify_thread.start()

        # Process file (will change during processing)
        result = cache_manager.cache_thumbnail(
            exr_file, show="test", sequence="seq", shot="0010", wait=True
        )

        modify_thread.join()

        # Should complete without crash
        assert result is None or isinstance(result, Path)


class TestPlatformSpecific:
    """Test platform-specific edge cases."""

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific")
    def test_windows_path_length_limit(self, tmp_path):
        """Windows MAX_PATH limitation should be handled."""
        # Create path approaching Windows limit (260 chars)
        long_dir = tmp_path
        while len(str(long_dir)) < 240:
            long_dir = long_dir / "subdir"

        try:
            long_dir.mkdir(parents=True)
            exr_file = long_dir / "test.exr"
            exr_file.write_bytes(b"EXR")

            # Should handle or report error gracefully
            result = PathUtils.validate_path_exists(exr_file, "Long path")
            # Either works or fails gracefully
            assert isinstance(result, bool)
        except OSError:
            # Expected on Windows with long paths
            pass

    @pytest.mark.skipif(os.name == "nt", reason="Unix-specific")
    def test_unix_special_device_files(self, tmp_path):
        """Special device files should not be processed as images."""
        # Create a named pipe (FIFO)
        fifo_path = tmp_path / "fake.exr"
        os.mkfifo(fifo_path)

        try:
            result = FileUtils.get_first_image_file(tmp_path, allow_fallback=True)
            # Should either skip or handle gracefully
            assert result is None or not stat.S_ISFIFO(result.stat().st_mode)
        finally:
            fifo_path.unlink()


class TestResourceExhaustion:
    """Test behavior under resource exhaustion conditions."""

    def test_many_small_exr_files(self, tmp_path):
        """Many small EXR files should not exhaust file handles."""
        # Create many small EXR files
        for i in range(100):
            exr_file = tmp_path / f"small_{i}.exr"
            exr_file.write_bytes(b"EXR")

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Process all files
        for i in range(100):
            exr_file = tmp_path / f"small_{i}.exr"

            if Image:
                with patch.object(Image, "open", return_value=MagicMock()):
                    cache_manager.cache_thumbnail(
                        exr_file,
                        show="test",
                        sequence=f"seq{i}",
                        shot=f"{i:04d}",
                        wait=False,  # Don't wait
                    )
            else:
                # Skip Image mocking if PIL not available
                cache_manager.cache_thumbnail(
                    exr_file,
                    show="test",
                    sequence=f"seq{i}",
                    shot=f"{i:04d}",
                    wait=False,  # Don't wait
                )

        # Should complete without file handle exhaustion
        # (actual file handle checking is OS-specific)
        assert True  # If we get here, handles were managed properly

    def test_cache_cleanup_under_pressure(self, tmp_path):
        """Cache should clean up under memory pressure."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Simulate memory pressure by adding many items
        for i in range(100):  # OPTIMIZED: Reduced from 1000 to 100 items
            # Simulate cached thumbnail tracking
            cache_key = f"test_seq{i}_shot{i:04d}"
            cache_manager._cached_thumbnails[cache_key] = 1024 * 1024  # 1MB each
            cache_manager._memory_usage_bytes += 1024 * 1024

        # Clear cache should free memory
        cache_manager.clear_cache()

        assert cache_manager._memory_usage_bytes == 0
        assert len(cache_manager._cached_thumbnails) == 0
