"""Thread safety tests for async callback race conditions.

Tests the specific thread safety fixes implemented in ShotItemModel and ShotInfoPanel
for async callback handling and race condition prevention.
"""

from __future__ import annotations

import concurrent.futures
import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QMetaObject, Qt, Q_ARG
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy

sys.path.insert(0, str(Path(__file__).parent.parent))

from shot_info_panel import ShotInfoPanel, InfoPanelPixmapLoader
from shot_item_model import ShotItemModel
from shot_model import Shot
from tests.test_doubles_library import TestCacheManager

pytestmark = [pytest.mark.thread_safety, pytest.mark.qt, pytest.mark.critical]


class TestShotItemModelThreadSafety:
    """Thread safety tests for ShotItemModel async callbacks."""

    @pytest.fixture
    def thread_safe_model(self, qtbot) -> ShotItemModel:
        """Create model for thread safety testing."""
        model = ShotItemModel(TestCacheManager())
        yield model
        model.clear_thumbnail_cache()
        model.deleteLater()

    @pytest.fixture
    def test_shots(self) -> list[Shot]:
        """Create test shots for thread safety testing."""
        return [
            Shot("thread_show", "thread_seq", f"shot_{i}", f"/workspace/shot_{i}")
            for i in range(10)
        ]

    def test_concurrent_shot_lookup_thread_safety(self, thread_safe_model, test_shots):
        """Test _find_shot_by_full_name under concurrent access."""
        thread_safe_model.set_shots(test_shots)
        
        results = []
        errors = []
        
        def lookup_worker(shot_names):
            """Worker function for concurrent lookups."""
            try:
                for name in shot_names:
                    result = thread_safe_model._find_shot_by_full_name(name)
                    results.append((name, result is not None))
                    time.sleep(0.001)  # Small delay to increase chance of race
            except Exception as e:
                errors.append(str(e))
        
        # Split shots among multiple threads
        shot_names = [shot.full_name for shot in test_shots]
        name_chunks = [shot_names[i::3] for i in range(3)]  # 3 threads
        
        # Run concurrent lookups
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(lookup_worker, chunk) 
                for chunk in name_chunks
            ]
            concurrent.futures.wait(futures, timeout=5.0)
            
        # Verify no errors and all lookups succeeded
        assert len(errors) == 0, f"Errors during concurrent lookups: {errors}"
        
        # Verify all shots were found correctly
        found_names = {name for name, found in results if found}
        assert len(found_names) == len(test_shots)

    def test_shot_removal_during_concurrent_callbacks(
        self, thread_safe_model, test_shots, qtbot
    ):
        """Test shot removal while async callbacks are executing."""
        thread_safe_model.set_shots(test_shots)
        
        callback_results = []
        callback_errors = []
        
        def simulate_async_callback(shot_full_name):
            """Simulate an async callback that might arrive after shot removal."""
            try:
                # Simulate delay as if coming from background thread
                time.sleep(0.1)
                
                # This mimics what _on_thumbnail_cached_safe does
                shot_data = thread_safe_model._find_shot_by_full_name(shot_full_name)
                callback_results.append((shot_full_name, shot_data is not None))
                
                if shot_data is not None:
                    shot, row = shot_data
                    # This should work even if called from background thread
                    QMetaObject.invokeMethod(
                        thread_safe_model, "_load_cached_pixmap_safe",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(object, Path("/fake/cache.jpg")),
                        Q_ARG(int, row),
                        Q_ARG(object, shot)
                    )
                    
            except Exception as e:
                callback_errors.append(str(e))
        
        # Start callbacks for all shots
        callback_threads = []
        for shot in test_shots:
            thread = threading.Thread(
                target=simulate_async_callback, 
                args=(shot.full_name,)
            )
            callback_threads.append(thread)
            thread.start()
        
        # Immediately remove half the shots
        qtbot.wait(50)  # Let callbacks start
        thread_safe_model.set_shots(test_shots[5:])  # Remove first 5 shots
        
        # Wait for all callbacks
        for thread in callback_threads:
            thread.join(timeout=2.0)
            
        qtbot.wait(200)  # Let Qt process any queued invocations
        
        # Verify no crashes occurred
        assert len(callback_errors) == 0, f"Callback errors: {callback_errors}"
        
        # Some callbacks should have found shots (the ones not removed)
        # Some should have returned None (the removed ones)
        found_count = sum(1 for name, found in callback_results if found)
        assert found_count == 5  # Only remaining shots should be found

    def test_thumbnail_cache_concurrent_access(self, thread_safe_model, test_shots):
        """Test concurrent access to thumbnail cache."""
        thread_safe_model.set_shots(test_shots)
        
        cache_operations = []
        cache_errors = []
        
        def cache_worker(worker_id):
            """Worker that performs cache operations."""
            try:
                for i, shot in enumerate(test_shots):
                    if i % 3 == worker_id:  # Divide work among workers
                        # Simulate cache operations
                        cache_key = shot.full_name
                        
                        # Read from cache
                        cached = thread_safe_model._thumbnail_cache.get(cache_key)
                        
                        # Write to cache
                        if cached is None:
                            test_image = QImage(32, 32, QImage.Format.Format_RGB32)
                            test_image.fill(0xFF0000)
                            thread_safe_model._thumbnail_cache[cache_key] = test_image
                            
                        cache_operations.append((worker_id, cache_key, "write"))
                        
                        time.sleep(0.001)  # Brief delay to increase contention
                        
            except Exception as e:
                cache_errors.append(f"Worker {worker_id}: {str(e)}")
        
        # Run concurrent cache operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(cache_worker, worker_id) 
                for worker_id in range(3)
            ]
            concurrent.futures.wait(futures, timeout=5.0)
            
        # Verify no errors in concurrent cache access
        assert len(cache_errors) == 0, f"Cache access errors: {cache_errors}"
        
        # Verify cache operations completed
        assert len(cache_operations) > 0
        
        # Verify cache integrity
        assert len(thread_safe_model._thumbnail_cache) <= len(test_shots)

    def test_model_reset_with_pending_callbacks(self, thread_safe_model, test_shots, qtbot):
        """Test model reset while callbacks are pending."""
        thread_safe_model.set_shots(test_shots)
        
        reset_errors = []
        callback_count = 0
        
        def delayed_callback(shot_full_name):
            """Callback that executes after model reset."""
            nonlocal callback_count
            try:
                time.sleep(0.2)  # Delay to ensure reset happens first
                
                # Try to access model after reset
                shot_data = thread_safe_model._find_shot_by_full_name(shot_full_name)
                callback_count += 1
                
                # Should handle gracefully even if shot no longer exists
                if shot_data is not None:
                    QMetaObject.invokeMethod(
                        thread_safe_model, "_load_cached_pixmap_safe",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(object, Path("/cache.jpg")),
                        Q_ARG(int, 0),
                        Q_ARG(object, shot_data[0])
                    )
                    
            except Exception as e:
                reset_errors.append(str(e))
        
        # Start delayed callbacks
        callback_threads = []
        for shot in test_shots[:3]:  # Just a few to avoid overhead
            thread = threading.Thread(
                target=delayed_callback,
                args=(shot.full_name,)
            )
            callback_threads.append(thread)
            thread.start()
        
        # Reset model immediately
        qtbot.wait(50)
        new_shots = [Shot("new", "new", "new", "/new")]
        thread_safe_model.set_shots(new_shots)
        
        # Wait for callbacks to complete
        for thread in callback_threads:
            thread.join(timeout=3.0)
            
        qtbot.wait(200)
        
        # Verify no errors during reset with pending callbacks
        assert len(reset_errors) == 0, f"Reset errors: {reset_errors}"
        assert callback_count == 3  # All callbacks should have executed


class TestShotInfoPanelThreadSafety:
    """Thread safety tests for ShotInfoPanel async loading."""

    @pytest.fixture
    def thread_safe_panel(self, qtbot) -> ShotInfoPanel:
        """Create panel for thread safety testing."""
        panel = ShotInfoPanel(TestCacheManager())
        qtbot.addWidget(panel)
        yield panel
        panel.deleteLater()

    def test_concurrent_pixmap_loading(self, thread_safe_panel, tmp_path, qtbot):
        """Test concurrent InfoPanelPixmapLoader operations."""
        # Create test images
        image_paths = []
        for i in range(5):
            image_path = tmp_path / f"test_{i}.jpg"
            image = QImage(64, 64, QImage.Format.Format_RGB32)
            image.fill(0xFF0000 + i * 0x100000)  # Different colors
            image.save(str(image_path), "JPEG")
            image_paths.append(image_path)
        
        loading_results = []
        loading_errors = []
        
        def loading_complete(success, path):
            loading_results.append((success, str(path)))
            
        def loading_error(path):
            loading_errors.append(str(path))
        
        # Start concurrent loaders
        loaders = []
        for path in image_paths:
            loader = InfoPanelPixmapLoader(thread_safe_panel, path)
            loader.signals.loaded.connect(
                lambda img, p=path: loading_complete(True, p)
            )
            loader.signals.failed.connect(
                lambda p=path: loading_error(p)
            )
            loaders.append(loader)
        
        # Start all loaders simultaneously
        from PySide6.QtCore import QThreadPool
        for loader in loaders:
            QThreadPool.globalInstance().start(loader)
            
        # Wait for completion
        qtbot.wait(1500)
        
        # Verify all operations completed without errors
        assert len(loading_errors) == 0, f"Loading errors: {loading_errors}"
        assert len(loading_results) == len(image_paths)
        
        # All should have succeeded
        success_count = sum(1 for success, _ in loading_results if success)
        assert success_count == len(image_paths)

    def test_rapid_shot_changes_thread_safety(self, thread_safe_panel, tmp_path, qtbot):
        """Test rapid shot changes don't cause race conditions."""
        # Create test shots with images
        shots = []
        for i in range(10):
            image_path = tmp_path / f"shot_{i}.jpg"
            image = QImage(32, 32, QImage.Format.Format_RGB32)
            image.fill(0x0000FF + i * 0x001100)  # Varying colors
            image.save(str(image_path), "JPEG")
            
            shot = Shot(f"show_{i}", f"seq_{i}", f"shot_{i}", str(tmp_path))
            shot.get_thumbnail_path = lambda p=image_path: p
            shots.append(shot)
        
        change_errors = []
        
        def rapid_changer():
            """Rapidly change shots from background thread."""
            try:
                for shot in shots:
                    # This should be thread-safe via Qt's signal mechanism
                    QMetaObject.invokeMethod(
                        thread_safe_panel, "set_shot",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(object, shot)
                    )
                    time.sleep(0.02)  # Brief delay between changes
                    
            except Exception as e:
                change_errors.append(str(e))
        
        # Start background shot changing
        changer_thread = threading.Thread(target=rapid_changer)
        changer_thread.start()
        
        # Also change shots from main thread
        for i in range(5):
            thread_safe_panel.set_shot(shots[i])
            qtbot.wait(50)
            
        # Wait for background thread
        changer_thread.join(timeout=5.0)
        
        # Final stabilization
        qtbot.wait(500)
        
        # Verify no errors during rapid changes
        assert len(change_errors) == 0, f"Shot change errors: {change_errors}"
        
        # Panel should be in valid state
        assert thread_safe_panel._current_shot in shots or thread_safe_panel._current_shot is None

    def test_loader_memory_safety_under_stress(self, thread_safe_panel, tmp_path, qtbot):
        """Test memory safety of loaders under high load."""
        # Create many small images
        image_paths = []
        for i in range(20):
            image_path = tmp_path / f"stress_{i}.jpg"
            image = QImage(16, 16, QImage.Format.Format_RGB32)
            image.fill(0xFF0000)
            image.save(str(image_path), "JPEG")
            image_paths.append(image_path)
        
        # Track completion
        completed = threading.Event()
        completion_count = 0
        
        def on_completion():
            nonlocal completion_count
            completion_count += 1
            if completion_count >= len(image_paths):
                completed.set()
        
        # Start many loaders
        for path in image_paths:
            loader = InfoPanelPixmapLoader(thread_safe_panel, path)
            loader.signals.loaded.connect(lambda img: on_completion())
            loader.signals.failed.connect(lambda: on_completion())
            
            QThreadPool.globalInstance().start(loader)
        
        # Wait for all to complete
        completed.wait(timeout=10.0)
        
        # Allow Qt cleanup
        qtbot.wait(200)
        
        # Should complete without memory errors or crashes
        assert completion_count >= len(image_paths) * 0.8  # Allow for some failures


class TestCrossComponentThreadSafety:
    """Test thread safety across multiple components."""

    def test_model_and_panel_concurrent_operations(self, qtbot, tmp_path):
        """Test model and panel operating concurrently without interference."""
        # Create test setup
        image_path = tmp_path / "concurrent.jpg"
        image = QImage(64, 64, QImage.Format.Format_RGB32)
        image.fill(0x00FF00)
        image.save(str(image_path), "JPEG")
        
        model = ShotItemModel(TestCacheManager())
        panel = ShotInfoPanel(TestCacheManager())
        qtbot.addWidget(panel)
        
        try:
            # Create shared shots
            shots = []
            for i in range(5):
                shot = Shot(f"conc_{i}", f"seq_{i}", f"shot_{i}", str(tmp_path))
                shot.get_thumbnail_path = lambda p=image_path: p
                shots.append(shot)
            
            operation_errors = []
            
            def model_worker():
                """Concurrent model operations."""
                try:
                    for i in range(10):
                        model.set_shots(shots[i % len(shots):])
                        model.set_visible_range(0, 2)
                        time.sleep(0.05)
                except Exception as e:
                    operation_errors.append(f"Model: {str(e)}")
            
            def panel_worker():
                """Concurrent panel operations."""
                try:
                    for i in range(10):
                        panel.set_shot(shots[i % len(shots)])
                        time.sleep(0.05)
                except Exception as e:
                    operation_errors.append(f"Panel: {str(e)}")
            
            # Run concurrent operations
            model_thread = threading.Thread(target=model_worker)
            panel_thread = threading.Thread(target=panel_worker)
            
            model_thread.start()
            panel_thread.start()
            
            # Wait for completion
            model_thread.join(timeout=10.0)
            panel_thread.join(timeout=10.0)
            
            # Allow Qt to process events
            qtbot.wait(500)
            
            # Verify no errors in concurrent operations
            assert len(operation_errors) == 0, f"Concurrent operation errors: {operation_errors}"
            
        finally:
            model.deleteLater()
            panel.deleteLater()