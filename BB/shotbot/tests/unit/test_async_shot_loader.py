#!/usr/bin/env python3
"""Critical tests for AsyncShotLoader thread safety and signal emission.

Refactored to eliminate unittest.mock and fix thread safety issues.
Follows UNIFIED_TESTING_GUIDE patterns with real components and TestProcessPool boundaries.
"""

# Third-party imports
import pytest
from PySide6.QtTest import QSignalSpy

# Local application imports
from base_shot_model import BaseShotModel
from shot_model import AsyncShotLoader, ShotModel
from tests.test_doubles_extended import TestProcessPoolDouble as TestProcessPool


class TestAsyncShotLoader:
    """Test AsyncShotLoader thread behavior and signal emission."""

    @pytest.fixture
    def test_process_pool(self):
        """Create test process pool for testing."""
        pool = TestProcessPool()
        pool.set_outputs(
            "workspace /shows/TEST/shots/seq01/TEST_seq01_0010\n"
            "workspace /shows/TEST/shots/seq01/TEST_seq01_0020\n"
            "workspace /shows/TEST/shots/seq02/TEST_seq02_0010"
        )
        return pool

    @pytest.fixture
    def loader(self, test_process_pool, qtbot):
        """Create AsyncShotLoader for testing."""
        # Create BaseShotModel instance to get the parse function
        base_model = BaseShotModel()
        loader = AsyncShotLoader(
            test_process_pool, parse_function=base_model._parse_ws_output
        )
        # AsyncShotLoader is a QThread, not a QWidget, so we don't use addWidget
        # Instead, ensure it gets properly cleaned up
        yield loader
        if loader.isRunning():
            loader.quit()
            loader.wait(1000)

    def test_loader_signals_exist(self, loader) -> None:
        """Test that AsyncShotLoader has required signals."""
        assert hasattr(loader, "shots_loaded")
        assert hasattr(loader, "load_failed")

    def test_successful_shot_loading_signal_emission(self, loader, qtbot) -> None:
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
        shots = spy.at(0)[0]  # First argument of first emission
        assert len(shots) == 3
        assert shots[0].show == "TEST"
        assert shots[0].sequence == "seq01"
        assert shots[0].shot == "0010"

    def test_failed_loading_signal_emission(self, qtbot) -> None:
        """Test load_failed signal is emitted on exception."""
        # Create failing process pool
        failing_pool = TestProcessPool()
        failing_pool.should_fail = True
        failing_pool.fail_with_message = "Command failed"

        base_model = BaseShotModel()
        loader = AsyncShotLoader(
            failing_pool, parse_function=base_model._parse_ws_output
        )
        try:
            # Use QSignalSpy for error signal
            error_spy = QSignalSpy(loader.load_failed)

            loader.start()
            assert loader.wait(5000)

            # Verify error signal emission
            assert error_spy.count() == 1
            assert "Command failed" in error_spy.at(0)[0]
        finally:
            if loader.isRunning():
                loader.quit()
                loader.wait(1000)

    def test_loader_stop_request(self, qtbot) -> None:
        """Test that stop() request prevents signal emission."""
        # Create slow process pool
        slow_pool = TestProcessPool()
        slow_pool.simulated_delay = 0.1  # Simulate slow operation
        slow_pool.set_outputs("workspace /shows/TEST/shots/seq01/TEST_seq01_0010")

        base_model = BaseShotModel()
        loader = AsyncShotLoader(slow_pool, parse_function=base_model._parse_ws_output)
        try:
            spy = QSignalSpy(loader.shots_loaded)

            # Start and immediately stop
            loader.start()
            loader.stop()

            assert loader.wait(1000)

            # No signals should be emitted when stopped
            assert spy.count() == 0
        finally:
            if loader.isRunning():
                loader.quit()
                loader.wait(1000)

    def test_thread_cleanup(self, loader, qtbot) -> None:
        """Test proper thread resource cleanup."""
        loader.start()
        assert loader.wait(5000)

        # Thread should be finished
        assert loader.isFinished()
        assert not loader.isRunning()

    def test_concurrent_loader_instances(self, qtbot) -> None:
        """Test multiple AsyncShotLoader instances don't interfere."""
        pool1 = TestProcessPool()
        pool1.set_outputs("workspace /shows/SHOW1/shots/seq01/SHOW1_seq01_0010")

        pool2 = TestProcessPool()
        pool2.set_outputs("workspace /shows/SHOW2/shots/seq01/SHOW2_seq01_0020")

        base_model1 = BaseShotModel()
        base_model2 = BaseShotModel()
        loader1 = AsyncShotLoader(pool1, parse_function=base_model1._parse_ws_output)
        loader2 = AsyncShotLoader(pool2, parse_function=base_model2._parse_ws_output)
        # loaders are QThread objects, not widgets

        try:
            spy1 = QSignalSpy(loader1.shots_loaded)
            spy2 = QSignalSpy(loader2.shots_loaded)

            # Start both loaders
            loader1.start()
            loader2.start()

            # Wait for both
            assert loader1.wait(5000)
            assert loader2.wait(5000)

            # Both should complete successfully
            assert spy1.count() == 1
            assert spy2.count() == 1

            # Results should be different
            shots1 = spy1.at(0)[0]
            shots2 = spy2.at(0)[0]
            assert shots1[0].show != shots2[0].show
        finally:
            # Clean up both loaders
            for loader in [loader1, loader2]:
                if loader.isRunning():
                    loader.quit()
                    loader.wait(1000)


class TestShotModelSignals:
    """Test ShotModel signal emission patterns."""

    @pytest.fixture
    def optimized_model(self, real_cache_manager, qtbot):
        """Create ShotModel for testing."""
        model = ShotModel(real_cache_manager)
        # model is a QObject, not a widget
        return model

    def test_background_load_signals(self, optimized_model, qtbot) -> None:
        """Test background_load_started/finished signals."""
        started_spy = QSignalSpy(optimized_model.background_load_started)
        finished_spy = QSignalSpy(optimized_model.background_load_finished)

        # Use TestProcessPool boundary mock to avoid real subprocess
        test_pool = TestProcessPool()
        test_pool.set_outputs("workspace /shows/TEST/shots/seq01/TEST_seq01_0010")
        optimized_model._process_pool = test_pool

        # Initialize async
        result = optimized_model.initialize_async()

        # Verify initialization succeeded
        assert result.success is True, "Async initialization should succeed"

        # Wait for background load to complete
        qtbot.waitUntil(lambda: finished_spy.count() == 1, timeout=5000)

        # Verify signal sequence
        assert started_spy.count() == 1
        assert finished_spy.count() == 1

    def test_shots_changed_signal_on_background_update(
        self, optimized_model, qtbot
    ) -> None:
        """Test shots_changed signal emitted when background load finds changes."""
        # Pre-populate with initial shots
        optimized_model.shots = []

        shots_changed_spy = QSignalSpy(optimized_model.shots_changed)

        # Use TestProcessPool with new data
        test_pool = TestProcessPool()
        test_pool.set_outputs("workspace /shows/NEW/shots/seq01/NEW_seq01_0010")
        optimized_model._process_pool = test_pool

        optimized_model.initialize_async()

        # Wait for background update
        qtbot.waitUntil(lambda: shots_changed_spy.count() == 1, timeout=5000)

        assert len(optimized_model.shots) == 1
        assert optimized_model.shots[0].show == "NEW"
