"""Integration tests for feature flag switching between ShotModel implementations."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from base_shot_model import BaseShotModel
from cache_manager import CacheManager
from main_window import MainWindow
from shot_model import Shot, ShotModel
from shot_model_optimized import OptimizedShotModel


class TestFeatureFlagSwitching:
    """Test feature flag switching between shot model implementations."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, qtbot):
        """Set up test environment with qtbot."""
        self.qtbot = qtbot
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)
        yield
        self.temp_dir.cleanup()

    def test_standard_model_when_flag_not_set(self, qtbot):
        """Test that OptimizedShotModel is used when legacy flag is not set (default behavior)."""
        # Clear environment variable to use default
        os.environ.pop("SHOTBOT_USE_LEGACY_MODEL", None)

        # Create main window with proper Qt management
        with patch("main_window.CacheManager") as MockCacheManager:
            mock_cache = Mock()
            mock_cache.get_cached_shots.return_value = []  # Return empty list instead of Mock
            mock_cache.get_cached_threede_scenes.return_value = []  # Fix 3DE scene iteration too
            MockCacheManager.return_value = mock_cache

            # Mock QTimer to prevent delayed operations
            with patch("PySide6.QtCore.QTimer.singleShot"):
                # Mock ProcessPoolManager to avoid subprocess calls
                with patch("shot_model_optimized.ProcessPoolManager"):
                    window = MainWindow()
                    qtbot.addWidget(window)  # CRITICAL: Register for cleanup

                    # Verify OptimizedShotModel is used by default
                    assert isinstance(window.shot_model, OptimizedShotModel)
                    assert isinstance(window.shot_model, BaseShotModel)

                    # Clean up any threads if present
                    if hasattr(window, "_threede_worker") and window._threede_worker:
                        if window._threede_worker.isRunning():
                            window._threede_worker.quit()
                            window._threede_worker.wait(1000)
                    window.close()

    def test_legacy_model_when_flag_set(self, qtbot):
        """Test that ShotModel is used when legacy flag is set."""
        # Set environment variable
        os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"

        try:
            # Create main window with proper Qt management
            with patch("main_window.CacheManager") as MockCacheManager:
                mock_cache = Mock()
                mock_cache.get_cached_shots.return_value = []  # Return empty list instead of Mock
                mock_cache.get_cached_threede_scenes.return_value = []  # Fix 3DE scene iteration too
                MockCacheManager.return_value = mock_cache

                # Mock QTimer to prevent delayed operations
                with patch("PySide6.QtCore.QTimer.singleShot"):
                    window = MainWindow()
                    qtbot.addWidget(window)  # CRITICAL: Register for cleanup

                    # Verify ShotModel is used when legacy flag is set
                    assert isinstance(window.shot_model, ShotModel)
                    assert not isinstance(window.shot_model, OptimizedShotModel)

                    # Clean up any threads if present
                    if hasattr(window, "_threede_worker") and window._threede_worker:
                        if window._threede_worker.isRunning():
                            window._threede_worker.quit()
                            window._threede_worker.wait(1000)
                    window.close()
        finally:
            # Clean up environment
            os.environ.pop("SHOTBOT_USE_LEGACY_MODEL", None)

    def test_flag_values_recognized(self, qtbot):
        """Test that various flag values are recognized correctly for legacy model."""
        test_cases = [
            ("1", True),  # Use legacy ShotModel
            ("true", True),  # Use legacy ShotModel
            ("True", True),  # Use legacy ShotModel
            ("TRUE", True),  # Use legacy ShotModel
            ("yes", True),  # Use legacy ShotModel
            ("Yes", True),  # Use legacy ShotModel
            ("YES", True),  # Use legacy ShotModel
            ("0", False),  # Use default OptimizedShotModel
            ("false", False),  # Use default OptimizedShotModel
            ("no", False),  # Use default OptimizedShotModel
            ("invalid", False),  # Use default OptimizedShotModel
            ("", False),  # Use default OptimizedShotModel
        ]

        for value, expected_legacy in test_cases:
            os.environ["SHOTBOT_USE_LEGACY_MODEL"] = value

            try:
                with patch("main_window.CacheManager") as MockCacheManager:
                    mock_cache = Mock()
                    mock_cache.get_cached_shots.return_value = []  # Return empty list instead of Mock
                    mock_cache.get_cached_threede_scenes.return_value = []  # Fix 3DE scene iteration too
                    MockCacheManager.return_value = mock_cache

                    # Mock QTimer to prevent delayed operations
                    with patch("PySide6.QtCore.QTimer.singleShot"):
                        # Handle different model types with appropriate mocking
                        if not expected_legacy:
                            # Use OptimizedShotModel, need to mock ProcessPoolManager
                            with patch("shot_model_optimized.ProcessPoolManager"):
                                window = MainWindow()
                                qtbot.addWidget(
                                    window
                                )  # CRITICAL: Register for cleanup

                                assert isinstance(
                                    window.shot_model, OptimizedShotModel
                                ), f"Expected OptimizedShotModel for value '{value}'"

                                # Clean up any threads if present
                                if (
                                    hasattr(window, "_threede_worker")
                                    and window._threede_worker
                                ):
                                    if window._threede_worker.isRunning():
                                        window._threede_worker.quit()
                                        window._threede_worker.wait(1000)
                                window.close()
                        else:
                            # Use legacy ShotModel, no ProcessPoolManager needed
                            window = MainWindow()
                            qtbot.addWidget(window)  # CRITICAL: Register for cleanup

                            assert isinstance(window.shot_model, ShotModel), (
                                f"Expected ShotModel for value '{value}'"
                            )
                            assert not isinstance(
                                window.shot_model, OptimizedShotModel
                            ), f"Should not be OptimizedShotModel for value '{value}'"

                            # Clean up any threads if present
                            if (
                                hasattr(window, "_threede_worker")
                                and window._threede_worker
                            ):
                                if window._threede_worker.isRunning():
                                    window._threede_worker.quit()
                                    window._threede_worker.wait(1000)
                            window.close()
            finally:
                os.environ.pop("SHOTBOT_USE_LEGACY_MODEL", None)

    def test_both_models_share_same_interface(self):
        """Test that both models implement the same interface."""
        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Create both models
        standard_model = ShotModel(cache_manager, load_cache=False)
        optimized_model = OptimizedShotModel(cache_manager, load_cache=False)

        # Check common methods exist in both
        common_methods = [
            "get_shots",
            "refresh_shots",
            "get_shot_count",
            "select_shot",
            "get_selected_shot",
            "find_shot_by_name",
            "get_performance_metrics",
        ]

        for method_name in common_methods:
            assert hasattr(standard_model, method_name), (
                f"ShotModel missing method: {method_name}"
            )
            assert hasattr(optimized_model, method_name), (
                f"OptimizedShotModel missing method: {method_name}"
            )

            # Verify they're callable
            assert callable(getattr(standard_model, method_name))
            assert callable(getattr(optimized_model, method_name))

    def test_signal_compatibility(self):
        """Test that both models emit compatible signals."""
        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Create both models
        standard_model = ShotModel(cache_manager, load_cache=False)
        optimized_model = OptimizedShotModel(cache_manager, load_cache=False)

        # Check common signals exist
        common_signals = [
            "shots_loaded",
            "shots_changed",
            "refresh_started",
            "refresh_finished",
            "error_occurred",
            "shot_selected",
            "cache_updated",
        ]

        for signal_name in common_signals:
            assert hasattr(standard_model, signal_name), (
                f"ShotModel missing signal: {signal_name}"
            )
            assert hasattr(optimized_model, signal_name), (
                f"OptimizedShotModel missing signal: {signal_name}"
            )

    def test_cache_sharing_between_models(self):
        """Test that cache is properly shared when switching models."""
        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Create mock shot data
        test_shots = [
            Shot("TEST", "SEQ01", "0010", "/shows/TEST/shots/SEQ01/0010"),
            Shot("TEST", "SEQ01", "0020", "/shows/TEST/shots/SEQ01/0020"),
        ]

        # Cache shots using standard model
        cache_manager.cache_shots(test_shots)

        # Load with standard model
        standard_model = ShotModel(cache_manager, load_cache=True)
        assert len(standard_model.get_shots()) == 2

        # Load with optimized model - should get same cached data
        optimized_model = OptimizedShotModel(cache_manager, load_cache=True)
        assert len(optimized_model.get_shots()) == 2

        # Verify the shots are the same
        standard_shots = {s.full_name for s in standard_model.get_shots()}
        optimized_shots = {s.full_name for s in optimized_model.get_shots()}
        assert standard_shots == optimized_shots

    def test_cleanup_on_model_switch(self):
        """Test that cleanup is properly handled when switching models."""
        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Create optimized model with mock async loader
        optimized_model = OptimizedShotModel(cache_manager, load_cache=False)

        # Mock async loader
        mock_loader = Mock()
        mock_loader.isRunning.return_value = True
        mock_loader.wait.return_value = True
        optimized_model._async_loader = mock_loader

        # Call cleanup
        optimized_model.cleanup()

        # Verify cleanup was called
        mock_loader.stop.assert_called_once()
        mock_loader.wait.assert_called()
        mock_loader.deleteLater.assert_called_once()

        # Verify loader was cleared
        assert optimized_model._async_loader is None

    def test_performance_metrics_available_in_both(self):
        """Test that performance metrics are available in both models."""
        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Create both models
        standard_model = ShotModel(cache_manager, load_cache=False)
        optimized_model = OptimizedShotModel(cache_manager, load_cache=False)

        # Get metrics from both
        standard_metrics = standard_model.get_performance_metrics()
        optimized_metrics = optimized_model.get_performance_metrics()

        # Both should return dictionaries with some common keys
        assert isinstance(standard_metrics, dict)
        assert isinstance(optimized_metrics, dict)

        # Check for some expected keys
        expected_keys = ["total_shots", "cache_hits", "cache_misses"]
        for key in expected_keys:
            assert key in standard_metrics, f"Missing {key} in standard metrics"
            assert key in optimized_metrics, f"Missing {key} in optimized metrics"

        # Optimized model should have additional metrics
        assert "loading_in_progress" in optimized_metrics
        assert "session_warmed" in optimized_metrics


class TestMainWindowIntegration:
    """Test MainWindow integration with different shot models."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, qtbot):
        """Set up test environment with qtbot."""
        self.qtbot = qtbot
        yield

    def test_window_initialization_with_default_model(self, qtbot):
        """Test that MainWindow initializes correctly with default optimized model."""
        os.environ.pop("SHOTBOT_USE_LEGACY_MODEL", None)

        with patch("main_window.CacheManager") as MockCacheManager:
            mock_cache = Mock()
            mock_cache.get_cached_shots.return_value = []  # Return empty list instead of Mock
            mock_cache.get_cached_threede_scenes.return_value = []  # Fix 3DE scene iteration too
            MockCacheManager.return_value = mock_cache

            # Mock QTimer to prevent delayed operations
            with patch("PySide6.QtCore.QTimer.singleShot"):
                # Mock ProcessPoolManager for OptimizedShotModel
                with patch("shot_model_optimized.ProcessPoolManager"):
                    # Should not raise any exceptions
                    window = MainWindow()
                    qtbot.addWidget(window)  # CRITICAL: Register for cleanup
                    assert window is not None
                    assert window.shot_model is not None
                    assert isinstance(window.shot_model, OptimizedShotModel)

                    # Clean up any threads if present
                    if hasattr(window, "_threede_worker") and window._threede_worker:
                        if window._threede_worker.isRunning():
                            window._threede_worker.quit()
                            window._threede_worker.wait(1000)
                    window.close()

    def test_window_initialization_with_legacy_model(self, qtbot):
        """Test that MainWindow initializes correctly with legacy model."""
        os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"

        try:
            with patch("main_window.CacheManager") as MockCacheManager:
                mock_cache = Mock()
                mock_cache.get_cached_shots.return_value = []  # Return empty list
                mock_cache.get_cached_threede_scenes.return_value = []  # Fix 3DE scene iteration
                MockCacheManager.return_value = mock_cache

                # Mock QTimer to prevent delayed operations
                with patch("PySide6.QtCore.QTimer.singleShot"):
                    # Should not raise any exceptions
                    window = MainWindow()
                    qtbot.addWidget(window)  # CRITICAL: Register for cleanup
                    assert window is not None
                    assert window.shot_model is not None
                    assert isinstance(window.shot_model, ShotModel)
                    assert not isinstance(window.shot_model, OptimizedShotModel)

                    # Clean up any threads if present
                    if hasattr(window, "_threede_worker") and window._threede_worker:
                        if window._threede_worker.isRunning():
                            window._threede_worker.quit()
                            window._threede_worker.wait(1000)
                    window.close()
        finally:
            os.environ.pop("SHOTBOT_USE_LEGACY_MODEL", None)

    def test_closeEvent_handles_optimized_model(self, qtbot):
        """Test that closeEvent properly handles OptimizedShotModel cleanup (default behavior)."""
        # Use default OptimizedShotModel (no environment variable needed)
        os.environ.pop("SHOTBOT_USE_LEGACY_MODEL", None)

        try:
            with patch("main_window.CacheManager") as MockCacheManager:
                mock_cache = Mock()
                mock_cache.get_cached_shots.return_value = []  # Return empty list instead of Mock
                mock_cache.get_cached_threede_scenes.return_value = []  # Fix 3DE scene iteration too
                MockCacheManager.return_value = mock_cache

                # Mock QTimer to prevent delayed operations
                with patch("PySide6.QtCore.QTimer.singleShot"):
                    with patch("shot_model_optimized.ProcessPoolManager"):
                        window = MainWindow()
                        qtbot.addWidget(window)  # CRITICAL: Register for cleanup

                        # Mock the cleanup method
                        window.shot_model.cleanup = Mock()

                        # Create mock close event
                        mock_event = Mock()

                        # Call closeEvent
                        window.closeEvent(mock_event)

                        # Verify cleanup was called
                        window.shot_model.cleanup.assert_called_once()
        finally:
            pass  # No cleanup needed for default behavior


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
