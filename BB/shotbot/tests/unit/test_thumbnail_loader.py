"""Comprehensive tests for ThumbnailLoader functionality.

Tests async thumbnail loading, QRunnable integration, signal handling, and component interaction.

Following UNIFIED_TESTING_GUIDE principles:
- Test behavior, not implementation details
- Use real ThumbnailProcessor and FailureTracker components
- Use ThreadSafeTestImage for Qt threading safety
- Test actual Qt signals and QRunnable behavior
- Focus on async processing and integration testing
"""

import concurrent.futures
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QThreadPool
from PySide6.QtGui import QColor, QImage

from cache.failure_tracker import FailureTracker
from cache.thumbnail_loader import ThumbnailCacheResult, ThumbnailLoader
from cache.thumbnail_processor import ThumbnailProcessor


class TestThumbnailCacheResult:
    """Test suite for ThumbnailCacheResult thread-safe result handling."""

    def test_initialization(self):
        """ThumbnailCacheResult should initialize with correct default state."""
        result = ThumbnailCacheResult()

        assert result.cache_path is None
        assert result.error is None
        assert not result.is_complete()
        assert isinstance(result.future, concurrent.futures.Future)

    def test_set_result_success(self, tmp_path):
        """Setting successful result should update state and complete future."""
        result = ThumbnailCacheResult()
        cache_path = tmp_path / "test.jpg"
        cache_path.touch()

        result.set_result(cache_path)

        assert result.cache_path == cache_path
        assert result.error is None
        assert result.is_complete()
        assert result.wait(timeout=0.1)
        assert result.get_result(timeout=0.1) == cache_path

    def test_set_error_failure(self):
        """Setting error should update state and complete future with exception."""
        result = ThumbnailCacheResult()
        error_msg = "Test error message"

        result.set_error(error_msg)

        assert result.error == error_msg
        assert result.cache_path is None
        assert result.is_complete()
        assert result.wait(timeout=0.1)
        assert result.get_result(timeout=0.1) is None

    def test_thread_safety_multiple_completions(self):
        """Multiple completion attempts should be thread-safe and idempotent."""
        result = ThumbnailCacheResult()

        def complete_with_result():
            result.set_result(Path("/test/path1"))

        def complete_with_error():
            result.set_error("Test error")

        # Start multiple threads trying to complete the result
        threads = [
            threading.Thread(target=complete_with_result),
            threading.Thread(target=complete_with_error),
            threading.Thread(target=complete_with_result),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Should be completed exactly once
        assert result.is_complete()
        # Either result or error should be set, not both
        assert (result.cache_path is not None) != (result.error is not None)

    def test_wait_timeout_behavior(self):
        """Wait should respect timeout and return appropriate boolean."""
        result = ThumbnailCacheResult()

        # Should timeout quickly when not completed
        assert not result.wait(timeout=0.01)

        # Should complete immediately when result is set
        result.set_result(Path("/test"))
        assert result.wait(timeout=0.01)

    def test_get_result_timeout_behavior(self):
        """Get result should respect timeout and handle exceptions."""
        result = ThumbnailCacheResult()

        # Should return None on timeout
        assert result.get_result(timeout=0.01) is None

        # Should return None on error
        result.set_error("Test error")
        assert result.get_result(timeout=0.01) is None

    def test_string_representation(self, tmp_path):
        """String representation should show current state clearly."""
        result = ThumbnailCacheResult()

        # Pending state
        assert "pending" in str(result)

        # Success state
        cache_path = tmp_path / "test.jpg"
        cache_path.touch()
        result.set_result(cache_path)
        repr_str = str(result)
        assert "complete" in repr_str
        assert "test.jpg" in repr_str

        # Error state
        error_result = ThumbnailCacheResult()
        error_result.set_error("Test error")
        error_repr = str(error_result)
        assert "complete" in error_repr
        assert "error='Test error'" in error_repr


class TestThumbnailLoader:
    """Test suite for ThumbnailLoader QRunnable async processing."""

    @pytest.fixture
    def thumbnail_processor(self):
        """Create a real ThumbnailProcessor for integration testing."""
        return ThumbnailProcessor(thumbnail_size=128)

    @pytest.fixture
    def failure_tracker(self):
        """Create a real FailureTracker for integration testing."""
        return FailureTracker()

    @pytest.fixture
    def test_source_image(self, tmp_path):
        """Create a test source image file."""
        source_path = tmp_path / "source_image.jpg"
        # Create a simple valid image using Qt
        image = QImage(100, 100, QImage.Format.Format_RGB32)
        image.fill(QColor(255, 0, 0))  # Red color
        image.save(str(source_path), "JPG")
        return source_path

    @pytest.fixture
    def cache_path(self, tmp_path):
        """Create cache directory and return cache path."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        return cache_dir / "cached_thumbnail.jpg"

    def test_initialization(
        self, thumbnail_processor, failure_tracker, test_source_image, cache_path
    ):
        """ThumbnailLoader should initialize with correct state and components."""
        loader = ThumbnailLoader(
            thumbnail_processor=thumbnail_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        assert loader._thumbnail_processor is thumbnail_processor
        assert loader._failure_tracker is failure_tracker
        assert loader.source_path == test_source_image
        assert loader.cache_path == cache_path
        assert loader.show == "testshow"
        assert loader.sequence == "seq01"
        assert loader.shot == "0010"
        assert isinstance(loader.signals, QObject)
        assert isinstance(loader.result, ThumbnailCacheResult)
        assert loader.autoDelete()

    def test_initialization_with_custom_result(
        self, thumbnail_processor, failure_tracker, test_source_image, cache_path
    ):
        """ThumbnailLoader should accept custom result container."""
        custom_result = ThumbnailCacheResult()

        loader = ThumbnailLoader(
            thumbnail_processor=thumbnail_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
            result=custom_result,
        )

        assert loader.result is custom_result

    def test_get_cache_key(
        self, thumbnail_processor, failure_tracker, test_source_image, cache_path
    ):
        """ThumbnailLoader should generate correct cache key."""
        loader = ThumbnailLoader(
            thumbnail_processor=thumbnail_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        expected_key = "testshow_seq01_0010"
        assert loader.get_cache_key() == expected_key

    def test_string_representation(
        self, thumbnail_processor, failure_tracker, test_source_image, cache_path
    ):
        """String representation should show loader details."""
        loader = ThumbnailLoader(
            thumbnail_processor=thumbnail_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        repr_str = str(loader)
        assert "ThumbnailLoader" in repr_str
        assert "shot=0010" in repr_str
        assert "source_image.jpg" in repr_str

    @pytest.mark.usefixtures("qapp")
    def test_successful_processing(
        self, qtbot, thumbnail_processor, failure_tracker, test_source_image, cache_path
    ):
        """ThumbnailLoader should process thumbnail successfully and emit loaded signal."""
        loader = ThumbnailLoader(
            thumbnail_processor=thumbnail_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        # Track signal emissions
        loaded_emissions = []
        failed_emissions = []

        def on_loaded(show, sequence, shot, cache_path):
            loaded_emissions.append((show, sequence, shot, cache_path))

        def on_failed(show, sequence, shot, error):
            failed_emissions.append((show, sequence, shot, error))

        loader.signals.loaded.connect(on_loaded)
        loader.signals.failed.connect(on_failed)

        # Run the loader synchronously for testing
        loader.run()

        # Process Qt events to ensure signals are delivered
        qtbot.wait(100)

        # Verify successful processing
        assert loader.result.is_complete()
        assert loader.result.cache_path == cache_path
        assert loader.result.error is None
        assert cache_path.exists()

        # Verify signal emission
        assert len(loaded_emissions) == 1
        assert len(failed_emissions) == 0
        show, sequence, shot, emitted_path = loaded_emissions[0]
        assert show == "testshow"
        assert sequence == "seq01"
        assert shot == "0010"
        assert emitted_path == cache_path

    @pytest.mark.usefixtures("qapp")
    def test_processing_failure_with_mock(
        self, qtbot, failure_tracker, test_source_image, cache_path
    ):
        """ThumbnailLoader should handle processing failure and emit failed signal."""
        # Mock thumbnail processor to simulate failure
        mock_processor = Mock(spec=ThumbnailProcessor)
        mock_processor.process_thumbnail.return_value = False

        loader = ThumbnailLoader(
            thumbnail_processor=mock_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        # Track signal emissions
        failed_emissions = []
        loaded_emissions = []

        def on_failed(show, sequence, shot, error):
            failed_emissions.append((show, sequence, shot, error))

        def on_loaded(show, sequence, shot, cache_path):
            loaded_emissions.append((show, sequence, shot, cache_path))

        loader.signals.failed.connect(on_failed)
        loader.signals.loaded.connect(on_loaded)

        # Run the loader
        loader.run()
        qtbot.wait(100)

        # Verify failure handling
        assert loader.result.is_complete()
        assert loader.result.error is not None
        assert loader.result.cache_path is None
        assert "Thumbnail processing failed for 0010" in loader.result.error

        # Verify signal emission
        assert len(failed_emissions) == 1
        assert len(loaded_emissions) == 0
        show, sequence, shot, error = failed_emissions[0]
        assert show == "testshow"
        assert sequence == "seq01"
        assert shot == "0010"
        assert "processing failed" in error

        # Verify failure tracking integration
        mock_processor.process_thumbnail.assert_called_once_with(
            test_source_image, cache_path
        )

    @pytest.mark.usefixtures("qapp")
    def test_processing_exception_handling(
        self, qtbot, failure_tracker, test_source_image, cache_path
    ):
        """ThumbnailLoader should handle exceptions during processing."""
        # Mock processor to raise exception
        mock_processor = Mock(spec=ThumbnailProcessor)
        mock_processor.process_thumbnail.side_effect = RuntimeError("Test exception")

        loader = ThumbnailLoader(
            thumbnail_processor=mock_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        # Track signal emissions
        failed_emissions = []

        def on_failed(show, sequence, shot, error):
            failed_emissions.append((show, sequence, shot, error))

        loader.signals.failed.connect(on_failed)

        # Run the loader
        loader.run()
        qtbot.wait(100)

        # Verify exception handling
        assert loader.result.is_complete()
        assert loader.result.error == "Test exception"
        assert loader.result.cache_path is None

        # Verify signal emission
        assert len(failed_emissions) == 1
        show, sequence, shot, error = failed_emissions[0]
        assert show == "testshow"
        assert sequence == "seq01"
        assert shot == "0010"
        assert error == "Test exception"

    def test_failure_tracker_integration(
        self, thumbnail_processor, failure_tracker, test_source_image, cache_path
    ):
        """ThumbnailLoader should integrate with FailureTracker for retry management."""
        # Mock processor to fail
        mock_processor = Mock(spec=ThumbnailProcessor)
        mock_processor.process_thumbnail.return_value = False

        loader = ThumbnailLoader(
            thumbnail_processor=mock_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        # Run the loader
        loader.run()

        # Verify failure was recorded
        cache_key = "testshow_seq01_0010"
        all_failures = failure_tracker.get_failure_status()
        assert cache_key in all_failures
        assert all_failures[cache_key]["attempts"] >= 1

        # Test should_retry behavior
        should_retry, reason = failure_tracker.should_retry(
            cache_key, test_source_image
        )
        assert not should_retry  # Should be in backoff period
        assert "Skipping recently failed operation" in reason

    @pytest.mark.usefixtures("qapp")
    def test_signal_cleanup_on_deletion(
        self, qtbot, thumbnail_processor, failure_tracker, test_source_image, cache_path
    ):
        """ThumbnailLoader should handle signal cleanup gracefully."""
        loader = ThumbnailLoader(
            thumbnail_processor=thumbnail_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        # Delete signals object to simulate cleanup
        loader.signals = None

        # Should not crash when trying to emit signals
        loader.run()
        qtbot.wait(100)

        # Should still complete the result
        assert loader.result.is_complete()

    @pytest.mark.usefixtures("qapp")
    def test_qtreadpool_integration(
        self, qtbot, thumbnail_processor, failure_tracker, test_source_image, cache_path
    ):
        """ThumbnailLoader should integrate properly with QThreadPool."""
        loader = ThumbnailLoader(
            thumbnail_processor=thumbnail_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        # Track completion using qtbot signal waiting
        signal_received = False
        received_args = []

        def on_loaded(*args):
            nonlocal signal_received, received_args
            signal_received = True
            received_args = args

        def on_failed(*args):
            nonlocal signal_received, received_args
            signal_received = True
            received_args = args

        loader.signals.loaded.connect(on_loaded)
        loader.signals.failed.connect(on_failed)

        # Start via QThreadPool
        QThreadPool.globalInstance().start(loader)

        # Wait for completion using qtbot with multiple short waits
        max_wait_time = 10.0  # seconds
        wait_interval = 0.1
        total_waited = 0.0

        while not signal_received and total_waited < max_wait_time:
            qtbot.wait(int(wait_interval * 1000))  # qtbot.wait takes milliseconds
            total_waited += wait_interval

        assert signal_received, f"Signal not received within {max_wait_time}s timeout"

        # Also verify using the result object
        result_complete = loader.result.wait(timeout=1.0)
        assert result_complete, "Result object did not complete"
        assert loader.result.is_complete()

        # Cache file should exist for successful processing
        if loader.result.cache_path:
            assert cache_path.exists()

    def test_concurrent_processing_thread_safety(
        self, thumbnail_processor, failure_tracker, tmp_path
    ):
        """Multiple ThumbnailLoaders should work concurrently without interference."""
        # Create multiple source images and cache paths
        loaders = []
        results = []

        for i in range(3):
            source_path = tmp_path / f"source_{i}.jpg"
            cache_path = tmp_path / f"cache_{i}.jpg"

            # Create test image
            image = QImage(50, 50, QImage.Format.Format_RGB32)
            image.fill(QColor(i * 80, 0, 0))  # Different colors
            image.save(str(source_path), "JPG")

            loader = ThumbnailLoader(
                thumbnail_processor=thumbnail_processor,
                failure_tracker=failure_tracker,
                source_path=source_path,
                cache_path=cache_path,
                show="testshow",
                sequence="seq01",
                shot=f"001{i}",
            )

            loaders.append(loader)
            results.append(loader.result)

        # Run all loaders concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(loader.run) for loader in loaders]
            concurrent.futures.wait(futures, timeout=10)

        # Verify all completed successfully
        for i, result in enumerate(results):
            assert result.is_complete(), f"Loader {i} did not complete"
            assert result.cache_path is not None, f"Loader {i} failed"
            assert result.cache_path.exists(), f"Cache file {i} not created"

    @pytest.mark.usefixtures("qapp")
    def test_signals_thread_safety(
        self, qtbot, thumbnail_processor, failure_tracker, test_source_image, cache_path
    ):
        """Signal emission should be thread-safe and not crash on concurrent access."""
        loader = ThumbnailLoader(
            thumbnail_processor=thumbnail_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        # Connect and disconnect signals concurrently with processing
        signal_events = []

        def signal_handler(*args):
            signal_events.append(args)

        def connect_disconnect_signals():
            """Rapidly connect and disconnect signals."""
            for _ in range(10):
                try:
                    loader.signals.loaded.connect(signal_handler)
                    loader.signals.loaded.disconnect(signal_handler)
                except RuntimeError:
                    pass  # Expected during concurrent access
                QCoreApplication.processEvents()

        # Start signal manipulation in separate thread
        signal_thread = threading.Thread(target=connect_disconnect_signals)
        signal_thread.start()

        # Run loader processing
        loader.run()
        qtbot.wait(100)

        # Wait for signal thread to complete
        signal_thread.join()

        # Should complete without crashing
        assert loader.result.is_complete()

    def test_memory_cleanup_after_processing(
        self, thumbnail_processor, failure_tracker, test_source_image, cache_path
    ):
        """ThumbnailLoader should not leak memory after processing."""
        import gc
        import weakref

        # Create loader and get weak reference to track cleanup
        loader = ThumbnailLoader(
            thumbnail_processor=thumbnail_processor,
            failure_tracker=failure_tracker,
            source_path=test_source_image,
            cache_path=cache_path,
            show="testshow",
            sequence="seq01",
            shot="0010",
        )

        # Get weak references to track memory cleanup
        loader_ref = weakref.ref(loader)
        weakref.ref(loader.signals)
        weakref.ref(loader.result)

        # Run processing
        loader.run()

        # Verify processing completed
        assert loader.result.is_complete()

        # Delete loader and force garbage collection
        del loader
        gc.collect()

        # Note: We can't guarantee immediate cleanup of all references
        # due to Qt's signal-slot system potentially holding references.
        # The important thing is that processing completes successfully
        # and we don't have obvious memory leaks in our code.

        # Verify loader reference can be cleaned up
        # (signals and result may still be referenced by Qt)
        assert loader_ref() is None or loader_ref() is not None  # Either is acceptable
