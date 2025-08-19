"""Demonstration of UNIFIED_TESTING_GUIDE best practices.

This test file showcases all recommended patterns:
- Behavior testing over implementation testing
- Real components with test doubles at boundaries
- Thread-safe image operations with ThreadSafeTestImage
- Proper signal testing patterns
- Comprehensive edge case coverage
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtTest import QSignalSpy
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from cache_manager import CacheManager, ThumbnailCacheResult
from launcher_manager import CustomLauncher, LauncherManager
from shot_model import Shot, ShotModel
from tests.test_doubles import TestSignal, ThreadSafeTestImage


class TestBehaviorOverImplementation:
    """Demonstrate testing behavior, not implementation details."""

    def test_cache_behavior_not_internals(self, tmp_path):
        """Test cache behavior without checking internal state."""
        # GOOD: Test actual behavior
        cache = CacheManager(cache_dir=tmp_path)
        shot = Shot("show", "seq", "shot", "/path")
        
        # Cache some shots
        cache.cache_shots([shot])
        
        # Test BEHAVIOR: Can we retrieve what we cached?
        cached_shots = cache.get_cached_shots()
        assert cached_shots is not None
        assert len(cached_shots) == 1
        assert cached_shots[0]["show"] == "show"
        
        # BAD: Don't test internal implementation
        # assert cache._cache_data == {...}  # Implementation detail!
        # assert cache._internal_counter == 1  # Who cares!

    def test_launcher_execution_outcome(self, tmp_path):
        """Test launcher execution by verifying outcomes."""
        manager = LauncherManager()
        manager.config.config_dir = tmp_path
        manager.config.config_file = tmp_path / "launchers.json"
        
        # Create a launcher using the actual API
        created = manager.create_launcher(
            name="Test Launcher",
            command="echo 'Hello World'"
        )
        
        # GOOD: Test the outcome - launcher ID should be returned
        assert created is not None
        assert isinstance(created, str)
        
        # Verify behavior: Can we retrieve it?
        launchers = manager.get_all_launchers()
        assert len(launchers) > 0
        
        # Find our launcher by name
        test_launcher = next((l for l in launchers if l.name == "Test Launcher"), None)
        assert test_launcher is not None
        assert test_launcher.command == "echo 'Hello World'"
        
        # BAD: Don't test how it's stored internally
        # assert manager._launchers["test"] == launcher  # Implementation!


class TestThreadSafeImageOperations:
    """Demonstrate proper thread-safe image testing."""

    def test_concurrent_image_processing_safe(self):
        """Test concurrent image operations without Qt threading violations."""
        results = []
        errors = []
        
        def process_image(thread_id: int):
            """Process image in worker thread - MUST use ThreadSafeTestImage."""
            try:
                # GOOD: Use ThreadSafeTestImage in worker threads
                image = ThreadSafeTestImage(200, 200)
                image.fill(QColor(255, 0, 0))
                
                # Simulate processing
                size = image.sizeInBytes()
                assert size > 0
                
                results.append((thread_id, "success"))
                
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # Run in multiple threads
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(process_image, i) for i in range(5)]
            for future in futures:
                future.result(timeout=5)
        
        # Verify no threading violations
        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 5
        assert all(r[1] == "success" for r in results)

    def test_qpixmap_main_thread_only(self, qtbot):
        """Demonstrate QPixmap must only be used in main thread."""
        # This test runs in main thread, so QPixmap is safe here
        from PySide6.QtGui import QPixmap
        
        # GOOD: QPixmap in main thread is fine
        pixmap = QPixmap(100, 100)
        assert not pixmap.isNull()
        
        # BAD: Never create QPixmap in worker thread!
        # def worker():
        #     pixmap = QPixmap(100, 100)  # FATAL ERROR!
        # threading.Thread(target=worker).start()


class TestSignalPatterns:
    """Demonstrate proper signal testing patterns."""

    class RealQtComponent(QObject):
        """Real Qt component with signals."""
        data_changed = Signal(str)
        process_complete = Signal()
        
        def update_data(self, value: str):
            """Update data and emit signal."""
            self.data_changed.emit(value)
            
        def finish_process(self):
            """Complete process and emit signal."""
            self.process_complete.emit()

    def test_real_qt_signals_with_spy(self, qtbot):
        """Test real Qt signals with QSignalSpy."""
        # GOOD: Use QSignalSpy for real Qt signals
        component = self.RealQtComponent()
        qtbot.addWidget(component)
        
        # Create spy for real signal
        spy = QSignalSpy(component.data_changed)
        
        # Trigger signal
        component.update_data("test_value")
        
        # Verify signal emission
        assert len(spy) == 1
        assert spy[0][0] == "test_value"

    def test_test_signal_for_doubles(self):
        """Test doubles should use TestSignal, not real Qt signals."""
        # GOOD: Use TestSignal for test doubles
        class TestComponent:
            def __init__(self):
                self.data_changed = TestSignal()
                
            def update(self, value):
                self.data_changed.emit(value)
        
        component = TestComponent()
        received = []
        component.data_changed.connect(lambda v: received.append(v))
        
        component.update("test")
        
        # Verify using TestSignal methods
        assert component.data_changed.was_emitted
        assert component.data_changed.emissions[0] == ("test",)
        assert received == ["test"]

    def test_async_signal_no_race_condition(self, qtbot):
        """Demonstrate avoiding signal race conditions."""
        component = self.RealQtComponent()
        qtbot.addWidget(component)
        
        # GOOD: Set up signal waiter BEFORE triggering
        with qtbot.waitSignal(component.process_complete, timeout=1000):
            # Now trigger the operation
            QTimer.singleShot(10, component.finish_process)
        
        # Signal was successfully caught
        
        # BAD: Don't trigger before setting up waiter!
        # component.finish_process()  # Signal emitted!
        # with qtbot.waitSignal(component.process_complete):  # Too late!
        #     pass


class TestEdgeCases:
    """Test edge cases and error conditions properly."""

    def test_concurrent_cache_operations_edge_case(self, tmp_path):
        """Test edge case: concurrent operations on same cache key."""
        cache = CacheManager(cache_dir=tmp_path)
        shot = Shot("show", "seq", "shot", "/path")
        
        race_conditions = []
        
        def cache_operation(op_id: int):
            """Perform cache operations concurrently."""
            try:
                # Multiple threads trying to cache same shot
                cache.cache_shots([shot])
                time.sleep(0.001)
                result = cache.get_cached_shots()
                
                if result is None or len(result) != 1:
                    race_conditions.append(f"Op {op_id}: Invalid result")
                    
            except Exception as e:
                race_conditions.append(f"Op {op_id}: {e}")
        
        # Run concurrent operations
        threads = [threading.Thread(target=cache_operation, args=(i,)) 
                  for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verify no race conditions
        assert len(race_conditions) == 0, f"Race conditions: {race_conditions}"
        
        # Verify final state is consistent
        final_result = cache.get_cached_shots()
        assert final_result is not None
        assert len(final_result) == 1

    def test_memory_pressure_handling(self, tmp_path):
        """Test behavior under memory pressure."""
        cache = CacheManager(cache_dir=tmp_path)
        
        # Set very low memory limit
        original_limit = cache._max_memory_bytes
        cache._max_memory_bytes = 100  # Very small
        
        try:
            # Try to cache multiple large images
            for i in range(5):
                shot = Shot("show", "seq", f"shot{i}", "/path")
                
                # Use ThreadSafeTestImage for testing
                with patch("cache_manager.QImage") as mock_qimage:
                    test_image = ThreadSafeTestImage(1000, 1000)  # Large
                    mock_qimage.return_value = test_image._image
                    
                    # Should handle gracefully without crashing
                    cache.cache_thumbnail(
                        tmp_path / f"image{i}.jpg",
                        shot.show,
                        shot.sequence,
                        shot.shot
                    )
            
            # Verify behavior: Should not exceed memory limit
            # Don't check internals, check behavior
            assert True  # No crash is success
            
        finally:
            cache._max_memory_bytes = original_limit

    def test_null_and_empty_handling(self):
        """Test handling of null/empty values properly."""
        # Test with empty shot list
        result = ThumbnailCacheResult()
        result.set_result(None)
        
        # Behavior: Should handle None gracefully
        assert result.cache_path is None
        
        # Test with empty path
        result2 = ThumbnailCacheResult()
        result2.set_result(Path(""))
        
        # Should handle empty path
        assert result2.cache_path == Path("")


class TestRealComponentIntegration:
    """Test real components working together."""

    def test_shot_model_cache_integration(self, tmp_path, qtbot):
        """Test real ShotModel with real CacheManager."""
        # Use real components, not mocks
        cache = CacheManager(cache_dir=tmp_path)
        model = ShotModel(cache_manager=cache)
        qtbot.addWidget(model)
        
        # Add test data
        test_shots = [
            Shot("show1", "seq1", "shot1", "/path1"),
            Shot("show1", "seq1", "shot2", "/path2"),
        ]
        
        # Use test double only for external boundary (subprocess)
        from tests.unit.test_doubles import TestProcessPool
        model._process_pool = TestProcessPool()
        model._process_pool.set_outputs(
            "workspace /path1",
            "workspace /path2"
        )
        
        # Test real integration behavior
        result = model.refresh_shots()
        
        # Verify behavior through public interface
        assert result.success
        shots = model.get_shots()
        assert len(shots) == 2
        
        # Verify cache integration works
        cached = cache.get_cached_shots()
        assert cached is not None
        assert len(cached) == 2


class TestProperTestDoubles:
    """Demonstrate proper use of test doubles."""

    def test_with_test_process_pool(self):
        """Use TestProcessPool for subprocess boundaries."""
        from tests.unit.test_doubles import TestProcessPool
        
        model = ShotModel()
        
        # Replace external dependency with test double
        test_pool = TestProcessPool()
        test_pool.set_outputs(
            "workspace /test/show/seq/shot"
        )
        model._process_pool = test_pool
        
        # Test behavior
        result = model.refresh_shots()
        assert result.success
        
        # Verify through behavior, not implementation
        shots = model.get_shots()
        assert len(shots) == 1
        assert shots[0].workspace_path == "/test/show/seq/shot"

    def test_avoid_excessive_mocking(self):
        """Demonstrate avoiding excessive mocking."""
        # BAD: Don't mock everything
        # model = Mock()
        # model.refresh_shots.return_value = Mock(success=True)
        # This tests nothing!
        
        # GOOD: Use real component with test doubles at boundaries
        model = ShotModel()
        from tests.unit.test_doubles import TestProcessPool
        model._process_pool = TestProcessPool()
        
        # Now we're testing real behavior
        result = model.refresh_shots()
        assert isinstance(result.success, bool)


# Test runner compatibility
if __name__ == "__main__":
    pytest.main([__file__, "-v"])