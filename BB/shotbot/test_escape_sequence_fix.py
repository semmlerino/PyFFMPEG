#!/usr/bin/env python3
"""Test script to verify terminal escape sequence handling fix.

This tests that:
1. TERM=dumb prevents most escape sequences
2. Any remaining sequences are stripped from output
3. Commands return clean, parseable output
"""

import logging
import os
import sys
import time

# Enable debugging
os.environ["SHOTBOT_DEBUG_LEVEL"] = "all"
os.environ["SHOTBOT_DEBUG_VERBOSE"] = "1"

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def test_escape_sequence_stripping():
    """Test that escape sequences are properly stripped from output."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Terminal Escape Sequence Handling")
    logger.info("=" * 60)
    
    try:
        # Mock Qt components
        from unittest.mock import MagicMock
        
        sys.modules["PySide6"] = MagicMock()
        sys.modules["PySide6.QtCore"] = MagicMock()
        sys.modules["PySide6.QtCore"].QObject = object
        sys.modules["PySide6.QtCore"].Signal = MagicMock
        
        # Import after mocking
        from process_pool_manager import PersistentBashSession
        
        logger.info("\n📝 Testing command output with escape sequence handling...")
        
        # Create a test session
        session = PersistentBashSession("test_escape_sequences")
        
        # Test 1: Simple echo command
        logger.info("\n🔧 Test 1: Simple echo command")
        result = session.execute("echo 'Hello World'", timeout=5)
        logger.info(f"Output: '{result}'")
        
        # Check for clean output
        if "Hello World" in result and "]777" not in result and "\x1b" not in result:
            logger.info("✅ Clean output - no escape sequences")
        else:
            logger.error(f"❌ Output contains escape sequences or is corrupted")
            logger.error(f"Raw output repr: {repr(result)}")
            return False
        
        # Test 2: Command with potential color output
        logger.info("\n🔧 Test 2: Command with potential color output")
        result = session.execute("ls --color=never /tmp | head -5", timeout=5)
        logger.info(f"Output length: {len(result)} chars")
        
        # Check for escape sequences
        if "\x1b[" not in result and "]777" not in result:
            logger.info("✅ No escape sequences in ls output")
        else:
            logger.error("❌ Escape sequences found in output")
            return False
        
        # Test 3: Test the specific ws -sg scenario
        logger.info("\n🔧 Test 3: Simulating ws -sg command")
        # Since ws might not exist, simulate with echo
        test_output = """shot1 /path/to/shot1
shot2 /path/to/shot2
shot3 /path/to/shot3"""
        result = session.execute(f"echo '{test_output}'", timeout=5)
        
        # Parse the output
        lines = result.strip().split('\n')
        logger.info(f"Parsed {len(lines)} lines")
        
        for i, line in enumerate(lines):
            logger.info(f"  Line {i+1}: '{line}'")
            # Check each line is clean
            if "\x1b" in line or "]777" in line:
                logger.error(f"❌ Line {i+1} contains escape sequences")
                return False
        
        logger.info("✅ All lines are clean and parseable")
        
        # Test 4: Multiple commands in sequence
        logger.info("\n🔧 Test 4: Multiple commands in sequence")
        commands = [
            "echo 'Test 1'",
            "echo 'Test 2'",
            "echo 'Test 3'"
        ]
        
        for cmd in commands:
            result = session.execute(cmd, timeout=5)
            expected = cmd.split("'")[1]
            if expected in result and "\x1b" not in result:
                logger.info(f"✅ Command '{cmd}' returned clean output")
            else:
                logger.error(f"❌ Command '{cmd}' failed or has escape sequences")
                return False
        
        # Clean up
        session.close()
        
        logger.info("\n" + "=" * 40)
        logger.info("🎉 SUCCESS: All escape sequence tests passed!")
        logger.info("Terminal output is clean and parseable.")
        logger.info("=" * 40)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_strip_function():
    """Test the escape sequence stripping function directly."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Escape Sequence Stripping Function")
    logger.info("=" * 60)
    
    try:
        # Import the stripping function
        from unittest.mock import MagicMock
        sys.modules["PySide6"] = MagicMock()
        sys.modules["PySide6.QtCore"] = MagicMock()
        
        from process_pool_manager import PersistentBashSession
        session = PersistentBashSession("test_strip")
        
        # Test cases with various escape sequences
        test_cases = [
            ("]777;preexec\\SHOTBOT_INIT_abc123", "SHOTBOT_INIT_abc123"),
            ("\x1b[31mRed Text\x1b[0m", "Red Text"),
            ("]777;notify;Command completed;test\x07", "test"),
            ("Normal text\x1b[1;32m green \x1b[0m normal", "Normal text green  normal"),
            ("\x1b]0;Terminal Title\x07Content", "Content"),
        ]
        
        logger.info("\nTesting escape sequence stripping...")
        for input_text, expected in test_cases:
            result = session._strip_escape_sequences(input_text)
            if result == expected:
                logger.info(f"✅ Correctly stripped: '{input_text[:30]}...' → '{result}'")
            else:
                logger.error(f"❌ Failed to strip: '{input_text}'")
                logger.error(f"   Expected: '{expected}'")
                logger.error(f"   Got: '{result}'")
                return False
        
        session.close()
        logger.info("\n✅ All stripping tests passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Strip function test failed: {e}")
        return False


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("TERMINAL ESCAPE SEQUENCE FIX TEST")
    logger.info("=" * 60)
    logger.info("\nThis tests that terminal escape sequences don't")
    logger.info("interfere with command output parsing.")
    
    all_passed = True
    
    # Test 1: Direct stripping function
    if not test_strip_function():
        all_passed = False
    
    # Test 2: Full integration test
    if not test_escape_sequence_stripping():
        all_passed = False
    
    # Summary
    logger.info("\n" + "=" * 60)
    if all_passed:
        logger.info("✅ ALL TESTS PASSED - Escape sequence handling works!")
        logger.info("\nThe fixes applied:")
        logger.info("  • TERM=dumb - Prevents most escape sequences")
        logger.info("  • PS1='' PS2='' - Clears prompts")
        logger.info("  • Escape stripping - Removes any remaining sequences")
    else:
        logger.error("❌ SOME TESTS FAILED - Review the logs above")
    logger.info("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())