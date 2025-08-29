"""Refactored ProcessPoolManager tests following UNIFIED_TESTING_GUIDE principles.

This refactored version demonstrates:
1. NO Mock() usage - uses test doubles with realistic behavior
2. Tests behavior through state changes and outcomes
3. Only mocks at system boundaries (subprocess)
4. Tests actual functionality, not implementation details

Key improvements over the original:
- Removed Mock() and @patch decorators
- Created BashSessionDouble with realistic behavior
- Tests actual caching behavior, not mock calls
- Verifies outcomes, not method invocations
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from process_pool_manager import (
    CommandCache,
    ProcessMetrics,
    ProcessPoolManager,
)

pytestmark = [pytest.mark.unit, pytest.mark.slow]


# =============================================================================
# TEST DOUBLES AT SYSTEM BOUNDARY
# =============================================================================


class BashSessionDouble:
    """Test double for PersistentBashSession at system boundary.

    Provides realistic bash session behavior without actual subprocess.
    This is the ONLY place we mock - at the actual system boundary.
    """

    def __init__(self):
        """Initialize with predictable behavior."""
        self.executed_commands: list[str] = []
        self.responses: dict[str, str] = {}
        self.should_fail = False
        self.failure_message = "Command failed"
        self.execution_delay = 0.0  # Simulate execution time
        self.is_closed = False

    def execute(self, command: str, timeout: float | None = None) -> str:
        """Execute command with realistic behavior."""
        if self.is_closed:
            raise RuntimeError("Session is closed")

        self.executed_commands.append(command)

        # Simulate execution delay
        if self.execution_delay > 0:
            time.sleep(self.execution_delay)

        # Handle failure scenarios
        if self.should_fail:
            raise Exception(self.failure_message)

        # Return configured response first (highest priority)
        if command in self.responses:
            return self.responses[command]

        # Generate realistic default responses
        if command.startswith("echo "):
            return command[5:]  # Return what echo would output
        elif command.startswith("ls "):
            return "file1.txt\nfile2.txt\nfile3.txt"
        elif command == "pwd":
            return "/home/user/workspace"
        else:
            return f"Output for: {command}"

    def set_response(self, command: str, response: str):
        """Configure specific response for testing."""
        self.responses[command] = response

    def close(self):
        """Close the session."""
        self.is_closed = True

    def reset(self):
        """Reset for fresh test."""
        self.executed_commands.clear()
        self.responses.clear()
        self.should_fail = False
        self.is_closed = False


class InjectableProcessPoolManager(ProcessPoolManager):
    """ProcessPoolManager with dependency injection for testing.

    Allows injection of BashSessionDouble without mocking the manager itself.
    Bypasses singleton pattern to ensure fresh instances for each test.
    """

    def __new__(cls, *args, **kwargs):
        """Override to bypass singleton pattern in tests."""
        # Don't use singleton for test instances - use QObject's __new__
        from PySide6.QtCore import QObject

        instance = QObject.__new__(cls)
        return instance

    def __init__(self, max_workers: int = 4):
        """Initialize with optional session injection."""
        # Initialize directly without calling super().__init__() to avoid singleton issues
        import concurrent.futures
        import threading

        from PySide6.QtCore import QObject

        QObject.__init__(self)  # Initialize QObject directly

        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._session_pools: dict[str, list[BashSessionDouble]] = {}
        self._session_round_robin: dict[str, int] = {}
        self._sessions_per_type = 3
        self._cache = CommandCache(default_ttl=30)
        self._session_lock = threading.RLock()
        self._metrics = ProcessMetrics()
        self._initialized = True
        self._test_session: BashSessionDouble | None = None

    def set_test_session(self, session: BashSessionDouble):
        """Inject test session for testing."""
        self._test_session = session

    def _get_bash_session(self, session_type: str):
        """Override to return injected test session when available."""
        if self._test_session:
            return self._test_session
        return super()._get_bash_session(session_type)


# =============================================================================
# BEHAVIOR-FOCUSED TEST CLASSES
# =============================================================================


class TestCommandCacheBehavior:
    """Test CommandCache behavior through state changes."""

    def test_cache_stores_and_retrieves_values(self):
        """Test that cache correctly stores and retrieves values.

        CORRECT: Testing actual behavior, not implementation.
        """
        cache = CommandCache(default_ttl=10)

        # Store value
        cache.set("echo test", "test output", ttl=5)

        # Test BEHAVIOR: Value can be retrieved
        result = cache.get("echo test")
        assert result == "test output"

        # Test BEHAVIOR: Non-existent key returns None
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_respects_ttl(self):
        """Test that cache respects TTL expiration.

        CORRECT: Testing time-based behavior, not mocking time.
        """
        cache = CommandCache(default_ttl=0.1)  # 100ms TTL

        # Store value with short TTL
        cache.set("temp_key", "temp_value", ttl=0.1)

        # Test BEHAVIOR: Value available immediately
        assert cache.get("temp_key") == "temp_value"

        # Wait for expiration
        time.sleep(0.15)

        # Test BEHAVIOR: Value expired
        assert cache.get("temp_key") is None

    def test_cache_tracks_statistics(self):
        """Test that cache tracks hit/miss statistics.

        CORRECT: Testing observable behavior through stats.
        """
        cache = CommandCache()

        # Set up cache state
        cache.set("existing", "value")

        # Generate hits and misses
        cache.get("existing")  # Hit
        cache.get("existing")  # Hit
        cache.get("missing")  # Miss
        cache.get("missing2")  # Miss
        cache.get("missing3")  # Miss

        # Test BEHAVIOR: Statistics are tracked correctly
        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 3
        assert stats["hit_rate"] == 40.0  # 40%

    def test_cache_invalidation_by_pattern(self):
        """Test selective cache invalidation.

        CORRECT: Testing outcome of invalidation, not method calls.
        """
        cache = CommandCache()

        # Set up cache with commands that will be stored in value[3]
        # The cache stores (result, timestamp, ttl, command) tuples
        # and invalidate() checks if pattern is in the command
        cache.set("test_cmd1", "output1")  # command="test_cmd1"
        cache.set("test_cmd2", "output2")  # command="test_cmd2"
        cache.set("other_cmd", "output3")  # command="other_cmd"
        cache.set("another_test", "output4")  # command="another_test"

        # Invalidate by pattern - checks if pattern is IN the command string
        cache.invalidate(pattern="test_")

        # Test BEHAVIOR: Entries with "test_" in command are invalidated
        assert cache.get("test_cmd1") is None  # Has "test_" in command
        assert cache.get("test_cmd2") is None  # Has "test_" in command
        assert cache.get("other_cmd") == "output3"  # Doesn't have "test_"
        assert cache.get("another_test") == "output4"  # Has "test" but not "test_"


class TestProcessMetricsBehavior:
    """Test ProcessMetrics behavior and calculations."""

    def test_metrics_track_operations(self):
        """Test that metrics track operations correctly.

        CORRECT: Testing state changes, not internal counters.
        """
        metrics = ProcessMetrics()

        # Perform operations that should be tracked
        metrics.subprocess_calls += 1
        metrics.subprocess_calls += 1
        metrics.cache_hits += 3
        metrics.python_operations += 5

        # Record response times
        metrics.update_response_time(100)
        metrics.update_response_time(200)
        metrics.update_response_time(150)

        # Test BEHAVIOR: Metrics reflect operations
        report = metrics.get_report()
        assert report["subprocess_calls"] == 2
        assert report["python_operations"] == 5
        assert report["average_response_ms"] == 150  # (100+200+150)/3

    def test_metrics_reset_functionality(self):
        """Test that metrics can be reinitialized.

        CORRECT: Testing observable state after creating new instance.
        """
        # Generate some metrics in first instance
        metrics = ProcessMetrics()
        metrics.subprocess_calls = 10
        metrics.cache_hits = 20
        metrics.update_response_time(500)

        # Create fresh instance (since ProcessMetrics has no reset method)
        metrics = ProcessMetrics()

        # Test BEHAVIOR: New instance starts with clean state
        assert metrics.subprocess_calls == 0
        assert metrics.cache_hits == 0
        assert metrics.response_count == 0


class TestProcessPoolManagerBehavior:
    """Test ProcessPoolManager behavior with injected dependencies."""

    def test_singleton_ensures_single_instance(self):
        """Test that singleton pattern creates only one instance.

        CORRECT: Testing behavior (single instance), not implementation.
        """
        # Reset singleton for test isolation
        ProcessPoolManager._instance = None

        # Create multiple "instances"
        manager1 = ProcessPoolManager(max_workers=2)
        manager2 = ProcessPoolManager(max_workers=4)
        manager3 = ProcessPoolManager()

        # Test BEHAVIOR: All references point to same instance
        assert manager1 is manager2
        assert manager2 is manager3

        # Cleanup
        manager1.shutdown()
        ProcessPoolManager._instance = None

    def test_command_execution_with_caching(self):
        """Test that commands are cached and reused.

        CORRECT: Using test double at system boundary, testing behavior.
        """
        # Reset singleton
        ProcessPoolManager._instance = None

        # Create manager with injected session
        manager = InjectableProcessPoolManager()
        session = BashSessionDouble()
        # Don't set custom response - use default echo logic that returns "hello" for "echo hello"
        manager.set_test_session(session)

        # First execution - should call session
        result1 = manager.execute_workspace_command("echo hello", cache_ttl=10)
        # The BashSessionDouble returns "hello" for "echo hello" commands (default logic)
        assert result1 == "hello"
        assert len(session.executed_commands) == 1

        # Second execution - should use cache
        result2 = manager.execute_workspace_command("echo hello", cache_ttl=10)
        assert result2 == "hello"
        assert len(session.executed_commands) == 1  # Still 1, used cache

        # Test BEHAVIOR: Cache statistics reflect usage
        metrics = manager.get_metrics()
        assert metrics["cache_stats"]["hits"] == 1
        assert metrics["cache_stats"]["misses"] == 1

        # Cleanup InjectableProcessPoolManager (it bypasses singleton)
        manager.shutdown()

    def test_batch_command_execution(self):
        """Test batch execution of multiple commands.

        CORRECT: Testing actual batch behavior, not mocked responses.
        """
        # Reset singleton
        ProcessPoolManager._instance = None

        manager = InjectableProcessPoolManager()
        session = BashSessionDouble()

        # Configure realistic responses
        session.set_response("ls /tmp", "file1\nfile2")
        session.set_response("pwd", "/home/user")
        session.set_response("echo done", "done")

        manager.set_test_session(session)

        # Execute batch
        commands = ["ls /tmp", "pwd", "echo done"]
        results = manager.batch_execute(commands)

        # Test BEHAVIOR: All commands executed and results returned
        assert len(results) == 3
        assert results["ls /tmp"] == "file1\nfile2"
        assert results["pwd"] == "/home/user"
        assert results["echo done"] == "done"

        # Test BEHAVIOR: Commands were executed in order
        assert session.executed_commands == commands

        # Cleanup InjectableProcessPoolManager (it bypasses singleton)
        manager.shutdown()

    def test_error_recovery_during_execution(self):
        """Test that manager recovers from execution errors.

        CORRECT: Testing error recovery behavior, not error detection.
        """
        ProcessPoolManager._instance = None

        manager = InjectableProcessPoolManager()
        session = BashSessionDouble()

        # Configure session to fail initially
        session.should_fail = True
        session.failure_message = "Connection lost"

        manager.set_test_session(session)

        # First execution should handle error gracefully
        try:
            result = manager.execute_workspace_command("echo test")
        except Exception as e:
            assert "Connection lost" in str(e)

        # Reset session to working state
        session.should_fail = False
        session.reset()

        # Test BEHAVIOR: Manager recovers and works after error
        result = manager.execute_workspace_command("echo recovered")
        assert result == "recovered"

        # Cleanup InjectableProcessPoolManager (it bypasses singleton)
        manager.shutdown()

    def test_concurrent_access_thread_safety(self):
        """Test thread-safe access to singleton.

        CORRECT: Testing actual concurrent behavior, not locking mechanism.
        FIXED: Create ProcessPoolManager in main thread to avoid Qt threading violations.
        """
        ProcessPoolManager._instance = None

        # Create the singleton instance in the MAIN thread (Qt requirement)
        # QObjects must be created in the thread where they will live
        main_manager = ProcessPoolManager()

        managers = []
        results = []

        def access_manager(index):
            """Thread function to access existing manager."""
            # Access the already-created singleton (don't create new QObject in thread)
            manager = ProcessPoolManager()  # This returns the existing singleton
            managers.append(manager)

            # Use manager - find_files_python is thread-safe since it doesn't create Qt objects
            result = manager.find_files_python(".", "*.txt")
            results.append((index, result))

        # Create multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=access_manager, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Test BEHAVIOR: All threads got same instance
        assert all(m is main_manager for m in managers)
        assert all(m is managers[0] for m in managers)

        # Test BEHAVIOR: All threads completed successfully
        assert len(results) == 10

        # Cleanup
        main_manager.shutdown()
        ProcessPoolManager._instance = None


class TestPythonFileOperations:
    """Test Python-based file operations without subprocess."""

    def test_find_files_in_directory(self, tmp_path):
        """Test file finding using Python glob.

        CORRECT: Using real filesystem with temp directory.
        """
        ProcessPoolManager._instance = None
        manager = ProcessPoolManager()

        # Create test directory structure
        test_dir = tmp_path / "test_files"
        test_dir.mkdir()

        # Create test files
        (test_dir / "doc1.txt").touch()
        (test_dir / "doc2.txt").touch()
        (test_dir / "image.png").touch()
        (test_dir / "data.json").touch()

        # Create subdirectory with more files
        sub_dir = test_dir / "subdir"
        sub_dir.mkdir()
        (sub_dir / "nested.txt").touch()

        # Test BEHAVIOR: Finds correct files by pattern (rglob is recursive)
        txt_files = manager.find_files_python(str(test_dir), "*.txt")
        assert len(txt_files) == 3  # doc1.txt, doc2.txt, and nested.txt in subdir
        assert all("txt" in f for f in txt_files)

        # Test BEHAVIOR: Different patterns work
        json_files = manager.find_files_python(str(test_dir), "*.json")
        assert len(json_files) == 1
        assert "data.json" in json_files[0]

        # Test BEHAVIOR: Returns empty list for no matches
        pdf_files = manager.find_files_python(str(test_dir), "*.pdf")
        assert pdf_files == []

        # Cleanup
        manager.shutdown()
        ProcessPoolManager._instance = None

    def test_nonexistent_directory_handling(self):
        """Test behavior with nonexistent directories.

        CORRECT: Testing actual error handling behavior.
        """
        ProcessPoolManager._instance = None
        manager = ProcessPoolManager()

        # Test BEHAVIOR: Returns empty list for nonexistent path
        results = manager.find_files_python("/this/does/not/exist", "*.txt")
        assert results == []

        # Test BEHAVIOR: Manager remains functional after error
        # (Can still perform other operations)
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "test.txt").touch()
            results = manager.find_files_python(temp_dir, "*.txt")
            assert len(results) == 1

        # Cleanup
        manager.shutdown()
        ProcessPoolManager._instance = None


class TestCacheInvalidation:
    """Test cache invalidation strategies."""

    def test_selective_cache_invalidation(self):
        """Test that cache can be selectively invalidated.

        CORRECT: Testing behavior through observable state changes.
        """
        ProcessPoolManager._instance = None

        manager = InjectableProcessPoolManager()
        session = BashSessionDouble()
        manager.set_test_session(session)

        # Populate cache with various commands
        session.set_response("ls /tmp", "tmp files")
        session.set_response("ls /home", "home files")
        session.set_response("pwd", "/current/dir")

        # Execute commands to populate cache
        manager.execute_workspace_command("ls /tmp", cache_ttl=60)
        manager.execute_workspace_command("ls /home", cache_ttl=60)
        manager.execute_workspace_command("pwd", cache_ttl=60)

        # Reset session to track new executions
        initial_count = len(session.executed_commands)

        # Invalidate ls commands
        manager.invalidate_cache(pattern="ls ")

        # Test BEHAVIOR: ls commands need re-execution
        manager.execute_workspace_command("ls /tmp", cache_ttl=60)
        manager.execute_workspace_command("ls /home", cache_ttl=60)

        # These should have been re-executed
        assert len(session.executed_commands) > initial_count

        # Test BEHAVIOR: pwd still cached
        initial_count = len(session.executed_commands)
        manager.execute_workspace_command("pwd", cache_ttl=60)
        assert len(session.executed_commands) == initial_count  # Not re-executed

        # Cleanup InjectableProcessPoolManager (it bypasses singleton)
        manager.shutdown()


# =============================================================================
# KEY IMPROVEMENTS DEMONSTRATED
# =============================================================================

"""
This refactored version demonstrates:

1. NO Mock() objects - uses BashSessionDouble with realistic behavior
2. Dependency injection through InjectableProcessPoolManager
3. Tests actual behavior:
   - Cache hit/miss rates
   - TTL expiration
   - Thread safety
   - Error recovery
4. Real filesystem operations with tmp_path
5. Verifies outcomes, not method calls
6. Tests state changes, not implementation

The tests are now:
- More reliable (test actual behavior)
- Less fragile (don't break on refactoring)
- More valuable (catch real bugs)
- Easier to understand (clear intent)
"""
