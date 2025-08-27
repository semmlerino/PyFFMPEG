"""Integration tests for feature flag switching between ShotModel implementations."""

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shot_model import ShotModel, Shot, RefreshResult
from shot_model_optimized import OptimizedShotModel
from base_shot_model import BaseShotModel
from cache_manager import CacheManager
from main_window import MainWindow


class TestFeatureFlagSwitching:
    """Test feature flag switching between shot model implementations."""
    
    def setup_method(self):
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)
        
    def teardown_method(self):
        """Clean up test environment."""
        self.temp_dir.cleanup()
    
    def test_standard_model_when_flag_not_set(self):
        """Test that ShotModel is used when feature flag is not set."""
        # Clear environment variable
        os.environ.pop("SHOTBOT_OPTIMIZED_MODE", None)
        
        # Create main window
        with patch('main_window.CacheManager') as MockCacheManager:
            mock_cache = Mock()
            MockCacheManager.return_value = mock_cache
            
            window = MainWindow()
            
            # Verify standard ShotModel is used
            assert isinstance(window.shot_model, ShotModel)
            assert not isinstance(window.shot_model, OptimizedShotModel)
    
    def test_optimized_model_when_flag_set(self):
        """Test that OptimizedShotModel is used when feature flag is set."""
        # Set environment variable
        os.environ["SHOTBOT_OPTIMIZED_MODE"] = "1"
        
        try:
            # Create main window
            with patch('main_window.CacheManager') as MockCacheManager:
                mock_cache = Mock()
                MockCacheManager.return_value = mock_cache
                
                window = MainWindow()
                
                # Verify OptimizedShotModel is used
                assert isinstance(window.shot_model, OptimizedShotModel)
                assert isinstance(window.shot_model, BaseShotModel)
        finally:
            # Clean up environment
            os.environ.pop("SHOTBOT_OPTIMIZED_MODE", None)
    
    def test_flag_values_recognized(self):
        """Test that various flag values are recognized correctly."""
        test_cases = [
            ("1", True),
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("yes", True),
            ("Yes", True),
            ("YES", True),
            ("0", False),
            ("false", False),
            ("no", False),
            ("invalid", False),
            ("", False),
        ]
        
        for value, expected_optimized in test_cases:
            os.environ["SHOTBOT_OPTIMIZED_MODE"] = value
            
            try:
                with patch('main_window.CacheManager') as MockCacheManager:
                    mock_cache = Mock()
                    MockCacheManager.return_value = mock_cache
                    
                    window = MainWindow()
                    
                    if expected_optimized:
                        assert isinstance(window.shot_model, OptimizedShotModel), \
                            f"Expected OptimizedShotModel for value '{value}'"
                    else:
                        assert isinstance(window.shot_model, ShotModel), \
                            f"Expected ShotModel for value '{value}'"
                        assert not isinstance(window.shot_model, OptimizedShotModel), \
                            f"Should not be OptimizedShotModel for value '{value}'"
            finally:
                os.environ.pop("SHOTBOT_OPTIMIZED_MODE", None)
    
    def test_both_models_share_same_interface(self):
        """Test that both models implement the same interface."""
        cache_manager = CacheManager(cache_dir=self.cache_dir)
        
        # Create both models
        standard_model = ShotModel(cache_manager, load_cache=False)
        optimized_model = OptimizedShotModel(cache_manager, load_cache=False)
        
        # Check common methods exist in both
        common_methods = [
            'get_shots',
            'refresh_shots',
            'get_shot_count',
            'select_shot',
            'get_selected_shot',
            'find_shot_by_name',
            'get_performance_metrics',
        ]
        
        for method_name in common_methods:
            assert hasattr(standard_model, method_name), \
                f"ShotModel missing method: {method_name}"
            assert hasattr(optimized_model, method_name), \
                f"OptimizedShotModel missing method: {method_name}"
            
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
            'shots_loaded',
            'shots_changed',
            'refresh_started',
            'refresh_finished',
            'error_occurred',
            'shot_selected',
            'cache_updated',
        ]
        
        for signal_name in common_signals:
            assert hasattr(standard_model, signal_name), \
                f"ShotModel missing signal: {signal_name}"
            assert hasattr(optimized_model, signal_name), \
                f"OptimizedShotModel missing signal: {signal_name}"
    
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
        expected_keys = ['total_shots', 'cache_hits', 'cache_misses']
        for key in expected_keys:
            assert key in standard_metrics, f"Missing {key} in standard metrics"
            assert key in optimized_metrics, f"Missing {key} in optimized metrics"
        
        # Optimized model should have additional metrics
        assert 'loading_in_progress' in optimized_metrics
        assert 'session_warmed' in optimized_metrics


class TestMainWindowIntegration:
    """Test MainWindow integration with different shot models."""
    
    def setup_method(self):
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        
    def test_window_initialization_with_standard_model(self):
        """Test that MainWindow initializes correctly with standard model."""
        os.environ.pop("SHOTBOT_OPTIMIZED_MODE", None)
        
        with patch('main_window.CacheManager') as MockCacheManager:
            mock_cache = Mock()
            MockCacheManager.return_value = mock_cache
            
            # Should not raise any exceptions
            window = MainWindow()
            assert window is not None
            assert window.shot_model is not None
    
    def test_window_initialization_with_optimized_model(self):
        """Test that MainWindow initializes correctly with optimized model."""
        os.environ["SHOTBOT_OPTIMIZED_MODE"] = "1"
        
        try:
            with patch('main_window.CacheManager') as MockCacheManager:
                mock_cache = Mock()
                MockCacheManager.return_value = mock_cache
                
                # Mock ProcessPoolManager to avoid subprocess calls
                with patch('shot_model_optimized.ProcessPoolManager'):
                    # Should not raise any exceptions
                    window = MainWindow()
                    assert window is not None
                    assert window.shot_model is not None
                    assert isinstance(window.shot_model, OptimizedShotModel)
        finally:
            os.environ.pop("SHOTBOT_OPTIMIZED_MODE", None)
    
    def test_closeEvent_handles_optimized_model(self):
        """Test that closeEvent properly handles OptimizedShotModel cleanup."""
        os.environ["SHOTBOT_OPTIMIZED_MODE"] = "1"
        
        try:
            with patch('main_window.CacheManager') as MockCacheManager:
                mock_cache = Mock()
                MockCacheManager.return_value = mock_cache
                
                with patch('shot_model_optimized.ProcessPoolManager'):
                    window = MainWindow()
                    
                    # Mock the cleanup method
                    window.shot_model.cleanup = Mock()
                    
                    # Create mock close event
                    mock_event = Mock()
                    
                    # Call closeEvent
                    window.closeEvent(mock_event)
                    
                    # Verify cleanup was called
                    window.shot_model.cleanup.assert_called_once()
        finally:
            os.environ.pop("SHOTBOT_OPTIMIZED_MODE", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])