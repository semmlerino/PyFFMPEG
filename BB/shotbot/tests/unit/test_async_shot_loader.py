#!/usr/bin/env python3
"""Critical tests for AsyncShotLoader thread safety and signal emission."""

import pytest
import time
from unittest.mock import Mock
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtTest import QSignalSpy

from shot_model_optimized import AsyncShotLoader, OptimizedShotModel
from process_pool_manager import ProcessPoolManager


class TestAsyncShotLoader:
    """Test AsyncShotLoader thread behavior and signal emission."""

    @pytest.fixture
    def mock_process_pool(self):
        """Create mock process pool for testing."""
        pool = Mock(spec=ProcessPoolManager)
        pool.execute_workspace_command.return_value = """workspace /shows/TEST/seq01/0010
workspace /shows/TEST/seq01/0020
workspace /shows/TEST/seq02/0010"""
        return pool

    @pytest.fixture
    def loader(self, mock_process_pool, qtbot):
        """Create AsyncShotLoader for testing."""
        loader = AsyncShotLoader(mock_process_pool)
        # AsyncShotLoader is a QThread, not a QWidget, so we don't use addWidget
        # Instead, ensure it gets properly cleaned up
        yield loader
        if loader.isRunning():
            loader.quit()
            loader.wait(1000)

    def test_loader_signals_exist(self, loader):
        """Test that AsyncShotLoader has required signals."""
        assert hasattr(loader, 'shots_loaded')
        assert hasattr(loader, 'load_failed')

    def test_successful_shot_loading_signal_emission(self, loader, qtbot):
        """Test shots_loaded signal is emitted with correct data."""
        # Use QSignalSpy to verify signal emission
        spy = QSignalSpy(loader.shots_loaded)
        
        # Start loader
        loader.start()
        
        # Wait for thread completion with timeout
        assert loader.wait(5000), "Thread did not complete within 5 seconds"
        
        # Verify signal was emitted
        assert spy.count() == 1, "shots_loaded signal was not emitted"
        
        # Verify signal data
        shots = spy[0][0]  # First argument of first emission
        assert len(shots) == 3
        assert shots[0].show == "TEST"
        assert shots[0].sequence == "seq01"
        assert shots[0].shot == "0010"

    def test_failed_loading_signal_emission(self, qtbot):
        """Test load_failed signal is emitted on exception."""
        # Create failing process pool
        failing_pool = Mock(spec=ProcessPoolManager)
        failing_pool.execute_workspace_command.side_effect = RuntimeError("Command failed")
        
        loader = AsyncShotLoader(failing_pool)
        qtbot.addWidget(loader)
        
        # Use QSignalSpy for error signal
        error_spy = QSignalSpy(loader.load_failed)
        
        loader.start()
        assert loader.wait(5000)
        
        # Verify error signal emission
        assert len(error_spy) == 1
        assert "Command failed" in error_spy[0][0]

    def test_loader_stop_request(self, loader, qtbot):
        """Test that stop() request prevents signal emission."""
        # Create slow process pool
        slow_pool = Mock(spec=ProcessPoolManager)
        def slow_command(*args, **kwargs):
            time.sleep(0.1)  # Simulate slow operation
            return "workspace /shows/TEST/seq01/0010"
        slow_pool.execute_workspace_command.side_effect = slow_command
        
        loader = AsyncShotLoader(slow_pool)
        qtbot.addWidget(loader)
        
        spy = QSignalSpy(loader.shots_loaded)
        
        # Start and immediately stop
        loader.start()
        loader.stop()
        
        assert loader.wait(1000)
        
        # No signals should be emitted when stopped
        assert spy.count() == 0

    def test_thread_cleanup(self, loader, qtbot):
        """Test proper thread resource cleanup."""
        loader.start()
        assert loader.wait(5000)
        
        # Thread should be finished
        assert loader.isFinished()
        assert not loader.isRunning()

    def test_concurrent_loader_instances(self, qtbot):
        """Test multiple AsyncShotLoader instances don't interfere."""
        pool1 = Mock(spec=ProcessPoolManager)
        pool1.execute_workspace_command.return_value = "workspace /shows/SHOW1/seq01/0010"
        
        pool2 = Mock(spec=ProcessPoolManager)
        pool2.execute_workspace_command.return_value = "workspace /shows/SHOW2/seq01/0020"
        
        loader1 = AsyncShotLoader(pool1)
        loader2 = AsyncShotLoader(pool2)
        qtbot.addWidget(loader1)
        qtbot.addWidget(loader2)
        
        spy1 = QSignalSpy(loader1.shots_loaded)
        spy2 = QSignalSpy(loader2.shots_loaded)
        
        # Start both loaders
        loader1.start()
        loader2.start()
        
        # Wait for both
        assert loader1.wait(5000)
        assert loader2.wait(5000)
        
        # Both should complete successfully
        assert len(spy1) == 1
        assert len(spy2) == 1
        
        # Results should be different
        shots1 = spy1[0][0]
        shots2 = spy2[0][0]
        assert shots1[0].show != shots2[0].show


class TestOptimizedShotModelSignals:
    """Test OptimizedShotModel signal emission patterns."""

    @pytest.fixture
    def optimized_model(self, real_cache_manager, qtbot):
        """Create OptimizedShotModel for testing."""
        model = OptimizedShotModel(real_cache_manager)
        qtbot.addWidget(model)
        return model

    def test_background_load_signals(self, optimized_model, qtbot):
        """Test background_load_started/finished signals."""
        started_spy = QSignalSpy(optimized_model.background_load_started)
        finished_spy = QSignalSpy(optimized_model.background_load_finished)
        
        # Mock process pool to avoid real subprocess
        mock_pool = Mock()
        mock_pool.execute_workspace_command.return_value = "workspace /test/path"
        optimized_model._process_pool = mock_pool
        
        # Initialize async
        result = optimized_model.initialize_async()
        
        # Wait for background load to complete
        qtbot.waitUntil(lambda: len(finished_spy) == 1, timeout=5000)
        
        # Verify signal sequence
        assert len(started_spy) == 1
        assert len(finished_spy) == 1

    def test_shots_changed_signal_on_background_update(self, optimized_model, qtbot):
        """Test shots_changed signal emitted when background load finds changes."""
        # Pre-populate with initial shots
        optimized_model.shots = []
        
        shots_changed_spy = QSignalSpy(optimized_model.shots_changed)
        
        # Mock new data
        mock_pool = Mock()
        mock_pool.execute_workspace_command.return_value = "workspace /shows/NEW/seq01/0010"
        optimized_model._process_pool = mock_pool
        
        optimized_model.initialize_async()
        
        # Wait for background update
        qtbot.waitUntil(lambda: len(shots_changed_spy) == 1, timeout=5000)
        
        assert len(optimized_model.shots) == 1
        assert optimized_model.shots[0].show == "NEW"