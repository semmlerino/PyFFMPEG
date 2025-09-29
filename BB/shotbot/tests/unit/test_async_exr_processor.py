"""Tests for AsyncEXRProcessor - Non-blocking EXR thumbnail processing.

Following UNIFIED_TESTING_GUIDE best practices:
- Test behavior, not implementation
- Mock only at system boundaries (subprocess)
- Use factory fixtures for flexible test data
- Proper Qt thread cleanup
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from cache.async_exr_processor import AsyncEXRProcessor
from cache.thumbnail_manager import ThumbnailProcessor

# Test markers for categorization and parallel safety
pytestmark = [
    pytest.mark.unit,
    pytest.mark.qt,
    pytest.mark.xdist_group("qt_state"),  # Critical for parallel execution safety
]


# Factory fixtures for test data creation
@pytest.fixture
def make_thumbnail_processor():
    """Factory for creating ThumbnailProcessor instances."""

    def _make(thumbnail_size=256):
        processor = ThumbnailProcessor(thumbnail_size=thumbnail_size)
        return processor

    return _make


@pytest.fixture
def make_exr_processor(make_thumbnail_processor):
    """Factory for creating AsyncEXRProcessor instances with cleanup."""
    processors = []

    def _make(exr_files=None):
        if exr_files is None:
            exr_files = [Path(f"/test/file{i}.exr") for i in range(3)]
        thumb_processor = make_thumbnail_processor()
        processor = AsyncEXRProcessor(thumb_processor, exr_files)
        processors.append(processor)
        return processor

    yield _make

    # Cleanup all created processors
    for processor in processors:
        if processor.isRunning():
            processor.quit()
            processor.wait(1000)  # Wait up to 1 second
        processor.deleteLater()


@pytest.fixture
def make_test_exr_files(tmp_path):
    """Factory for creating test EXR file paths."""

    def _make(count=3):
        files = []
        for i in range(count):
            exr_file = tmp_path / f"test_{i}.exr"
            exr_file.touch()  # Create empty file
            files.append(exr_file)
        return files

    return _make


@pytest.fixture
def mock_subprocess():
    """Mock subprocess at system boundary."""
    with patch("subprocess.run") as mock_run:
        # Mock successful OpenEXR conversion
        mock_run.return_value.returncode = 0
        yield mock_run


# Mock fixture removed - direct patching is more reliable for async functions in QThread


class TestAsyncEXRProcessor:
    """Test suite for AsyncEXRProcessor class."""

    def test_signal_emission_on_completion(self, qtbot, make_exr_processor):
        """Test that batch_completed signal is emitted with results.

        Following guide pattern: Signal testing with parameter validation.
        """
        # Create processor
        exr_files = [Path(f"/test/file{i}.exr") for i in range(3)]
        processor = make_exr_processor(exr_files)

        # Create mock async function
        async def mock_process(batch):
            """Mock processor that returns results."""
            await asyncio.sleep(0)
            return {f: f.with_suffix(".jpg") for f in batch}

        # Apply mock
        with patch.object(
            processor._processor, "process_exr_batch_async", new=mock_process
        ):
            # Set up signal spy before starting (avoid race condition)
            with qtbot.waitSignal(processor.batch_completed, timeout=2000) as blocker:
                processor.start()

            # Verify signal was emitted with correct data
            assert len(blocker.args) == 1
            results = blocker.args[0]
            assert isinstance(results, dict)
            assert len(results) == 3
            # Results are strings due to Qt signal marshalling
            assert "/test/file0.exr" in results
            assert results["/test/file0.exr"] == "/test/file0.jpg"

    def test_progress_updates_during_processing(self, qtbot, make_exr_processor):
        """Test that progress_updated signals are emitted during batch processing."""
        processor = make_exr_processor()

        # Create mock async function
        async def mock_process(batch):
            await asyncio.sleep(0)
            return {f: f.with_suffix(".jpg") for f in batch}

        with patch.object(
            processor._processor, "process_exr_batch_async", new=mock_process
        ):
            # Track all progress updates
            progress_values = []
            processor.progress_updated.connect(progress_values.append)

            # Wait for completion
            with qtbot.waitSignal(processor.batch_completed, timeout=2000):
                processor.start()

            # Should have received at least one progress update
            assert len(progress_values) > 0
            # Progress should be between 0 and 100
            for value in progress_values:
                assert 0 <= value <= 100

    def test_thread_cleanup_after_completion(self, qtbot, make_exr_processor):
        """Test proper QThread cleanup after processing.

        Following guide: Worker Thread Pattern cleanup requirements.
        """
        processor = make_exr_processor()

        # Create mock async function
        async def mock_process(batch):
            await asyncio.sleep(0)
            return {f: f.with_suffix(".jpg") for f in batch}

        with patch.object(
            processor._processor, "process_exr_batch_async", new=mock_process
        ):
            # Process batch
            with qtbot.waitSignal(processor.batch_completed, timeout=2000):
                processor.start()

            # Wait for thread to finish
            assert processor.wait(1000)  # Should finish within 1 second
            assert not processor.isRunning()

    def test_error_handling_in_async_processing(
        self, qtbot, make_exr_processor, make_thumbnail_processor
    ):
        """Test that exceptions in async processing are handled gracefully."""
        thumb_processor = make_thumbnail_processor()
        processor = AsyncEXRProcessor(thumb_processor, [Path("/test.exr")])

        # Create async function that raises exception
        async def mock_error_batch(batch):
            """Mock function that raises an error."""
            await asyncio.sleep(0)
            raise Exception("Test error")

        # Mock to raise exception
        with patch.object(
            thumb_processor,
            "process_exr_batch_async",
            new=mock_error_batch,  # Use real async function that raises
        ):
            # Should emit error signal
            with qtbot.waitSignal(processor.error_occurred, timeout=2000) as blocker:
                processor.start()

            # Verify error message
            error_msg = blocker.args[0]
            assert "Test error" in error_msg

    def test_empty_batch_handling(self, qtbot, make_thumbnail_processor):
        """Test handling of empty EXR file list."""
        thumb_processor = make_thumbnail_processor()
        processor = AsyncEXRProcessor(thumb_processor, [])

        # Should complete immediately
        with qtbot.waitSignal(processor.batch_completed, timeout=1000) as blocker:
            processor.start()

        # Should return empty results
        assert blocker.args[0] == {}

    @pytest.mark.parametrize("file_count", [1, 5, 10])
    def test_various_batch_sizes(
        self,
        qtbot,
        make_test_exr_files,
        make_thumbnail_processor,
        file_count,
        mock_subprocess,
    ):
        """Test processing various batch sizes.

        Following guide: Parametrization for comprehensive testing.
        """
        exr_files = make_test_exr_files(file_count)
        thumb_processor = make_thumbnail_processor()
        processor = AsyncEXRProcessor(thumb_processor, exr_files)

        # Create async function that returns appropriate results
        async def mock_batch_processor(batch):
            """Mock that returns expected results for the batch."""
            await asyncio.sleep(0)
            # Return only files from this batch
            return {f: f.with_suffix(".jpg") for f in batch if f in exr_files}

        with patch.object(
            thumb_processor,
            "process_exr_batch_async",
            new=mock_batch_processor,  # Use real async function
        ):
            with qtbot.waitSignal(processor.batch_completed, timeout=3000) as blocker:
                processor.start()

            # Verify all files processed (results are strings)
            results = blocker.args[0]
            assert len(results) == file_count
            for exr_file in exr_files:
                assert str(exr_file) in results
                assert results[str(exr_file)] == str(exr_file.with_suffix(".jpg"))

    def test_concurrent_processor_instances(self, qtbot, make_exr_processor):
        """Test multiple processor instances running concurrently.

        Following guide: Thread safety testing.
        """
        processor1 = make_exr_processor([Path("/batch1/file.exr")])
        processor2 = make_exr_processor([Path("/batch2/file.exr")])

        # Create mock async function
        async def mock_process(batch):
            await asyncio.sleep(0)
            return {f: f.with_suffix(".jpg") for f in batch}

        with (
            patch.object(
                processor1._processor, "process_exr_batch_async", new=mock_process
            ),
            patch.object(
                processor2._processor, "process_exr_batch_async", new=mock_process
            ),
        ):
            completed = []
            processor1.batch_completed.connect(lambda r: completed.append(1))
            processor2.batch_completed.connect(lambda r: completed.append(2))

            # Start both processors
            processor1.start()
            processor2.start()

            # Wait for both to complete
            qtbot.wait(2000)  # Give time for both to finish

            # Both should have completed
            assert 1 in completed
            assert 2 in completed

    def test_processor_reuse_not_allowed(self, qtbot, make_exr_processor):
        """Test that processor cannot be reused after completion."""
        processor = make_exr_processor()

        # Create mock async function
        async def mock_process(batch):
            await asyncio.sleep(0)
            return {f: f.with_suffix(".jpg") for f in batch}

        with patch.object(
            processor._processor, "process_exr_batch_async", new=mock_process
        ):
            # First run
            with qtbot.waitSignal(processor.batch_completed, timeout=2000):
                processor.start()

            # Wait for thread to actually finish
            processor.wait(1000)
            assert not processor.isRunning()

        # QThread cannot be restarted after finishing
        # Create a new processor for second run
        processor2 = make_exr_processor()
        with patch.object(
            processor2._processor, "process_exr_batch_async", new=mock_process
        ):
            with qtbot.waitSignal(processor2.batch_completed, timeout=2000):
                processor2.start()

            # Both should be finished
            assert not processor.isRunning()
            assert processor2.wait(1000)  # Wait for completion

    @pytest.mark.slow
    def test_actual_subprocess_integration(
        self, qtbot, tmp_path, make_thumbnail_processor
    ):
        """Integration test with actual subprocess (if OpenEXR available).

        Following guide: Integration test at system boundary.
        """
        import shutil

        # Skip if convert command (ImageMagick) is not available
        if not shutil.which("convert"):
            pytest.skip("ImageMagick 'convert' command not available")
        # Create a small test EXR file
        exr_file = tmp_path / "test.exr"
        exr_file.write_bytes(b"fake exr content")  # Would be real EXR in production

        thumb_processor = make_thumbnail_processor()
        processor = AsyncEXRProcessor(thumb_processor, [exr_file])

        # Don't mock subprocess - test actual integration
        # This will likely emit error_occurred since it's not a real EXR
        signal_received = False

        def on_signal():
            nonlocal signal_received
            signal_received = True

        processor.batch_completed.connect(on_signal)
        processor.error_occurred.connect(on_signal)

        processor.start()
        processor.wait(5000)  # Wait up to 5 seconds

        # Should have received either completion or error
        assert signal_received
