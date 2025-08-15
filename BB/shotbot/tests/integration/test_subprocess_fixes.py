#!/usr/bin/env python3
"""Comprehensive integration tests for subprocess fixes.

These tests use real subprocess instances with minimal mocking to verify:
1. File descriptor inheritance fix (close_fds=True)
2. Terminal escape sequence handling (TERM=dumb)
3. Multiple session creation without hanging
4. Concurrent command execution
5. Error handling and timeouts
"""

import concurrent.futures
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Only mock Qt components - everything else should be real
from unittest.mock import MagicMock

# Mock Qt before importing our modules
sys.modules["PySide6"] = MagicMock()
sys.modules["PySide6.QtCore"] = MagicMock()
sys.modules["PySide6.QtCore"].QObject = object
sys.modules["PySide6.QtCore"].Signal = MagicMock


class TestSubprocessCreation(unittest.TestCase):
    """Test subprocess creation with FD inheritance fix."""

    def setUp(self):
        """Set up test environment."""
        # Import after mocking Qt
        from process_pool_manager import PersistentBashSession

        self.PersistentBashSession = PersistentBashSession
        self.sessions: List = []

    def tearDown(self):
        """Clean up sessions."""
        for session in self.sessions:
            try:
                session.close()
            except:
                pass

    def test_multiple_sessions_create_without_hanging(self):
        """Test that multiple sessions can be created without hanging."""
        # This tests the close_fds=True fix
        for i in range(3):
            session_id = f"test_session_{i}"
            start = time.time()

            session = self.PersistentBashSession(session_id)
            elapsed = time.time() - start

            self.sessions.append(session)

            # Should create quickly (under 2 seconds)
            self.assertLess(
                elapsed,
                2.0,
                f"Session {i} took {elapsed:.2f}s to create (possible hang)",
            )

            # Verify session is alive
            self.assertTrue(
                session._is_alive(), f"Session {i} died immediately after creation"
            )

    def test_environment_variables_set_correctly(self):
        """Test that TERM=dumb and PS1/PS2 are set."""
        session = self.PersistentBashSession("test_env")
        self.sessions.append(session)

        # Check environment by echoing variables
        result = session.execute("echo $TERM", timeout=5)
        self.assertIn("dumb", result, "TERM should be set to 'dumb'")

        # PS1 and PS2 should be empty
        result = session.execute("echo \"PS1='$PS1' PS2='$PS2'\"", timeout=5)
        self.assertIn("PS1=''", result, "PS1 should be empty")
        self.assertIn("PS2=''", result, "PS2 should be empty")

    def test_subprocess_parameters(self):
        """Test that critical subprocess parameters are set."""
        session = self.PersistentBashSession("test_params")
        self.sessions.append(session)

        # Access the internal process
        proc = session._process
        self.assertIsNotNone(proc, "Process should be created")

        # Can't directly test close_fds, start_new_session, restore_signals
        # but we can verify the process works correctly
        self.assertEqual(proc.poll(), None, "Process should be running")

        # Test that process is in a new session (Linux only)
        if os.name == "posix":
            result = session.execute("echo $$", timeout=5)
            pid = result.strip()
            if pid.isdigit():
                # Process should be in its own process group
                self.assertTrue(int(pid) > 0)


class TestEscapeSequenceHandling(unittest.TestCase):
    """Test terminal escape sequence stripping."""

    def setUp(self):
        """Set up test environment."""
        from process_pool_manager import PersistentBashSession

        self.PersistentBashSession = PersistentBashSession
        self.sessions: List = []

    def tearDown(self):
        """Clean up sessions."""
        for session in self.sessions:
            try:
                session.close()
            except:
                pass

    def test_strip_escape_sequences_method(self):
        """Test the _strip_escape_sequences method directly."""
        session = self.PersistentBashSession("test_strip")
        self.sessions.append(session)

        # Test various escape sequences
        test_cases = [
            # (input, expected_output)
            ("]777;preexec\\Hello", "Hello"),
            ("\x1b[31mRed\x1b[0m", "Red"),
            ("]777;notify;Done;test\x07", "test"),
            ("Normal\x1b[1mBold\x1b[0mNormal", "NormalBoldNormal"),
            ("\x1b]0;Title\x07Content", "Content"),
            ("Line1\n]777;preexec\\Line2", "Line1\nLine2"),
        ]

        for input_text, expected in test_cases:
            result = session._strip_escape_sequences(input_text)
            self.assertEqual(result, expected, f"Failed to strip: {repr(input_text)}")

    def test_command_output_is_clean(self):
        """Test that command output doesn't contain escape sequences."""
        session = self.PersistentBashSession("test_clean")
        self.sessions.append(session)

        # Execute commands that might produce escape sequences
        result = session.execute("echo 'Hello World'", timeout=5)

        # Check for common escape sequence patterns
        self.assertNotIn("\x1b[", result, "CSI escape sequence found")
        self.assertNotIn("]777", result, "OSC escape sequence found")
        self.assertNotIn("\x07", result, "BEL character found")
        self.assertIn("Hello World", result, "Expected output not found")

    def test_multiline_output_cleaned(self):
        """Test that multiline output is properly cleaned."""
        session = self.PersistentBashSession("test_multiline")
        self.sessions.append(session)

        # Create multiline output
        result = session.execute("echo -e 'Line1\\nLine2\\nLine3'", timeout=5)

        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 3, "Should have 3 lines")

        for i, line in enumerate(lines, 1):
            self.assertEqual(line, f"Line{i}", f"Line {i} not cleaned properly")
            # Verify no escape sequences
            self.assertNotIn("\x1b", line)
            self.assertNotIn("]777", line)


class TestCommandExecution(unittest.TestCase):
    """Test real command execution scenarios."""

    def setUp(self):
        """Set up test environment."""
        from process_pool_manager import PersistentBashSession, ProcessPoolManager

        self.PersistentBashSession = PersistentBashSession
        self.ProcessPoolManager = ProcessPoolManager
        self.sessions: List = []
        self.pool = None

    def tearDown(self):
        """Clean up resources."""
        for session in self.sessions:
            try:
                session.close()
            except:
                pass
        if self.pool:
            try:
                self.pool.shutdown()
            except:
                pass

    def test_simple_command_execution(self):
        """Test basic command execution."""
        session = self.PersistentBashSession("test_simple")
        self.sessions.append(session)

        # Test various commands
        commands = [
            ("echo 'test'", "test"),
            ("echo $HOME", os.environ.get("HOME", "")),
            ("pwd", ""),  # Just check it returns something
            ("echo $((2+2))", "4"),
        ]

        for cmd, expected in commands:
            result = session.execute(cmd, timeout=5)
            if expected:
                self.assertIn(
                    expected, result, f"Command '{cmd}' didn't return expected output"
                )

    def test_command_with_pipes(self):
        """Test commands with pipes."""
        session = self.PersistentBashSession("test_pipes")
        self.sessions.append(session)

        # Test piped commands
        result = session.execute("echo 'line1\nline2\nline3' | grep line2", timeout=5)
        self.assertIn("line2", result)
        self.assertNotIn("line1", result)
        self.assertNotIn("line3", result)

    def test_command_timeout(self):
        """Test that commands timeout correctly."""
        session = self.PersistentBashSession("test_timeout")
        self.sessions.append(session)

        # Command that takes too long
        with self.assertRaises(TimeoutError):
            session.execute("sleep 10", timeout=1)

        # Session should recover after timeout
        result = session.execute("echo 'recovered'", timeout=5)
        self.assertIn("recovered", result, "Session didn't recover after timeout")

    def test_concurrent_execution_with_pool(self):
        """Test concurrent command execution using ProcessPoolManager."""
        self.pool = self.ProcessPoolManager.get_instance()

        # Execute multiple commands concurrently
        commands = [
            "echo 'cmd1'",
            "echo 'cmd2'",
            "echo 'cmd3'",
            "echo 'cmd4'",
            "echo 'cmd5'",
        ]

        # Use batch_execute for parallel execution
        results = self.pool.batch_execute(commands, cache_ttl=0)

        # Verify all commands executed
        self.assertEqual(len(results), len(commands))

        for i, cmd in enumerate(commands, 1):
            self.assertIn(cmd, results, f"Command {cmd} not in results")
            result = results[cmd]
            self.assertIsNotNone(result, f"Command {cmd} returned None")
            self.assertIn(f"cmd{i}", result, f"Command {i} output incorrect")

    def test_session_persistence(self):
        """Test that sessions persist state between commands."""
        session = self.PersistentBashSession("test_persist")
        self.sessions.append(session)

        # Set a variable
        session.execute("TEST_VAR='persistent'", timeout=5)

        # Verify it persists
        result = session.execute("echo $TEST_VAR", timeout=5)
        self.assertIn("persistent", result, "Variable didn't persist")

        # Change directory
        session.execute("cd /tmp", timeout=5)
        result = session.execute("pwd", timeout=5)
        self.assertIn("/tmp", result, "Directory change didn't persist")


class TestErrorHandling(unittest.TestCase):
    """Test error handling and recovery."""

    def setUp(self):
        """Set up test environment."""
        from process_pool_manager import PersistentBashSession

        self.PersistentBashSession = PersistentBashSession
        self.sessions: List = []

    def tearDown(self):
        """Clean up sessions."""
        for session in self.sessions:
            try:
                session.close()
            except:
                pass

    def test_invalid_command_handling(self):
        """Test handling of invalid commands."""
        session = self.PersistentBashSession("test_invalid")
        self.sessions.append(session)

        # Execute invalid command (should not crash)
        result = session.execute("nonexistentcommand123", timeout=5)

        # Session should still work
        result = session.execute("echo 'still working'", timeout=5)
        self.assertIn("still working", result, "Session died after invalid command")

    def test_session_restart_on_death(self):
        """Test that sessions restart if they die."""
        session = self.PersistentBashSession("test_restart")
        self.sessions.append(session)

        # Kill the session process directly
        if session._process:
            session._process.kill()
            time.sleep(0.5)  # Wait for process to die

        # Next execute should restart the session
        result = session.execute("echo 'restarted'", timeout=5)
        self.assertIn("restarted", result, "Session didn't restart after death")

    def test_stress_many_commands(self):
        """Stress test with many rapid commands."""
        session = self.PersistentBashSession("test_stress")
        self.sessions.append(session)

        # Execute many commands rapidly
        for i in range(20):
            result = session.execute(f"echo 'stress{i}'", timeout=5)
            self.assertIn(f"stress{i}", result, f"Command {i} failed")

        # Session should still be healthy
        self.assertTrue(session._is_alive(), "Session died during stress test")


class TestRealWorldScenarios(unittest.TestCase):
    """Test real-world usage scenarios."""

    def setUp(self):
        """Set up test environment."""
        from process_pool_manager import ProcessPoolManager

        self.ProcessPoolManager = ProcessPoolManager
        self.pool = None

    def tearDown(self):
        """Clean up resources."""
        if self.pool:
            try:
                self.pool.shutdown()
            except:
                pass

    def test_workspace_command_simulation(self):
        """Simulate the ws -sg command scenario."""
        self.pool = self.ProcessPoolManager.get_instance()

        # Simulate ws -sg output
        mock_output = """shot001 /shows/test/shots/shot001
shot002 /shows/test/shots/shot002
shot003 /shows/test/shots/shot003"""

        # Use echo to simulate ws output
        cmd = f"echo '{mock_output}'"
        result = self.pool.execute_workspace_command(cmd, cache_ttl=0, timeout=5)

        # Verify output is clean and parseable
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 3, "Should have 3 shots")

        for line in lines:
            # Verify no escape sequences
            self.assertNotIn("\x1b", line)
            self.assertNotIn("]777", line)
            # Verify expected format
            parts = line.split()
            self.assertEqual(len(parts), 2, f"Line '{line}' not in expected format")

    def test_file_operations(self):
        """Test file operations through subprocess."""
        self.pool = self.ProcessPoolManager.get_instance()

        # Create a temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("test content\n")
            temp_path = f.name

        try:
            # Read file through subprocess
            result = self.pool.execute_workspace_command(
                f"cat {temp_path}", cache_ttl=0, timeout=5
            )
            self.assertIn("test content", result, "File content not read correctly")

            # List file
            result = self.pool.execute_workspace_command(
                f"ls -la {temp_path}", cache_ttl=0, timeout=5
            )
            self.assertIn(os.path.basename(temp_path), result, "File not listed")

        finally:
            # Clean up
            os.unlink(temp_path)

    def test_concurrent_different_commands(self):
        """Test executing different types of commands concurrently."""
        self.pool = self.ProcessPoolManager.get_instance()

        # Different command types
        commands = [
            "echo 'simple'",
            "ls /tmp | head -5",
            "date '+%Y-%m-%d'",
            "echo $HOME",
            "pwd",
        ]

        # Execute concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for cmd in commands:
                future = executor.submit(
                    self.pool.execute_workspace_command, cmd, 0, 10
                )
                futures.append((cmd, future))

            # Collect results
            for cmd, future in futures:
                try:
                    result = future.result(timeout=15)
                    self.assertIsNotNone(result, f"Command '{cmd}' returned None")
                    # Verify no escape sequences
                    self.assertNotIn("\x1b[", result)
                    self.assertNotIn("]777", result)
                except Exception as e:
                    self.fail(f"Command '{cmd}' failed: {e}")


class TestCaching(unittest.TestCase):
    """Test command caching functionality."""

    def setUp(self):
        """Set up test environment."""
        from process_pool_manager import ProcessPoolManager

        self.ProcessPoolManager = ProcessPoolManager
        self.pool = None

    def tearDown(self):
        """Clean up resources."""
        if self.pool:
            try:
                self.pool.shutdown()
            except:
                pass

    def test_cache_hit_performance(self):
        """Test that cached commands return quickly."""
        self.pool = self.ProcessPoolManager.get_instance()

        # First execution (cache miss)
        cmd = "echo 'cacheable'"
        start = time.time()
        result1 = self.pool.execute_workspace_command(cmd, cache_ttl=60, timeout=5)
        time1 = time.time() - start

        # Second execution (cache hit)
        start = time.time()
        result2 = self.pool.execute_workspace_command(cmd, cache_ttl=60, timeout=5)
        time2 = time.time() - start

        # Results should be identical
        self.assertEqual(result1, result2, "Cached result differs")

        # Cached should be much faster (at least 10x)
        self.assertLess(
            time2, time1 / 10, f"Cache not faster: {time2:.3f}s vs {time1:.3f}s"
        )

    def test_cache_invalidation(self):
        """Test cache invalidation."""
        self.pool = self.ProcessPoolManager.get_instance()

        # Execute and cache
        cmd = "date '+%s'"  # Unix timestamp
        result1 = self.pool.execute_workspace_command(cmd, cache_ttl=60, timeout=5)

        # Should get same result (cached)
        result2 = self.pool.execute_workspace_command(cmd, cache_ttl=60, timeout=5)
        self.assertEqual(result1, result2, "Should get cached result")

        # Invalidate cache
        self.pool.invalidate_cache()

        # Wait a bit to ensure timestamp changes
        time.sleep(1.1)

        # Should get new result
        result3 = self.pool.execute_workspace_command(cmd, cache_ttl=60, timeout=5)
        self.assertNotEqual(
            result1, result3, "Should get new result after invalidation"
        )


def run_tests():
    """Run all tests and report results."""
    # Set up test environment
    os.environ["SHOTBOT_DEBUG_VERBOSE"] = "0"  # Reduce noise during tests

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    test_classes = [
        TestSubprocessCreation,
        TestEscapeSequenceHandling,
        TestCommandExecution,
        TestErrorHandling,
        TestRealWorldScenarios,
        TestCaching,
    ]

    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")

    if result.wasSuccessful():
        print("\n✅ ALL TESTS PASSED!")
    else:
        print("\n❌ SOME TESTS FAILED")
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}")
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
