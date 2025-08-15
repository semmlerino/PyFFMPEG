#!/usr/bin/env python3
"""Test script to verify ProcessPoolManager initialization fix."""

import logging
import os
import sys
import time

# Enable verbose debug mode
os.environ['SHOTBOT_DEBUG_VERBOSE'] = '1'

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

def test_pool_initialization():
    """Test that ProcessPoolManager can initialize without hanging."""
    logger.info("=" * 60)
    logger.info("Testing ProcessPoolManager initialization...")
    logger.info("=" * 60)
    
    try:
        # Mock Qt components
        from unittest.mock import MagicMock
        
        # Mock PySide6 before importing ProcessPoolManager
        sys.modules['PySide6'] = MagicMock()
        sys.modules['PySide6.QtCore'] = MagicMock()
        sys.modules['PySide6.QtCore'].QObject = object
        sys.modules['PySide6.QtCore'].Signal = MagicMock
        
        # Import after setting environment variable and mocks
        from process_pool_manager import ProcessPoolManager
        
        logger.info("Creating ProcessPoolManager instance...")
        start_time = time.time()
        
        # This should trigger lazy initialization of sessions
        pm = ProcessPoolManager.get_instance()
        
        logger.info("Executing test command to trigger session creation...")
        result = pm.execute_workspace_command("echo 'test'", timeout=10)
        
        elapsed = time.time() - start_time
        logger.info(f"✓ Command executed successfully in {elapsed:.2f}s")
        logger.info(f"✓ Result: {result.strip()}")
        
        # Test multiple commands to use the pool
        logger.info("\nTesting multiple commands...")
        for i in range(3):
            cmd = f"echo 'test_{i}'"
            result = pm.execute_workspace_command(cmd, timeout=5)
            logger.info(f"✓ Command {i+1}: {result.strip()}")
        
        # Test that all sessions were created successfully
        metrics = pm.get_metrics()
        if 'sessions' in metrics and 'workspace' in metrics['sessions']:
            pool_size = metrics['sessions']['workspace']['pool_size']
            logger.info(f"✓ Created {pool_size} sessions in pool")
        
        logger.info("\n" + "=" * 60)
        logger.info("✓ ALL TESTS PASSED - ProcessPoolManager working correctly!")
        logger.info("=" * 60)
        
        # Clean shutdown
        pm.shutdown()
        return True
        
    except Exception as e:
        logger.error(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_pool_initialization()
    sys.exit(0 if success else 1)