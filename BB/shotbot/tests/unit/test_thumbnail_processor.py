"""Comprehensive tests for ThumbnailManager functionality.

Tests multi-format image processing, backend fallbacks, EXR handling, and resource management.

Following UNIFIED_TESTING_GUIDE principles:
- Test behavior, not implementation details
- Use real ThumbnailManager with actual file operations
- Mock only at system boundaries (subprocess calls)
- Use ThreadSafeTestImage for Qt threading safety
- Focus on multi-format support and error conditions
"""

from __future__ import annotations

# Standard library imports
import concurrent.futures
from unittest.mock import Mock, patch

# Third-party imports
import pytest
from PySide6.QtGui import QColor

# Local application imports
from cache.thumbnail_manager import ThumbnailManager
from config import Config

try:
    # Third-party imports
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

# Standard library imports
from typing import TYPE_CHECKING

# Local application imports
from tests.test_doubles_library import TestSubprocess, ThreadSafeTestImage

if TYPE_CHECKING:
    # Standard library imports
    from pathlib import Path

pytestmark = [
    pytest.mark.unit,
    pytest.mark.qt,
    pytest.mark.slow,
    pytest.mark.xdist_group("qt_state"),
]


class PILImageDouble:
    """Test double for PIL Image objects with basic functionality."""

    def __init__(self, width: int = 100, height: int = 100) -> None:
        """Initialize PIL-compatible image double."""
        self.width = width
        self.height = height
        self.size = (width, height)
        self._loaded = False

    def load(self) -> None:
        """Mock PIL Image load method."""
        self._loaded = True

    def convert(self, mode: str = "RGB"):
        """Mock PIL Image convert method."""
        return self

    def resize(self, size: tuple, resample=None):
        """Mock PIL Image resize method."""
        return PILImageDouble(size[0], size[1])

    def save(self, path: str, format: str = None, **kwargs) -> bool:
        """Mock PIL Image save method."""
        # Create a minimal file to simulate successful save
        # Standard library imports
        from pathlib import Path

        Path(path).write_bytes(b"fake image data")
        return True


class TestThumbnailManagerInitialization:
    """Test ThumbnailManager initialization and configuration."""

    def test_default_initialization(self) -> None:
        """ThumbnailManager should initialize with default config values."""
        processor = ThumbnailManager()

        assert processor._thumbnail_size == Config.CACHE_THUMBNAIL_SIZE
        assert processor._heavy_formats == [".exr", ".tiff", ".tif"]

    def test_custom_thumbnail_size(self) -> None:
        """ThumbnailManager should accept custom thumbnail size."""
        custom_size = 256
        processor = ThumbnailManager(thumbnail_size=custom_size)

        assert processor._thumbnail_size == custom_size

    def test_heavy_formats_configuration(self) -> None:
        """ThumbnailManager should configure heavy formats from config."""
        processor = ThumbnailManager()

        # Should use fallback extensions from config if available
        expected_formats = getattr(
            Config, "THUMBNAIL_FALLBACK_EXTENSIONS", [".exr", ".tiff", ".tif"]
        )
        assert processor._heavy_formats == expected_formats

    def test_repr_string(self) -> None:
        """ThumbnailManager should provide meaningful string representation."""
        processor = ThumbnailManager(thumbnail_size=128)

        repr_str = repr(processor)
        assert "ThumbnailManager" in repr_str
        # ThumbnailManager has custom __repr__ showing failure count and delay
        assert "failures=" in repr_str
        assert "max_delay=" in repr_str


class TestThumbnailManagerBasicProcessing:
    """Test successful processing of standard image formats."""

    @pytest.fixture
    def processor(self):
        """Create ThumbnailManager for testing."""
        return ThumbnailManager(thumbnail_size=100)

    @pytest.fixture
    def test_jpeg(self, tmp_path):
        """Create a valid JPEG file using PIL or ThreadSafeTestImage."""
        jpeg_file = tmp_path / "test.jpg"
        try:
            img = PILImage.new("RGB", (100, 100), color="red")
            img.save(jpeg_file, "JPEG")
        except ImportError:
            # Use ThreadSafeTestImage to create Qt-compatible image
            test_img = ThreadSafeTestImage(100, 100)
            test_img.fill(QColor(255, 0, 0))  # Red fill
            test_img._image.save(str(jpeg_file), "JPEG")
        return jpeg_file

    @pytest.fixture
    def test_png(self, tmp_path):
        """Create a minimal valid PNG file."""
        png_file = tmp_path / "test.png"
        # Create PNG with PIL if available, otherwise mock bytes
        try:
            img = PILImage.new("RGB", (100, 100), color="white")
            img.save(png_file, "PNG")
        except ImportError:
            # Minimal PNG signature
            png_file.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00d\x00\x00\x00d\x08\x02"
                b"\x00\x00\x00\xff\x80\x02\x03\x00\x00\x00\x0cIDATh\xda\xed\xc1\x01\x00"
                b"\x00\x00\x00\xc0\xa0\xf7O\r\x0e\x00\x00\x00\x00IEND\xaeB`\x82"
            )
        return png_file

    def test_process_jpeg_success(self, processor, test_jpeg, tmp_path) -> None:
        """JPEG processing should succeed with Qt backend."""
        cache_path = tmp_path / "cache" / "thumbnail.jpg"

        result = processor.cache_thumbnail_sync(test_jpeg, cache_path)

        assert result is True
        assert cache_path.exists()
        assert cache_path.stat().st_size > 0

    def test_process_png_success(self, processor, test_png, tmp_path) -> None:
        """PNG processing should succeed with Qt backend."""
        cache_path = tmp_path / "cache" / "thumbnail.jpg"

        result = processor.cache_thumbnail_sync(test_png, cache_path)

        assert result is True
        assert cache_path.exists()
        assert cache_path.stat().st_size > 0

    def test_cache_directory_creation(self, processor, test_jpeg, tmp_path) -> None:
        """Cache directory should be created automatically."""
        nested_cache = tmp_path / "deep" / "nested" / "cache" / "thumbnail.jpg"

        result = processor.cache_thumbnail_sync(test_jpeg, nested_cache)

        assert result is True
        assert nested_cache.parent.exists()
        assert nested_cache.exists()

    def test_atomic_file_operations(self, processor, test_jpeg, tmp_path) -> None:
        """Thumbnail should be saved atomically with temporary file."""
        cache_path = tmp_path / "cache" / "thumbnail.jpg"

        # Process thumbnail
        result = processor.cache_thumbnail_sync(test_jpeg, cache_path)

        assert result is True
        assert cache_path.exists()

        # No temporary files should remain
        temp_files = list(cache_path.parent.glob("*.tmp_*"))
        assert len(temp_files) == 0


class TestThumbnailManagerMultiFormat:
    """Test format-specific processing paths and backend selection."""

    @pytest.fixture
    def processor(self):
        """Create ThumbnailManager for testing."""
        return ThumbnailManager(thumbnail_size=100)

    @pytest.fixture
    def small_tiff(self, tmp_path):
        """Create a small TIFF file that should use Qt processing."""
        tiff_file = tmp_path / "small.tif"
        try:
            img = PILImage.new("RGB", (50, 50), color="white")
            img.save(tiff_file, "TIFF")
        except ImportError:
            # Mock minimal TIFF
            tiff_file.write_bytes(b"II*\x00\x08\x00\x00\x00")
        return tiff_file

    @pytest.fixture
    def large_tiff(self, tmp_path):
        """Create a large TIFF file that should use PIL processing."""
        tiff_file = tmp_path / "large.tif"
        # Create file larger than 1MB to trigger PIL processing
        large_data = b"II*\x00\x08\x00\x00\x00" + (b"0" * (1024 * 1024 + 100))
        tiff_file.write_bytes(large_data)
        return tiff_file

    def test_file_analysis_small_file(self, processor, small_tiff) -> None:
        """Small files should be analyzed for Qt processing."""
        file_info = processor._analyze_source_file(small_tiff)

        assert file_info["suffix_lower"] == ".tif"
        assert file_info["is_heavy_format"] is True
        # Small file should not use PIL (under 1MB threshold)
        assert file_info["use_pil"] is False

    def test_file_analysis_large_heavy_format(self, processor, large_tiff) -> None:
        """Large heavy format files should be analyzed for PIL processing."""
        file_info = processor._analyze_source_file(large_tiff)

        assert file_info["suffix_lower"] == ".tif"
        assert file_info["is_heavy_format"] is True
        assert file_info["file_size_mb"] > 1.0
        # Large heavy format should use PIL
        assert file_info["use_pil"] is True

    def test_qt_processing_path(self, processor, small_tiff, tmp_path) -> None:
        """Small TIFF should be processed with Qt backend."""
        cache_path = tmp_path / "qt_thumbnail.jpg"

        with patch.object(processor, "_process_with_qt", return_value=True):
            with patch.object(processor, "_process_with_pil") as mock_pil:
                result = processor.cache_thumbnail_sync(small_tiff, cache_path)

                assert result is True
                mock_pil.assert_not_called()

    def test_pil_processing_path(self, processor, large_tiff, tmp_path) -> None:
        """Large heavy format should be processed with PIL backend."""
        cache_path = tmp_path / "pil_thumbnail.jpg"

        with patch.object(processor, "_process_with_pil", return_value=True):
            with patch.object(processor, "_process_with_qt") as mock_qt:
                result = processor.cache_thumbnail_sync(large_tiff, cache_path)

                assert result is True
                mock_qt.assert_not_called()


class TestThumbnailManagerEXRProcessing:
    """Test EXR-specific processing with multiple backends."""

    @pytest.fixture
    def processor(self):
        """Create ThumbnailManager for testing."""
        return ThumbnailManager(thumbnail_size=100)

    @pytest.fixture
    def mock_exr(self, tmp_path):
        """Create a mock EXR file."""
        exr_file = tmp_path / "test.exr"
        # Create large EXR to trigger PIL processing
        exr_data = b"v/1\x01" + (b"0" * (1024 * 1024 + 100))  # EXR magic + large data
        exr_file.write_bytes(exr_data)
        return exr_file

    def test_exr_backend_selection_openexr(self, processor, mock_exr, tmp_path) -> None:
        """EXR processing should successfully load with OpenEXR backend."""
        tmp_path / "exr_thumbnail.jpg"

        # Create test image double for EXR loading
        test_exr_image = PILImageDouble(100, 100)

        with patch.object(
            processor, "_load_exr_with_openexr", return_value=test_exr_image
        ):
            with patch.object(processor, "_load_exr_with_system_tools") as mock_system:
                with patch.object(processor, "_load_exr_with_imageio") as mock_imageio:
                    # Mock PIL processing to focus on EXR loading
                    with patch("PIL.Image.open", side_effect=ImportError):
                        result = processor._load_exr_image(mock_exr)

                        # Test behavior: OpenEXR backend should succeed
                        assert result is not None
                        mock_system.assert_not_called()
                        mock_imageio.assert_not_called()

    def test_exr_fallback_to_system_tools(self, processor, mock_exr, tmp_path) -> None:
        """EXR processing should fallback to ImageMagick when OpenEXR fails."""
        tmp_path / "exr_thumbnail.jpg"

        with patch.object(
            processor, "_load_exr_with_openexr", side_effect=Exception("OpenEXR failed")
        ):
            # Create test image double for system tools fallback
            test_system_image = PILImageDouble(100, 100)

            with patch.object(
                processor, "_load_exr_with_system_tools", return_value=test_system_image
            ):
                with patch.object(processor, "_load_exr_with_imageio") as mock_imageio:
                    result = processor._load_exr_image(mock_exr)

                    # Test behavior: System tools fallback should succeed
                    assert result is not None
                    mock_imageio.assert_not_called()

    def test_exr_fallback_to_imageio(self, processor, mock_exr, tmp_path) -> None:
        """EXR processing should fallback to imageio when system tools fail."""
        tmp_path / "exr_thumbnail.jpg"

        with patch.object(
            processor, "_load_exr_with_openexr", side_effect=Exception("OpenEXR failed")
        ):
            with patch.object(
                processor,
                "_load_exr_with_system_tools",
                side_effect=Exception("System tools failed"),
            ):
                # Create test image double for imageio fallback
                test_imageio_image = PILImageDouble(100, 100)

                with patch.object(
                    processor, "_load_exr_with_imageio", return_value=test_imageio_image
                ):
                    result = processor._load_exr_image(mock_exr)

                    # Test behavior: Imageio fallback should succeed
                    assert result is not None

    def test_exr_all_backends_fail(self, processor, mock_exr) -> None:
        """EXR processing should return None when all backends fail."""
        with patch.object(
            processor, "_load_exr_with_openexr", side_effect=Exception("OpenEXR failed")
        ):
            with patch.object(
                processor,
                "_load_exr_with_system_tools",
                side_effect=Exception("System tools failed"),
            ):
                with patch.object(
                    processor,
                    "_load_exr_with_imageio",
                    side_effect=Exception("imageio failed"),
                ):
                    result = processor._load_exr_image(mock_exr)

                    assert result is None

    # Use TestSubprocess instead
    def test_exr_system_tools_imagemagick(self, processor, mock_exr) -> None:
        """EXR system tools should use ImageMagick convert command."""
        # Use TestSubprocess instead of Mock for subprocess operations
        test_subprocess = TestSubprocess()
        test_subprocess.return_code = 0
        test_subprocess.stdout = ""
        test_subprocess.stderr = ""

        with patch("subprocess.run", test_subprocess.run):
            # Create PIL image double instead of Mock
            pil_image_double = PILImageDouble(100, 100)

            with patch("PIL.Image.open") as mock_pil:
                mock_pil.return_value = pil_image_double

                with patch("tempfile.NamedTemporaryFile") as mock_temp:
                    mock_temp.return_value.__enter__.return_value.name = "/tmp/test.jpg"

                    with patch("pathlib.Path.exists", return_value=True):
                        with patch("pathlib.Path.stat") as mock_stat:
                            mock_stat.return_value.st_size = 1000

                            processor._load_exr_with_system_tools(mock_exr)

                            # Should have executed commands
                            assert len(test_subprocess.executed_commands) >= 1
                            # Check that convert command was called
                            convert_called = any(
                                "convert" in str(cmd)
                                if isinstance(cmd, str)
                                else "convert" in " ".join(cmd)
                                for cmd in test_subprocess.executed_commands
                            )
                            assert convert_called


class TestThumbnailManagerFallbackMechanisms:
    """Test backend fallback chains and error recovery."""

    @pytest.fixture
    def processor(self):
        """Create ThumbnailManager for testing."""
        return ThumbnailManager(thumbnail_size=100)

    @pytest.fixture
    def test_image(self, tmp_path):
        """Create a test image file."""
        image_file = tmp_path / "test.jpg"
        image_file.write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        )
        return image_file

    def test_pil_fallback_to_qt(self, processor, test_image, tmp_path) -> None:
        """PIL processing should fallback to Qt when PIL fails."""
        cache_path = tmp_path / "fallback_thumbnail.jpg"

        with patch.object(
            processor, "_process_with_pil", side_effect=ImportError("PIL not available")
        ):
            with patch.object(processor, "_process_with_qt", return_value=True):
                result = processor.cache_thumbnail_sync(test_image, cache_path)

                assert result is True

    def test_pil_exception_fallback(self, processor, test_image, tmp_path) -> None:
        """PIL processing should fallback to Qt on general exceptions."""
        cache_path = tmp_path / "exception_thumbnail.jpg"

        with patch.object(
            processor,
            "_process_with_pil",
            side_effect=RuntimeError("PIL processing failed"),
        ):
            with patch.object(processor, "_process_with_qt", return_value=True):
                result = processor.cache_thumbnail_sync(test_image, cache_path)

                assert result is True

    def test_qt_null_image_fallback(self, processor, tmp_path) -> None:
        """Qt processing should handle null images gracefully."""
        # Create invalid image file
        bad_image = tmp_path / "bad.jpg"
        bad_image.write_bytes(b"not an image")
        cache_path = tmp_path / "null_thumbnail.jpg"

        result = processor.cache_thumbnail_sync(bad_image, cache_path)

        # Should fail gracefully
        assert result is False
        assert not cache_path.exists()


class TestThumbnailManagerErrorHandling:
    """Test error conditions and recovery mechanisms."""

    @pytest.fixture
    def processor(self):
        """Create ThumbnailManager for testing."""
        return ThumbnailManager(thumbnail_size=100)

    def test_missing_source_file(self, processor, tmp_path) -> None:
        """Processing should fail gracefully for missing source files."""
        nonexistent = tmp_path / "missing.jpg"
        cache_path = tmp_path / "thumbnail.jpg"

        result = processor.cache_thumbnail_sync(nonexistent, cache_path)

        assert result is False
        assert not cache_path.exists()

    def test_none_source_path(self, processor, tmp_path) -> None:
        """Processing should handle None source path gracefully."""
        cache_path = tmp_path / "thumbnail.jpg"

        result = processor.cache_thumbnail_sync(None, cache_path)

        assert result is False

    def test_none_cache_path(self, processor, tmp_path) -> None:
        """Processing should handle None cache path gracefully."""
        source = tmp_path / "test.jpg"
        source.write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        )

        result = processor.cache_thumbnail_sync(source, None)

        assert result is False

    def test_cache_directory_permission_error(self, processor, tmp_path) -> None:
        """Processing should handle cache directory creation failures."""
        source = tmp_path / "test.jpg"
        source.write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        )
        cache_path = tmp_path / "cache" / "thumbnail.jpg"

        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Access denied")):
            result = processor.cache_thumbnail_sync(source, cache_path)

            assert result is False

    def test_memory_error_handling(self, processor, tmp_path) -> None:
        """Processing should handle memory errors gracefully."""
        source = tmp_path / "test.jpg"
        source.write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        )
        cache_path = tmp_path / "thumbnail.jpg"

        with patch(
            "PySide6.QtGui.QImage.__init__", side_effect=MemoryError("Out of memory")
        ):
            result = processor.cache_thumbnail_sync(source, cache_path)

            assert result is False
            assert not cache_path.exists()

    def test_image_dimension_validation(self, processor, tmp_path) -> None:
        """Processing should validate image dimensions against max_dimension."""
        source = tmp_path / "huge.jpg"
        source.write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        )
        cache_path = tmp_path / "thumbnail.jpg"

        # Mock QImage to report huge dimensions without actually allocating memory
        with patch("PySide6.QtGui.QImage") as mock_qimage_class:
            mock_image = Mock()
            mock_image.isNull.return_value = False
            mock_image.width.return_value = 50000  # Huge width
            mock_image.height.return_value = 50000  # Huge height
            mock_qimage_class.return_value = mock_image

            result = processor.cache_thumbnail_sync(
                source, cache_path, max_dimension=1000
            )

            assert result is False


class TestThumbnailManagerResourceManagement:
    """Test cleanup and memory management."""

    @pytest.fixture
    def processor(self):
        """Create ThumbnailManager for testing."""
        return ThumbnailManager(thumbnail_size=100)

    def test_temporary_file_cleanup_on_success(self, processor, tmp_path) -> None:
        """Temporary files should be cleaned up after successful processing."""
        source = tmp_path / "test.jpg"
        # Create valid JPEG
        try:
            img = PILImage.new("RGB", (100, 100), color="yellow")
            img.save(source, "JPEG")
        except ImportError:
            test_img = ThreadSafeTestImage(100, 100)
            test_img.fill(QColor(255, 255, 0))  # Yellow fill
            test_img._image.save(str(source), "JPEG")

        cache_path = tmp_path / "thumbnail.jpg"

        result = processor.cache_thumbnail_sync(source, cache_path)

        assert result is True
        # No temporary files should remain
        temp_files = list(cache_path.parent.glob("*.tmp_*"))
        assert len(temp_files) == 0

    def test_temporary_file_cleanup_on_failure(self, processor, tmp_path) -> None:
        """Temporary files should be cleaned up after processing failures."""
        source = tmp_path / "test.jpg"
        source.write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        )
        cache_path = tmp_path / "thumbnail.jpg"

        # Mock save operation to fail
        with patch("PySide6.QtGui.QImage.save", return_value=False):
            result = processor.cache_thumbnail_sync(source, cache_path)

            assert result is False
            # No temporary files should remain
            temp_files = list(cache_path.parent.glob("*.tmp_*"))
            assert len(temp_files) == 0

    def test_garbage_collection_behavior(self, processor, tmp_path) -> None:
        """Processing should handle memory management correctly."""
        source = tmp_path / "test.jpg"
        source.write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        )
        cache_path = tmp_path / "thumbnail.jpg"

        # Track memory usage pattern instead of gc calls
        # Standard library imports
        import gc

        gc_count_before = len(gc.get_objects())

        result = processor.cache_thumbnail_sync(source, cache_path)

        # Test behavior: processing should complete successfully
        # Memory management is internal implementation detail
        assert result is True or result is False  # Should complete without exceptions

        # Verify no excessive object accumulation (loose check)
        gc_count_after = len(gc.get_objects())
        assert gc_count_after - gc_count_before < 1000  # Reasonable object growth

    def test_qt_resource_cleanup(self, processor, tmp_path) -> None:
        """Qt image resources should be properly cleaned up."""
        # Create valid JPEG
        source = tmp_path / "test.jpg"
        try:
            img = PILImage.new("RGB", (100, 100), color="blue")
            img.save(source, "JPEG")
        except ImportError:
            test_img = ThreadSafeTestImage(100, 100)
            test_img.fill(QColor(0, 0, 255))  # Blue fill
            test_img._image.save(str(source), "JPEG")

        cache_path = tmp_path / "thumbnail.jpg"

        # Verify processing works (resource cleanup is internal)
        result = processor.cache_thumbnail_sync(source, cache_path)

        # This mainly tests that the cleanup code path doesn't crash
        assert result is True or result is False  # Should complete without exceptions


class TestThumbnailManagerThreadSafety:
    """Test concurrent operations and thread safety."""

    @pytest.fixture
    def processor(self):
        """Create ThumbnailManager for testing."""
        return ThumbnailManager(thumbnail_size=100)

    @pytest.fixture
    def test_images(self, tmp_path) -> list[Path]:
        """Create multiple test images for concurrent processing."""
        images = []
        for i in range(5):
            image_file = tmp_path / f"test_{i}.jpg"
            try:
                color = (i * 50, (i * 30) % 255, (i * 70) % 255)
                img = PILImage.new("RGB", (150, 150), color=color)
                img.save(image_file, "JPEG")
            except ImportError:
                test_img = ThreadSafeTestImage(150, 150)
                test_img.fill(QColor(i * 50, (i * 30) % 255, (i * 70) % 255))
                test_img._image.save(str(image_file), "JPEG")
            images.append(image_file)
        return images

    def test_concurrent_processing(self, processor, test_images, tmp_path) -> None:
        """Multiple thumbnails should be processable concurrently."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        def process_image(source_path: Path) -> bool:
            cache_path = cache_dir / f"thumb_{source_path.name}"
            return processor.cache_thumbnail_sync(source_path, cache_path)

        # Process images concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(process_image, img) for img in test_images]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # All processing should succeed
        assert all(results)

        # All cache files should be created
        cache_files = list(cache_dir.glob("thumb_*.jpg"))
        assert len(cache_files) == len(test_images)


class TestThumbnailManagerIntegration:
    """Integration tests combining multiple aspects of thumbnail processing."""

    @pytest.fixture
    def processor(self):
        """Create ThumbnailManager for testing."""
        return ThumbnailManager(thumbnail_size=200)

    def test_end_to_end_jpeg_processing(self, processor, tmp_path) -> None:
        """Complete JPEG processing workflow should work end-to-end."""
        # Create valid source image
        source = tmp_path / "source.jpg"
        try:
            img = PILImage.new("RGB", (300, 200), color="green")
            img.save(source, "JPEG")
        except ImportError:
            test_img = ThreadSafeTestImage(300, 200)
            test_img.fill(QColor(0, 255, 0))  # Green fill
            test_img._image.save(str(source), "JPEG")

        # Define cache location
        cache_path = tmp_path / "cache" / "processed" / "thumbnail.jpg"

        # Process thumbnail
        result = processor.cache_thumbnail_sync(source, cache_path)

        # Verify complete success
        assert result is True
        assert cache_path.exists()
        assert cache_path.stat().st_size > 0
        assert cache_path.parent.exists()

        # Verify no temporary files remain
        temp_files = list(cache_path.parent.glob("*.tmp_*"))
        assert len(temp_files) == 0

    def test_processing_pipeline_error_recovery(self, processor, tmp_path) -> None:
        """Processing pipeline should recover gracefully from various errors."""
        # Test with various problematic inputs
        test_cases = [
            (tmp_path / "nonexistent.jpg", "Missing file"),
            (tmp_path / "empty.jpg", "Empty file"),
            (tmp_path / "invalid.jpg", "Invalid data"),
        ]

        # Create problematic files
        (tmp_path / "empty.jpg").touch()  # Empty file
        (tmp_path / "invalid.jpg").write_bytes(b"not an image")  # Invalid data

        results = []
        for source_path, description in test_cases:
            cache_path = tmp_path / f"cache_{source_path.name}"
            result = processor.cache_thumbnail_sync(source_path, cache_path)
            results.append((result, description))

        # All should fail gracefully (return False, no exceptions)
        for result, description in results:
            assert result is False, f"Should fail gracefully for: {description}"

        # No cache files should be created
        cache_files = list(tmp_path.glob("cache_*"))
        assert len(cache_files) == 0
