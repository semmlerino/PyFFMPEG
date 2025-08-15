#!/usr/bin/env python3
"""Test script to verify multiple session creation doesn't hang."""

import logging
import os
import signal
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

def timeout_handler(signum, frame):
    logger.error("✗ TIMEOUT - Session creation hung!")
    sys.exit(1)

def test_session_creation():
    """Test that creating multiple sessions doesn't hang."""
    logger.info("=" * 60)
    logger.info("Testing multiple session creation...")
    logger.info("=" * 60)
    
    # Set a timeout to detect hangs
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)  # 30 second timeout
    
    try:
        # Mock Qt components
        from unittest.mock import MagicMock
        sys.modules['PySide6'] = MagicMock()
        sys.modules['PySide6.QtCore'] = MagicMock()
        sys.modules['PySide6.QtCore'].QObject = object
        sys.modules['PySide6.QtCore'].Signal = MagicMock
        
        # Import after mocking
        from process_pool_manager import PersistentBashSession
        
        logger.info("Creating individual sessions to test for hangs...")
        
        # Test creating multiple sessions directly
        sessions = []
        for i in range(3):
            logger.info(f"\nCreating session {i+1}/3...")
            start = time.time()
            
            session = PersistentBashSession(f"test_session_{i}")
            elapsed = time.time() - start
            
            logger.info(f"✓ Session {i+1} created in {elapsed:.2f}s")
            sessions.append(session)
            
            # Small delay between sessions (as in the pool manager)
            if i < 2:
                time.sleep(0.1)
        
        logger.info("\nTesting command execution on each session...")
        for i, session in enumerate(sessions):
            result = session.execute("echo 'test'", timeout=5)
            logger.info(f"✓ Session {i+1} executed command: {result.strip()}")
        
        logger.info("\nCleaning up sessions...")
        for session in sessions:
            session.close()
        
        # Cancel timeout
        signal.alarm(0)
        
        logger.info("\n" + "=" * 60)
        logger.info("✓ ALL TESTS PASSED - No hanging detected!")
        logger.info("=" * 60)
        return True
        
    except Exception as e:
        signal.alarm(0)  # Cancel timeout
        logger.error(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_session_creation()
    sys.exit(0 if success else 1)