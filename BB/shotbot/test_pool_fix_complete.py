#!/usr/bin/env python3
"""Test script to verify ProcessPoolManager fix."""

import logging
import sys

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_pool_manager():
    """Test ProcessPoolManager initialization and basic command execution."""
    try:
        # Import ProcessPoolManager (this would fail if Qt is needed)
        # First, let's mock Qt components properly
        import sys
        from unittest.mock import MagicMock
        
        # Create a mock signal class that has emit method
        class MockSignal:
            def __init__(self, *args):
                pass
            def emit(self, *args, **kwargs):
                pass
            def connect(self, func):
                pass
        
        # Mock PySide6 before importing ProcessPoolManager
        mock_qtcore = MagicMock()
        mock_qtcore.QObject = object
        mock_qtcore.Signal = MockSignal
        
        sys.modules['PySide6'] = MagicMock()
        sys.modules['PySide6.QtCore'] = mock_qtcore
        
        # Now import ProcessPoolManager
        from process_pool_manager import ProcessPoolManager
        
        logger.info("Creating ProcessPoolManager instance...")
        manager = ProcessPoolManager.get_instance()
        logger.info("✓ ProcessPoolManager created successfully")
        
        # Test simple command execution
        logger.info("Testing simple command execution...")
        result = manager.execute_workspace_command("echo 'Hello from fixed pool'", timeout=5)
        logger.info(f"✓ Command executed: {result.strip()}")
        
        # Test caching
        logger.info("Testing command caching...")
        result2 = manager.execute_workspace_command("echo 'Hello from fixed pool'", timeout=5)
        logger.info(f"✓ Cached result: {result2.strip()}")
        
        # Get metrics
        metrics = manager.get_metrics()
        logger.info(f"✓ Metrics: subprocess_calls={metrics.get('subprocess_calls', 0)}")
        
        # Test that we didn't hang
        logger.info("✓ All tests passed - no hanging detected!")
        
        # Cleanup
        manager.shutdown()
        logger.info("✓ Shutdown completed")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_pool_manager()
    sys.exit(0 if success else 1)
