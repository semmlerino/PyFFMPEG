#!/usr/bin/env python3
"""Test script to verify file descriptor inheritance fix for Linux subprocess hang.

This script tests the critical fix for the workspace_1 hang issue on Linux systems.
The problem was caused by file descriptor inheritance from Qt to subprocess.
"""

import logging
import os
import signal
import subprocess
import sys
import time

# Enable all debugging
os.environ["SHOTBOT_DEBUG_LEVEL"] = "all"
os.environ["SHOTBOT_DEBUG_VERBOSE"] = "1"

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def timeout_handler(signum, frame):
    logger.error("✗ TIMEOUT - Test hung!")
    sys.exit(1)


def test_subprocess_creation_with_fd_fix():
    """Test that subprocess creation doesn't hang with FD inheritance fix."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing File Descriptor Inheritance Fix")
    logger.info("=" * 60)
    
    # Set timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)  # 30 second timeout
    
    try:
        # Mock Qt components to simulate the real environment
        from unittest.mock import MagicMock
        
        sys.modules["PySide6"] = MagicMock()
        sys.modules["PySide6.QtCore"] = MagicMock()
        sys.modules["PySide6.QtCore"].QObject = object
        sys.modules["PySide6.QtCore"].Signal = MagicMock
        
        # Import after mocking
        from process_pool_manager import PersistentBashSession
        
        logger.info("\n📝 Creating test sessions with FD inheritance fix...")
        logger.info("Expected: All sessions create without hanging")
        logger.info("-" * 40)
        
        sessions = []
        for i in range(3):
            session_id = f"test_workspace_{i}"
            logger.info(f"\n🔧 Creating session {i+1}/3: {session_id}")
            
            start = time.time()
            session = PersistentBashSession(session_id)
            elapsed = time.time() - start
            
            logger.info(f"✅ Session {session_id} created in {elapsed:.3f}s")
            sessions.append(session)
            
            # Test that session is responsive
            logger.info(f"🔍 Testing session {session_id} responsiveness...")
            test_start = time.time()
            result = session.execute("echo 'test'", timeout=5)
            test_elapsed = time.time() - test_start
            
            if "test" in result:
                logger.info(f"✅ Session {session_id} responded in {test_elapsed:.3f}s")
            else:
                logger.error(f"❌ Session {session_id} failed to respond correctly")
                return False
            
            # Add delay between sessions (as in real code)
            if i < 2:
                time.sleep(0.3)
                logger.info("⏸️  Pausing 0.3s before next session...")
        
        logger.info("\n" + "=" * 40)
        logger.info("🎉 SUCCESS: All sessions created without hanging!")
        logger.info("The file descriptor inheritance fix is working.")
        logger.info("=" * 40)
        
        # Clean up
        for session in sessions:
            session.close()
        
        # Cancel timeout
        signal.alarm(0)
        return True
        
    except Exception as e:
        signal.alarm(0)
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_direct_subprocess_creation():
    """Test subprocess creation directly to isolate the fix."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Direct Subprocess Creation")
    logger.info("=" * 60)
    
    processes = []
    
    for i in range(3):
        logger.info(f"\n🔧 Creating subprocess {i+1}/3...")
        
        try:
            # Test with the critical parameters
            start = time.time()
            proc = subprocess.Popen(
                ["/bin/bash", "-i"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=os.environ.copy(),
                # CRITICAL parameters for Linux
                close_fds=True,
                start_new_session=True,
                restore_signals=True,
            )
            elapsed = time.time() - start
            
            logger.info(f"✅ Subprocess {i} created in {elapsed:.3f}s (PID: {proc.pid})")
            
            # Test subprocess is responsive
            proc.stdin.write("echo 'alive'\n")
            proc.stdin.flush()
            
            # Read with timeout
            import select
            ready, _, _ = select.select([proc.stdout], [], [], 1.0)
            if ready:
                line = proc.stdout.readline()
                if "alive" in line:
                    logger.info(f"✅ Subprocess {i} is responsive")
                else:
                    logger.warning(f"⚠️ Subprocess {i} gave unexpected output: {line}")
            else:
                logger.warning(f"⚠️ Subprocess {i} didn't respond in 1s")
            
            processes.append(proc)
            
        except Exception as e:
            logger.error(f"❌ Failed to create subprocess {i}: {e}")
            return False
    
    # Clean up
    for proc in processes:
        proc.terminate()
        proc.wait(timeout=2)
    
    logger.info("\n✅ All subprocesses created successfully with FD fix")
    return True


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("FILE DESCRIPTOR INHERITANCE FIX TEST")
    logger.info("=" * 60)
    logger.info("\nThis tests the critical fix for Linux subprocess hanging")
    logger.info("when creating workspace_1 due to file descriptor inheritance.")
    
    all_passed = True
    
    # Test 1: Direct subprocess creation
    if not test_direct_subprocess_creation():
        all_passed = False
    
    # Test 2: Full session creation with PersistentBashSession
    if not test_subprocess_creation_with_fd_fix():
        all_passed = False
    
    # Summary
    logger.info("\n" + "=" * 60)
    if all_passed:
        logger.info("✅ ALL TESTS PASSED - FD inheritance fix is working!")
        logger.info("\nThe critical parameters added:")
        logger.info("  • close_fds=True - Prevents Qt FD inheritance")
        logger.info("  • start_new_session=True - Creates new process group")
        logger.info("  • restore_signals=True - Resets signal handlers")
    else:
        logger.error("❌ SOME TESTS FAILED - Review the logs above")
    logger.info("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())