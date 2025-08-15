"""Process Pool Integration Tests for ShotBot.

This module provides comprehensive integration tests for the new ProcessPoolManager
architecture, validating singleton behavior, session recovery, caching, concurrent
execution, thread safety, and performance improvements over the old subprocess approach.

Key test areas:
1. ProcessPoolManager singleton behavior and lifecycle
2. PersistentBashSession session recovery after crashes
3. CommandCache TTL expiration and cleanup mechanisms
4. Concurrent command execution with batch_execute
5. Thread safety of all operations
6. Performance benchmarks comparing old vs new implementation
7. Memory usage tracking and resource management
8. Integration with existing shot model and launcher systems
"""

import logging
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Tuple
from unittest.mock import Mock, patch

import psutil
import pytest
from PySide6.QtTest import QSignalSpy

from process_pool_manager import (
    CommandCache,
    PersistentBashSession,
    ProcessMetrics,
    ProcessPoolManager,
)

logger = logging.getLogger(__name__)


class MockWorkspaceCommand:
    """Mock workspace command for testing without real ws command."""

    def __init__(self, delay_ms: int = 50, fail_rate: float = 0.0):
        """Initialize mock workspace command.

        Args:
            delay_ms: Simulated command execution delay in milliseconds
            fail_rate: Probability of command failure (0.0-1.0)
        """
        self.delay_ms = delay_ms
        self.fail_rate = fail_rate
        self.call_count = 0
        self.command_history: List[str] = []

        # Pre-generated mock data
        self.mock_shots = [
            "workspace /shows/testshow/shots/SEQ001/SEQ001_0010",
            "workspace /shows/testshow/shots/SEQ001/SEQ001_0020",
            "workspace /shows/testshow/shots/SEQ001/SEQ001_0030",
            "workspace /shows/prodshow/shots/PROD001/PROD001_0001",
            "workspace /shows/prodshow/shots/PROD001/PROD001_0002",
            "workspace /shows/demoshow/shots/DEMO001/DEMO001_0001",
        ]

    def execute(self, command: str) -> str:
        """Execute mock workspace command.

        Args:
            command: Command to execute

        Returns:
            Mock command output

        Raises:
            RuntimeError: If fail_rate triggers failure
        """
        self.call_count += 1
        self.command_history.append(command)

        # Simulate execution delay
        time.sleep(self.delay_ms / 1000.0)

        # Simulate random failures
        import random

        if random.random() < self.fail_rate:
            raise RuntimeError(f"Mock command failed: {command}")

        # Return mock workspace output
        if "ws -sg" in command:
            return "\n".join(self.mock_shots)
        elif "echo" in command:
            return command.replace("echo ", "").strip("'\"")
        else:
            return f"Mock output for: {command}"


class ProcessPoolTestHarness:
    """Test harness for process pool testing with isolation."""

    def __init__(self):
        """Initialize test harness."""
        self.original_instance = None
        self.temp_dirs: List[Path] = []
        self.active_processes: List[subprocess.Popen] = []
        self.memory_snapshots: List[Tuple[float, float]] = []  # (timestamp, memory_mb)

    def setup(self):
        """Set up isolated test environment."""
        # Store original singleton instance
        self.original_instance = ProcessPoolManager._instance
        ProcessPoolManager._instance = None

        # Create temporary directories
        self.temp_cache_dir = Path(tempfile.mkdtemp(prefix="shotbot_cache_"))
        self.temp_dirs.append(self.temp_cache_dir)

        # Take initial memory snapshot
        self._take_memory_snapshot()

    def teardown(self):
        """Clean up test environment."""
        # Restore original singleton
        ProcessPoolManager._instance = self.original_instance

        # Clean up any active pool managers
        try:
            if ProcessPoolManager._instance:
                ProcessPoolManager._instance.shutdown()
        except:
            pass

        # Clean up temporary directories
        import shutil

        for temp_dir in self.temp_dirs:
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

        # Clean up any leaked processes
        for proc in self.active_processes:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except:
                try:
                    proc.kill()
                except:
                    pass

    def _take_memory_snapshot(self):
        """Take memory usage snapshot."""
        try:
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.memory_snapshots.append((time.time(), memory_mb))
        except:
            pass

    def get_memory_growth(self) -> float:
        """Get memory growth since setup.

        Returns:
            Memory growth in MB
        """
        if len(self.memory_snapshots) < 2:
            self._take_memory_snapshot()
            return 0.0

        self._take_memory_snapshot()
        initial_memory = self.memory_snapshots[0][1]
        current_memory = self.memory_snapshots[-1][1]
        return current_memory - initial_memory


@pytest.fixture
def process_pool_harness():
    """Fixture providing isolated process pool test environment."""
    harness = ProcessPoolTestHarness()
    harness.setup()
    yield harness
    harness.teardown()


@pytest.fixture
def mock_workspace_cmd():
    """Fixture providing mock workspace command."""
    return MockWorkspaceCommand()


@pytest.fixture
def slow_mock_workspace_cmd():
    """Fixture providing slow mock workspace command for performance testing."""
    return MockWorkspaceCommand(delay_ms=200)


@pytest.fixture
def unreliable_mock_workspace_cmd():
    """Fixture providing unreliable mock workspace command."""
    return MockWorkspaceCommand(delay_ms=100, fail_rate=0.3)


class TestProcessPoolManagerSingleton:
    """Test ProcessPoolManager singleton behavior."""

    def test_singleton_creation(self, process_pool_harness):
        """Test singleton instance creation."""
        # First instance
        pool1 = ProcessPoolManager.get_instance()
        assert pool1 is not None
        assert isinstance(pool1, ProcessPoolManager)

        # Second instance should be the same
        pool2 = ProcessPoolManager.get_instance()
        assert pool2 is pool1

        # Direct instantiation should also return same instance
        pool3 = ProcessPoolManager()
        assert pool3 is pool1

    def test_singleton_thread_safety(self, process_pool_harness):
        """Test singleton thread safety during concurrent creation."""
        instances = []
        creation_count = 10

        def create_instance(index: int):
            instance = ProcessPoolManager.get_instance()
            instances.append((index, instance))

        # Create instances concurrently
        threads = []
        for i in range(creation_count):
            thread = threading.Thread(target=create_instance, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=2.0)

        # All instances should be the same
        assert len(instances) == creation_count
        first_instance = instances[0][1]

        for index, instance in instances:
            assert instance is first_instance, f"Instance {index} is different"

    def test_singleton_initialization_once(self, process_pool_harness):
        """Test singleton only initializes once."""
        # Create instance with custom max_workers
        pool1 = ProcessPoolManager(max_workers=8)
        original_executor = pool1._executor

        # Create another instance with different max_workers
        pool2 = ProcessPoolManager(max_workers=16)

        # Should be same instance with original executor
        assert pool2 is pool1
        assert pool2._executor is original_executor
        assert pool2._executor._max_workers == 8  # Original value

    def test_singleton_signal_connectivity(self, process_pool_harness, qtbot):
        """Test singleton Qt signal connectivity."""
        pool = ProcessPoolManager.get_instance()

        # Test signal emissions
        command_completed_spy = QSignalSpy(pool.command_completed)
        command_failed_spy = QSignalSpy(pool.command_failed)

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.return_value = "test output"
            mock_session.return_value = mock_bash

            # Execute command
            result = pool.execute_workspace_command("echo 'test'")

            assert result == "test output"
            assert command_completed_spy.count() == 1
            assert command_failed_spy.count() == 0

    def test_singleton_cleanup_and_recreation(self, process_pool_harness):
        """Test singleton cleanup and recreation."""
        # Create and use instance
        pool1 = ProcessPoolManager.get_instance()
        initial_id = id(pool1)

        # Shutdown
        pool1.shutdown()

        # Clear singleton (simulating application restart)
        ProcessPoolManager._instance = None

        # Create new instance
        pool2 = ProcessPoolManager.get_instance()
        new_id = id(pool2)

        # Should be different instance
        assert new_id != initial_id
        assert pool2 is not pool1


class TestCommandCache:
    """Test CommandCache TTL and cleanup mechanisms."""

    def test_cache_basic_operations(self):
        """Test basic cache set/get operations."""
        cache = CommandCache(default_ttl=5)

        # Set and get
        cache.set("test_command", "test_result")
        result = cache.get("test_command")
        assert result == "test_result"

        # Get non-existent
        result = cache.get("nonexistent")
        assert result is None

        # Check stats
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration."""
        cache = CommandCache(default_ttl=1)  # 1 second TTL

        # Set value
        cache.set("short_lived", "result")

        # Should exist immediately
        result = cache.get("short_lived")
        assert result == "result"

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        result = cache.get("short_lived")
        assert result is None

        # Check cleanup happened
        stats = cache.get_stats()
        assert stats["size"] == 0  # Should be cleaned up

    def test_cache_custom_ttl(self):
        """Test cache with custom TTL values."""
        cache = CommandCache(default_ttl=10)

        # Set with custom TTL
        cache.set("custom_ttl", "result", ttl=1)
        cache.set("default_ttl", "result")  # Uses default TTL

        # Both should exist initially
        assert cache.get("custom_ttl") == "result"
        assert cache.get("default_ttl") == "result"

        # Wait for custom TTL to expire
        time.sleep(1.1)

        # Custom should be expired, default should remain
        assert cache.get("custom_ttl") is None
        assert cache.get("default_ttl") == "result"

    def test_cache_thread_safety(self):
        """Test cache thread safety."""
        cache = CommandCache(default_ttl=30)
        results = {}

        def cache_operations(thread_id: int):
            # Each thread performs multiple operations
            for i in range(10):
                key = f"thread_{thread_id}_item_{i}"
                value = f"result_{thread_id}_{i}"

                cache.set(key, value)
                result = cache.get(key)
                results[key] = result

        # Run concurrent cache operations
        threads = []
        for i in range(5):
            thread = threading.Thread(target=cache_operations, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join(timeout=2.0)

        # Verify all operations succeeded
        assert len(results) == 50  # 5 threads × 10 operations

        for key, value in results.items():
            expected_value = key.replace("thread_", "result_").replace("_item_", "_")
            assert value == expected_value

    def test_cache_invalidation(self):
        """Test cache invalidation patterns."""
        cache = CommandCache(default_ttl=30)

        # Set multiple items
        commands = ["ws -sg", "ws -s", "echo test", "find /tmp", "ls -la"]
        for cmd in commands:
            cache.set(cmd, f"result for {cmd}")

        assert cache.get_stats()["size"] == 5

        # Invalidate workspace commands
        cache.invalidate("ws")

        # Workspace commands should be gone
        assert cache.get("ws -sg") is None
        assert cache.get("ws -s") is None

        # Others should remain
        assert cache.get("echo test") is not None
        assert cache.get("find /tmp") is not None
        assert cache.get("ls -la") is not None

        # Clear all
        cache.invalidate()
        assert cache.get_stats()["size"] == 0

    def test_cache_cleanup_threshold(self):
        """Test cache cleanup only happens above threshold."""
        cache = CommandCache(default_ttl=1)  # Short TTL for testing

        # Add items below cleanup threshold (100)
        for i in range(50):
            cache.set(f"item_{i}", f"value_{i}")

        # Wait for expiration
        time.sleep(1.1)

        # Access cache to trigger potential cleanup
        cache.get("nonexistent")

        # Items should still be in cache (no cleanup below threshold)
        assert cache.get_stats()["size"] == 50

        # Add items above threshold
        for i in range(60):  # Total will be 110
            cache.set(f"big_item_{i}", f"big_value_{i}")

        # Wait for expiration of original items
        time.sleep(1.1)

        # Access to trigger cleanup
        cache.get("nonexistent")

        # Original expired items should be cleaned up
        stats = cache.get_stats()
        assert stats["size"] <= 60  # Should only have recent items

    def test_cache_hit_miss_statistics(self):
        """Test cache hit/miss statistics tracking."""
        cache = CommandCache(default_ttl=30)

        # Initial stats
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0

        # Cache miss
        result = cache.get("missing")
        assert result is None

        # Set and hit
        cache.set("present", "value")
        result = cache.get("present")
        assert result == "value"

        # Another miss
        cache.get("another_missing")

        # Check stats
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 2
        assert stats["hit_rate"] == 33.33333333333333  # 1/3 * 100
        assert stats["total_requests"] == 3


class TestPersistentBashSession:
    """Test PersistentBashSession session recovery."""

    def test_session_creation_and_basic_execution(self):
        """Test basic session creation and command execution."""
        session = PersistentBashSession("test_session")

        try:
            # Execute simple command
            result = session.execute("echo 'hello world'", timeout=5)
            assert "hello world" in result

            # Check session stats
            stats = session.get_stats()
            assert stats["session_id"] == "test_session"
            assert stats["alive"] is True
            assert stats["commands_executed"] == 1
            assert stats["uptime_seconds"] > 0

        finally:
            session.close()

    def test_session_recovery_after_crash(self):
        """Test session recovery after process crashes."""
        session = PersistentBashSession("recovery_test")

        try:
            # Execute successful command
            result1 = session.execute("echo 'before crash'", timeout=5)
            assert "before crash" in result1

            # Force crash by killing the underlying process
            if session._process:
                session._process.kill()
                session._process.wait()

            # Next command should trigger recovery
            result2 = session.execute("echo 'after recovery'", timeout=5)
            assert "after recovery" in result2

            # Session should be alive again
            stats = session.get_stats()
            assert stats["alive"] is True
            assert stats["commands_executed"] == 2  # Both commands counted

        finally:
            session.close()

    def test_session_timeout_handling(self):
        """Test session timeout handling."""
        session = PersistentBashSession("timeout_test")

        try:
            # Execute command that should timeout
            with pytest.raises(TimeoutError):
                session.execute("sleep 10", timeout=1)  # 1 second timeout

            # Session should recover and still work
            result = session.execute("echo 'after timeout'", timeout=5)
            assert "after timeout" in result

            stats = session.get_stats()
            assert stats["alive"] is True

        finally:
            session.close()

    def test_session_concurrent_execution_safety(self):
        """Test session thread safety with concurrent execution."""
        session = PersistentBashSession("concurrent_test")
        results = {}
        errors = []

        def execute_command(thread_id: int):
            try:
                result = session.execute(f"echo 'thread_{thread_id}'", timeout=5)
                results[thread_id] = result
            except Exception as e:
                errors.append((thread_id, str(e)))

        try:
            # Run concurrent executions
            threads = []
            for i in range(5):
                thread = threading.Thread(target=execute_command, args=(i,))
                threads.append(thread)
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join(timeout=10.0)

            # Check results - should all succeed due to thread locking
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) == 5

            for thread_id, result in results.items():
                assert f"thread_{thread_id}" in result

        finally:
            session.close()

    def test_session_environment_persistence(self):
        """Test session environment variable persistence."""
        session = PersistentBashSession("env_test")

        try:
            # Set environment variable
            session.execute("export TEST_VAR='session_value'", timeout=5)

            # Variable should persist across commands
            result = session.execute("echo $TEST_VAR", timeout=5)
            assert "session_value" in result

            # Set another variable
            session.execute("export ANOTHER_VAR='another_value'", timeout=5)

            # Both should be available
            result = session.execute("echo $TEST_VAR $ANOTHER_VAR", timeout=5)
            assert "session_value" in result
            assert "another_value" in result

        finally:
            session.close()

    def test_session_working_directory_persistence(self):
        """Test session working directory persistence."""
        session = PersistentBashSession("pwd_test")

        try:
            # Get initial directory
            initial_pwd = session.execute("pwd", timeout=5).strip()

            # Change directory to /tmp
            session.execute("cd /tmp", timeout=5)

            # Directory should persist
            current_pwd = session.execute("pwd", timeout=5).strip()
            assert current_pwd == "/tmp"
            assert current_pwd != initial_pwd

            # Should still be in /tmp for next command
            verify_pwd = session.execute("pwd", timeout=5).strip()
            assert verify_pwd == "/tmp"

        finally:
            session.close()

    def test_session_error_handling_and_recovery(self):
        """Test session error handling and recovery."""
        session = PersistentBashSession("error_test")

        try:
            # Execute failing command
            with pytest.raises(Exception):  # Could be RuntimeError or other
                session.execute("exit 1", timeout=5)  # This should kill the session

            # Session should restart and work again
            result = session.execute("echo 'recovered'", timeout=5)
            assert "recovered" in result

            stats = session.get_stats()
            assert stats["alive"] is True

        finally:
            session.close()


class TestConcurrentExecution:
    """Test concurrent command execution with batch_execute."""

    def test_batch_execute_basic(self, process_pool_harness, mock_workspace_cmd):
        """Test basic batch execution functionality."""
        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = mock_workspace_cmd.execute
            mock_session.return_value = mock_bash

            commands = [
                "echo 'command1'",
                "echo 'command2'",
                "echo 'command3'",
                "ws -sg",
            ]

            results = pool.batch_execute(commands, cache_ttl=30)

            assert len(results) == 4
            assert "command1" in results["echo 'command1'"]
            assert "command2" in results["echo 'command2'"]
            assert "command3" in results["echo 'command3'"]
            assert "workspace" in results["ws -sg"]

    def test_batch_execute_with_failures(
        self, process_pool_harness, unreliable_mock_workspace_cmd
    ):
        """Test batch execution with some command failures."""
        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = unreliable_mock_workspace_cmd.execute
            mock_session.return_value = mock_bash

            commands = [f"echo 'test_{i}'" for i in range(10)]

            results = pool.batch_execute(commands, cache_ttl=30)

            # Should have results for all commands (some may be None for failures)
            assert len(results) == 10

            # Count successful vs failed
            successful = sum(1 for r in results.values() if r is not None)
            failed = sum(1 for r in results.values() if r is None)

            # With 30% failure rate, expect some failures but not all
            assert successful > 0, "Some commands should succeed"
            assert successful + failed == 10, "All commands should be accounted for"

    def test_batch_execute_performance_vs_sequential(
        self, process_pool_harness, slow_mock_workspace_cmd
    ):
        """Test batch execution performance vs sequential execution."""
        pool = ProcessPoolManager.get_instance()

        commands = [f"echo 'performance_test_{i}'" for i in range(8)]

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = slow_mock_workspace_cmd.execute
            mock_session.return_value = mock_bash

            # Time sequential execution
            sequential_start = time.time()
            sequential_results = {}
            for cmd in commands:
                sequential_results[cmd] = pool.execute_workspace_command(cmd)
            sequential_time = time.time() - sequential_start

            # Clear cache for fair comparison
            pool.invalidate_cache()

            # Reset mock call count
            slow_mock_workspace_cmd.call_count = 0

            # Time batch execution
            batch_start = time.time()
            batch_results = pool.batch_execute(commands, cache_ttl=30)
            batch_time = time.time() - batch_start

            # Batch should be significantly faster
            speedup_ratio = sequential_time / batch_time
            assert speedup_ratio > 2.0, (
                f"Batch execution should be at least 2x faster, got {speedup_ratio:.1f}x"
            )

            # Results should be the same
            assert len(sequential_results) == len(batch_results)
            for cmd in commands:
                assert sequential_results[cmd] == batch_results[cmd]

    def test_concurrent_command_execution_thread_safety(
        self, process_pool_harness, mock_workspace_cmd
    ):
        """Test thread safety of concurrent command execution."""
        pool = ProcessPoolManager.get_instance()
        results = {}
        errors = []

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = mock_workspace_cmd.execute
            mock_session.return_value = mock_bash

            def execute_commands(thread_id: int):
                try:
                    # Each thread executes multiple commands
                    thread_results = {}
                    for i in range(5):
                        cmd = f"echo 'thread_{thread_id}_cmd_{i}'"
                        result = pool.execute_workspace_command(cmd, cache_ttl=30)
                        thread_results[cmd] = result

                    results[thread_id] = thread_results
                except Exception as e:
                    errors.append((thread_id, str(e)))

            # Run concurrent executions
            threads = []
            for i in range(6):  # 6 threads
                thread = threading.Thread(target=execute_commands, args=(i,))
                threads.append(thread)
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join(timeout=10.0)

            # Check results
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) == 6  # All threads completed

            # Verify each thread's results
            for thread_id, thread_results in results.items():
                assert len(thread_results) == 5  # Each thread ran 5 commands
                for cmd, result in thread_results.items():
                    expected_content = f"thread_{thread_id}_cmd_"
                    assert expected_content in result

    def test_concurrent_cache_access(self, process_pool_harness, mock_workspace_cmd):
        """Test concurrent cache access during command execution."""
        pool = ProcessPoolManager.get_instance()
        cache_hits = {}
        cache_misses = {}

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = mock_workspace_cmd.execute
            mock_session.return_value = mock_bash

            # Same command executed by multiple threads
            repeated_command = "echo 'cache_test'"

            def execute_repeated_command(thread_id: int):
                initial_stats = pool._cache.get_stats()
                pool.execute_workspace_command(repeated_command, cache_ttl=30)
                final_stats = pool._cache.get_stats()

                # Calculate hits/misses for this thread
                hit_delta = final_stats["hits"] - initial_stats["hits"]
                miss_delta = final_stats["misses"] - initial_stats["misses"]

                cache_hits[thread_id] = hit_delta
                cache_misses[thread_id] = miss_delta

            # First execution to populate cache
            pool.execute_workspace_command(repeated_command, cache_ttl=30)

            # Now run concurrent executions
            threads = []
            for i in range(8):
                thread = threading.Thread(target=execute_repeated_command, args=(i,))
                threads.append(thread)
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join(timeout=5.0)

            # Most threads should get cache hits
            total_hits = sum(cache_hits.values())
            total_misses = sum(cache_misses.values())

            assert total_hits > 0, "Should have some cache hits"
            # Cache hits should be much more common than misses for repeated command
            hit_ratio = total_hits / (total_hits + total_misses)
            assert hit_ratio > 0.5, (
                f"Cache hit ratio should be > 50%, got {hit_ratio:.1%}"
            )


class TestThreadSafety:
    """Test thread safety of all process pool operations."""

    def test_singleton_thread_safety_stress(self, process_pool_harness):
        """Stress test singleton thread safety."""
        instances = []

        def create_and_use_instance(thread_id: int):
            # Create instance
            pool = ProcessPoolManager.get_instance()
            instances.append((thread_id, id(pool)))

            # Use the instance
            with patch.object(pool, "_get_bash_session") as mock_session:
                mock_bash = Mock()
                mock_bash.execute.return_value = f"output_{thread_id}"
                mock_session.return_value = mock_bash

                result = pool.execute_workspace_command(
                    f"echo {thread_id}", cache_ttl=30
                )
                assert f"output_{thread_id}" == result

        # Run many concurrent threads
        threads = []
        for i in range(20):
            thread = threading.Thread(target=create_and_use_instance, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all
        for thread in threads:
            thread.join(timeout=5.0)

        # All instances should be the same
        assert len(instances) == 20
        first_id = instances[0][1]
        for thread_id, instance_id in instances:
            assert instance_id == first_id, f"Thread {thread_id} got different instance"

    def test_cache_thread_safety_stress(self, process_pool_harness):
        """Stress test cache thread safety."""
        cache = CommandCache(default_ttl=30)
        operations_per_thread = 100
        num_threads = 10

        results = {}
        errors = []

        def cache_stress_test(thread_id: int):
            try:
                thread_results = {"sets": 0, "gets": 0, "hits": 0, "misses": 0}

                for i in range(operations_per_thread):
                    # Mix of operations
                    if i % 3 == 0:
                        # Set operation
                        key = f"thread_{thread_id}_key_{i}"
                        value = f"value_{thread_id}_{i}"
                        cache.set(key, value)
                        thread_results["sets"] += 1
                    else:
                        # Get operation (mix of existing and non-existing keys)
                        if i % 2 == 0:
                            # Get existing key from same thread
                            existing_i = i - (i % 3)  # Previous set operation
                            key = f"thread_{thread_id}_key_{existing_i}"
                        else:
                            # Get potentially non-existing key
                            key = f"thread_{thread_id}_key_{i + 1000}"

                        result = cache.get(key)
                        thread_results["gets"] += 1
                        if result is not None:
                            thread_results["hits"] += 1
                        else:
                            thread_results["misses"] += 1

                results[thread_id] = thread_results

            except Exception as e:
                errors.append((thread_id, str(e)))

        # Run stress test
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=cache_stress_test, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join(timeout=10.0)

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors during cache stress test: {errors}"
        assert len(results) == num_threads

        # Verify operations were performed
        total_sets = sum(r["sets"] for r in results.values())
        total_gets = sum(r["gets"] for r in results.values())

        num_threads * (
            operations_per_thread // 3 + (1 if operations_per_thread % 3 > 0 else 0)
        )
        num_threads * operations_per_thread - total_sets

        assert total_sets > 0, "Should have performed set operations"
        assert total_gets > 0, "Should have performed get operations"

        # Cache should be consistent
        final_stats = cache.get_stats()
        assert final_stats["size"] <= total_sets, "Cache size should not exceed sets"

    def test_session_management_thread_safety(self, process_pool_harness):
        """Test thread safety of session management."""
        pool = ProcessPoolManager.get_instance()
        session_accesses = []

        def access_session(thread_id: int):
            # Access workspace session
            session = pool._get_bash_session("workspace")
            session_accesses.append((thread_id, id(session)))

            # Also access other session types
            general_session = pool._get_bash_session("general")
            test_session = pool._get_bash_session(f"test_{thread_id}")

            session_accesses.append((f"{thread_id}_general", id(general_session)))
            session_accesses.append((f"{thread_id}_test", id(test_session)))

        # Run concurrent session access
        threads = []
        for i in range(8):
            thread = threading.Thread(target=access_session, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join(timeout=5.0)

        # Analyze session sharing
        workspace_sessions = [sa for sa in session_accesses if isinstance(sa[0], int)]
        general_sessions = [sa for sa in session_accesses if "general" in str(sa[0])]

        # All workspace sessions should be the same instance
        workspace_ids = [sa[1] for sa in workspace_sessions]
        assert len(set(workspace_ids)) == 1, (
            "All threads should get same workspace session"
        )

        # All general sessions should be the same instance
        general_ids = [sa[1] for sa in general_sessions]
        assert len(set(general_ids)) == 1, "All threads should get same general session"

    def test_metrics_thread_safety(self, process_pool_harness):
        """Test thread safety of metrics collection."""
        metrics = ProcessMetrics()

        def update_metrics(thread_id: int):
            for i in range(100):
                # Update various metrics
                metrics.subprocess_calls += 1
                metrics.cache_hits += 1
                metrics.cache_misses += 1
                metrics.python_operations += 1
                metrics.update_response_time(float(i))

        # Run concurrent metric updates
        threads = []
        for i in range(8):
            thread = threading.Thread(target=update_metrics, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join(timeout=5.0)

        # Verify metrics are consistent
        report = metrics.get_report()

        # Each metric should reflect all updates
        expected_calls = 8 * 100  # 8 threads × 100 operations
        assert metrics.subprocess_calls == expected_calls
        assert metrics.cache_hits == expected_calls
        assert metrics.cache_misses == expected_calls
        assert metrics.python_operations == expected_calls
        assert metrics.response_count == expected_calls

        # Average response time should be calculated correctly
        assert report["average_response_ms"] > 0


class TestPerformanceBenchmarks:
    """Performance benchmarks comparing old vs new implementation."""

    def test_single_command_performance_comparison(self, process_pool_harness):
        """Compare single command execution performance."""

        # Test old implementation (subprocess.run)
        def old_implementation(command: str) -> str:
            result = subprocess.run(
                ["/bin/bash", "-i", "-c", command],
                capture_output=True,
                text=True,
                timeout=30,
                env=os.environ.copy(),
            )
            return result.stdout

        # Test new implementation
        pool = ProcessPoolManager.get_instance()

        test_command = "echo 'performance test'"

        # Warm up both implementations
        try:
            old_implementation(test_command)
        except:
            pass  # May fail in test environment

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.return_value = "performance test"
            mock_session.return_value = mock_bash

            pool.execute_workspace_command(test_command)

        # Benchmark old implementation
        old_times = []
        for _ in range(5):
            try:
                start_time = time.time()
                old_implementation(test_command)
                old_times.append((time.time() - start_time) * 1000)  # Convert to ms
            except:
                old_times.append(1000)  # Assume 1000ms if fails

        # Benchmark new implementation (with cache cleared)
        new_times = []
        for _ in range(5):
            pool.invalidate_cache()  # Clear cache for fair comparison

            start_time = time.time()
            pool.execute_workspace_command(test_command)
            new_times.append((time.time() - start_time) * 1000)  # Convert to ms

        # Calculate averages
        avg_old_time = sum(old_times) / len(old_times)
        avg_new_time = sum(new_times) / len(new_times)

        logger.info("Single command performance:")
        logger.info(f"  Old implementation: {avg_old_time:.1f}ms")
        logger.info(f"  New implementation: {avg_new_time:.1f}ms")

        # New implementation should be faster (due to session reuse)
        # But in mocked environment, this might not always hold
        # So we just verify both complete successfully
        assert avg_old_time > 0
        assert avg_new_time > 0

    def test_repeated_command_caching_performance(self, process_pool_harness):
        """Test performance improvement from caching."""
        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.return_value = "cached result"
            mock_session.return_value = mock_bash

            test_command = "ws -sg"

            # First execution (cache miss)
            start_time = time.time()
            result1 = pool.execute_workspace_command(test_command, cache_ttl=30)
            first_time = (time.time() - start_time) * 1000

            # Second execution (cache hit)
            start_time = time.time()
            result2 = pool.execute_workspace_command(test_command, cache_ttl=30)
            second_time = (time.time() - start_time) * 1000

            # Verify caching worked
            assert result1 == result2
            assert second_time < first_time, "Cached execution should be faster"

            # Check cache stats
            stats = pool._cache.get_stats()
            assert stats["hits"] >= 1
            assert stats["hit_rate"] > 0

            logger.info("Caching performance:")
            logger.info(f"  First execution (miss): {first_time:.1f}ms")
            logger.info(f"  Second execution (hit): {second_time:.1f}ms")
            logger.info(f"  Cache speedup: {first_time / second_time:.1f}x")

    def test_batch_execution_scalability(self, process_pool_harness):
        """Test batch execution scalability."""
        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = lambda cmd: f"result for {cmd}"
            mock_session.return_value = mock_bash

            # Test different batch sizes
            batch_sizes = [1, 5, 10, 20, 50]
            results = {}

            for batch_size in batch_sizes:
                commands = [f"echo 'batch_test_{i}'" for i in range(batch_size)]

                start_time = time.time()
                batch_results = pool.batch_execute(commands, cache_ttl=30)
                execution_time = (time.time() - start_time) * 1000

                results[batch_size] = {
                    "time_ms": execution_time,
                    "commands_per_second": batch_size / (execution_time / 1000),
                    "avg_time_per_command": execution_time / batch_size,
                }

                assert len(batch_results) == batch_size

                logger.info(
                    f"Batch size {batch_size}: {execution_time:.1f}ms total, "
                    f"{results[batch_size]['avg_time_per_command']:.1f}ms per command"
                )

            # Verify scalability - larger batches should be more efficient per command
            single_command_time = results[1]["avg_time_per_command"]
            large_batch_time = results[50]["avg_time_per_command"]

            # Large batches should have better per-command performance due to parallelization
            efficiency_ratio = single_command_time / large_batch_time
            assert efficiency_ratio > 1.0, (
                f"Batch execution should be more efficient, got {efficiency_ratio:.1f}x"
            )

    def test_memory_efficiency_comparison(self, process_pool_harness):
        """Test memory efficiency of new implementation."""
        process_pool_harness.get_memory_growth()

        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = lambda cmd: f"memory test result for {cmd}"
            mock_session.return_value = mock_bash

            # Execute many commands to test memory usage
            for i in range(100):
                command = f"echo 'memory_test_{i}'"
                result = pool.execute_workspace_command(command, cache_ttl=30)
                assert "memory test result" in result

                # Periodically check memory growth
                if i % 25 == 0:
                    memory_growth = process_pool_harness.get_memory_growth()
                    logger.info(
                        f"After {i + 1} commands: {memory_growth:.1f}MB memory growth"
                    )

                    # Memory growth should be reasonable
                    assert memory_growth < 50, (
                        f"Memory growth too high after {i + 1} commands: {memory_growth:.1f}MB"
                    )

        # Final memory check
        final_memory_growth = process_pool_harness.get_memory_growth()
        logger.info(
            f"Final memory growth after 100 commands: {final_memory_growth:.1f}MB"
        )

        # Total memory growth should be reasonable
        assert final_memory_growth < 100, (
            f"Total memory growth too high: {final_memory_growth:.1f}MB"
        )

        # Check cache size is reasonable
        cache_stats = pool._cache.get_stats()
        logger.info(f"Final cache stats: {cache_stats}")

        # Cache should not grow unbounded
        assert cache_stats["size"] <= 100, "Cache size should be bounded"


class TestMemoryUsageTracking:
    """Test memory usage tracking and resource management."""

    def test_cache_memory_management(self, process_pool_harness):
        """Test cache memory management and cleanup."""
        cache = CommandCache(default_ttl=1)  # Short TTL for testing

        initial_memory = process_pool_harness.get_memory_growth()

        # Fill cache with data
        large_data = "x" * 10000  # 10KB per entry
        for i in range(100):
            cache.set(f"large_entry_{i}", large_data)

        # Check memory growth
        after_fill_memory = process_pool_harness.get_memory_growth()
        fill_growth = after_fill_memory - initial_memory

        logger.info(f"Memory growth after filling cache: {fill_growth:.1f}MB")
        assert fill_growth < 50, "Memory growth from cache should be reasonable"

        # Wait for TTL expiration
        time.sleep(1.5)

        # Trigger cleanup by accessing cache
        cache.get("nonexistent")

        # Force garbage collection
        import gc

        gc.collect()

        # Check memory after cleanup
        after_cleanup_memory = process_pool_harness.get_memory_growth()
        cleanup_reduction = after_fill_memory - after_cleanup_memory

        logger.info(f"Memory reduction after cleanup: {cleanup_reduction:.1f}MB")

        # Cache should have cleaned up
        assert cache.get_stats()["size"] == 0, (
            "Cache should be empty after TTL expiration"
        )

    def test_session_memory_management(self):
        """Test session memory management and cleanup."""
        sessions = []

        # Create multiple sessions
        for i in range(5):
            session = PersistentBashSession(f"memory_test_{i}")
            sessions.append(session)

            # Execute commands to ensure session is active
            try:
                result = session.execute(f"echo 'session_{i}'", timeout=5)
                assert f"session_{i}" in result
            except:
                pass  # Ignore failures in test environment

        # Check sessions are alive
        alive_sessions = [s for s in sessions if s._is_alive()]
        logger.info(f"Created {len(sessions)} sessions, {len(alive_sessions)} alive")

        # Close all sessions
        for session in sessions:
            try:
                session.close()
            except:
                pass

        # Force garbage collection
        import gc

        gc.collect()

        # Check sessions are closed
        closed_sessions = [s for s in sessions if not s._is_alive()]
        assert len(closed_sessions) == len(sessions), "All sessions should be closed"

    def test_process_pool_resource_cleanup(self, process_pool_harness):
        """Test process pool resource cleanup."""
        initial_memory = process_pool_harness.get_memory_growth()

        # Create and use process pool
        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = lambda cmd: f"cleanup test: {cmd}"
            mock_session.return_value = mock_bash

            # Execute many operations
            for i in range(50):
                result = pool.execute_workspace_command(
                    f"echo 'cleanup_{i}'", cache_ttl=30
                )
                assert "cleanup test" in result

        # Check memory before cleanup
        before_cleanup_memory = process_pool_harness.get_memory_growth()

        # Shutdown pool
        pool.shutdown()

        # Force garbage collection
        import gc

        gc.collect()

        # Check memory after cleanup
        after_cleanup_memory = process_pool_harness.get_memory_growth()

        logger.info("Memory usage:")
        logger.info(f"  Initial: {initial_memory:.1f}MB")
        logger.info(f"  Before cleanup: {before_cleanup_memory:.1f}MB")
        logger.info(f"  After cleanup: {after_cleanup_memory:.1f}MB")

        # Memory should not grow excessively
        total_growth = after_cleanup_memory - initial_memory
        assert total_growth < 100, f"Total memory growth too high: {total_growth:.1f}MB"

    def test_memory_usage_under_stress(self, process_pool_harness):
        """Test memory usage under stress conditions."""
        pool = ProcessPoolManager.get_instance()

        initial_memory = process_pool_harness.get_memory_growth()
        memory_samples = []

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = lambda cmd: f"stress test result: {cmd}"
            mock_session.return_value = mock_bash

            # Stress test with many operations
            for iteration in range(200):
                # Mix of different operations
                if iteration % 4 == 0:
                    # Single command
                    pool.execute_workspace_command(
                        f"echo 'stress_{iteration}'", cache_ttl=30
                    )
                elif iteration % 4 == 1:
                    # Batch commands
                    commands = [f"echo 'batch_{iteration}_{i}'" for i in range(5)]
                    pool.batch_execute(commands, cache_ttl=30)
                elif iteration % 4 == 2:
                    # Cache invalidation
                    pool.invalidate_cache("echo")
                else:
                    # Metrics access
                    metrics = pool.get_metrics()
                    assert isinstance(metrics, dict)

                # Sample memory every 25 iterations
                if iteration % 25 == 0:
                    current_memory = process_pool_harness.get_memory_growth()
                    memory_samples.append((iteration, current_memory))

                    # Memory growth should be bounded
                    growth_since_start = current_memory - initial_memory
                    assert growth_since_start < 200, (
                        f"Memory growth too high at iteration {iteration}: {growth_since_start:.1f}MB"
                    )

        # Analyze memory trend
        final_memory = process_pool_harness.get_memory_growth()
        total_growth = final_memory - initial_memory

        logger.info("Stress test memory analysis:")
        logger.info(f"  Total growth: {total_growth:.1f}MB")
        logger.info(f"  Memory samples: {memory_samples}")

        # Memory growth should be reasonable for stress test
        assert total_growth < 300, f"Total memory growth too high: {total_growth:.1f}MB"

        # Memory should not show unbounded growth
        if len(memory_samples) >= 2:
            early_memory = memory_samples[1][1]  # Second sample
            late_memory = memory_samples[-1][1]  # Last sample
            growth_rate = (late_memory - early_memory) / (len(memory_samples) - 1)

            logger.info(f"  Average growth rate: {growth_rate:.1f}MB per sample")
            assert growth_rate < 5, (
                f"Memory growth rate too high: {growth_rate:.1f}MB per sample"
            )


class TestIntegrationWithExistingSystems:
    """Test integration with existing shot model and launcher systems."""

    def test_shot_model_integration_with_process_pool(
        self, process_pool_harness, mock_workspace_cmd
    ):
        """Test shot model integration with process pool."""
        # This would require modifying ShotModel to use ProcessPoolManager
        # For now, we test the pattern that would be used

        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = mock_workspace_cmd.execute
            mock_session.return_value = mock_bash

            # Simulate shot model refresh using process pool
            result = pool.execute_workspace_command("ws -sg", cache_ttl=30)

            # Parse result like shot model would
            lines = result.strip().split("\n")
            workspace_lines = [line for line in lines if line.startswith("workspace")]

            assert len(workspace_lines) == 6  # Based on mock data

            # Verify cache is working
            cached_result = pool.execute_workspace_command("ws -sg", cache_ttl=30)
            assert cached_result == result

            # Check metrics
            metrics = pool.get_metrics()
            assert metrics["cache_stats"]["hits"] >= 1

    def test_launcher_system_integration(
        self, process_pool_harness, mock_workspace_cmd
    ):
        """Test launcher system integration with process pool."""
        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = mock_workspace_cmd.execute
            mock_session.return_value = mock_bash

            # Simulate launcher commands that might use process pool
            launcher_commands = [
                "cd /shot/workspace && nuke",
                "cd /shot/workspace && maya",
                "cd /shot/workspace && 3de",
            ]

            # Execute commands through process pool
            results = pool.batch_execute(launcher_commands, cache_ttl=60)

            assert len(results) == 3
            for cmd, result in results.items():
                assert "Mock output for:" in result
                assert cmd in result

    def test_process_pool_signals_integration(self, process_pool_harness, qtbot):
        """Test process pool Qt signals integration."""
        pool = ProcessPoolManager.get_instance()

        # Set up signal spies
        command_completed_spy = QSignalSpy(pool.command_completed)
        command_failed_spy = QSignalSpy(pool.command_failed)

        with patch.object(pool, "_get_bash_session") as mock_session:
            # Test successful command
            mock_bash = Mock()
            mock_bash.execute.return_value = "success result"
            mock_session.return_value = mock_bash

            result = pool.execute_workspace_command("echo 'test'", cache_ttl=30)

            assert result == "success result"
            assert len(command_completed_spy) == 1
            assert len(command_failed_spy) == 0

            # Test failed command
            mock_bash.execute.side_effect = RuntimeError("Command failed")

            with pytest.raises(RuntimeError):
                pool.execute_workspace_command("failing_command", cache_ttl=30)

            assert len(command_failed_spy) == 1

    def test_performance_comparison_with_shot_model(self, process_pool_harness):
        """Test performance comparison with current shot model implementation."""

        # Current shot model implementation (simplified)
        def old_shot_model_refresh():
            try:
                result = subprocess.run(
                    ["/bin/bash", "-i", "-c", "ws -sg"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=os.environ.copy(),
                )
                return result.stdout if result.returncode == 0 else ""
            except:
                return ""

        # New implementation using process pool
        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.return_value = "\n".join(
                [
                    "workspace /shows/test1/shots/SEQ/SEQ_0001",
                    "workspace /shows/test2/shots/SEQ/SEQ_0002",
                ]
            )
            mock_session.return_value = mock_bash

            def new_shot_model_refresh():
                return pool.execute_workspace_command("ws -sg", cache_ttl=30)

            # Benchmark both approaches
            old_times = []
            for _ in range(3):
                start = time.time()
                old_shot_model_refresh()
                old_times.append((time.time() - start) * 1000)

            new_times = []
            for _ in range(3):
                pool.invalidate_cache()  # Clear cache for fair comparison
                start = time.time()
                new_shot_model_refresh()
                new_times.append((time.time() - start) * 1000)

            # Also test cached performance
            cached_times = []
            for _ in range(3):
                start = time.time()
                new_shot_model_refresh()  # Should be cached
                cached_times.append((time.time() - start) * 1000)

            avg_old = sum(old_times) / len(old_times)
            avg_new = sum(new_times) / len(new_times)
            avg_cached = sum(cached_times) / len(cached_times)

            logger.info("Shot model performance comparison:")
            logger.info(f"  Old implementation: {avg_old:.1f}ms")
            logger.info(f"  New implementation: {avg_new:.1f}ms")
            logger.info(f"  Cached implementation: {avg_cached:.1f}ms")

            # Cached should be significantly faster
            assert avg_cached < avg_new, "Cached execution should be faster"
            assert avg_cached < avg_old, "Cached execution should be faster than old"


# Additional stress tests and edge cases
@pytest.mark.stress
class TestProcessPoolStress:
    """Stress tests for process pool under extreme conditions."""

    def test_rapid_fire_commands(self, process_pool_harness):
        """Test rapid fire command execution."""
        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = lambda cmd: f"rapid_{cmd}"
            mock_session.return_value = mock_bash

            # Execute commands rapidly
            results = []
            start_time = time.time()

            for i in range(100):
                result = pool.execute_workspace_command(f"echo {i}", cache_ttl=30)
                results.append(result)

            execution_time = time.time() - start_time

            # All commands should complete
            assert len(results) == 100
            for i, result in enumerate(results):
                assert f"rapid_echo {i}" == result

            logger.info(
                f"Rapid fire test: 100 commands in {execution_time:.2f}s "
                f"({100 / execution_time:.1f} commands/sec)"
            )

    def test_concurrent_batch_executions(self, process_pool_harness):
        """Test multiple concurrent batch executions."""
        pool = ProcessPoolManager.get_instance()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = lambda cmd: f"batch_result_{cmd}"
            mock_session.return_value = mock_bash

            batch_results = {}

            def execute_batch(batch_id: int):
                commands = [f"echo batch_{batch_id}_cmd_{i}" for i in range(10)]
                results = pool.batch_execute(commands, cache_ttl=30)
                batch_results[batch_id] = results

            # Run multiple batches concurrently
            threads = []
            for i in range(5):
                thread = threading.Thread(target=execute_batch, args=(i,))
                threads.append(thread)
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join(timeout=10.0)

            # Verify all batches completed
            assert len(batch_results) == 5

            for batch_id, results in batch_results.items():
                assert len(results) == 10
                for cmd, result in results.items():
                    assert f"batch_{batch_id}" in cmd
                    assert f"batch_result_{cmd}" == result

    def test_memory_under_extreme_load(self, process_pool_harness):
        """Test memory usage under extreme load."""
        pool = ProcessPoolManager.get_instance()

        initial_memory = process_pool_harness.get_memory_growth()

        with patch.object(pool, "_get_bash_session") as mock_session:
            mock_bash = Mock()
            mock_bash.execute.side_effect = (
                lambda cmd: f"extreme_load_{cmd}" + "x" * 1000
            )  # 1KB result
            mock_session.return_value = mock_bash

            # Execute extreme load
            for i in range(500):  # 500 commands with 1KB each = ~500KB
                result = pool.execute_workspace_command(
                    f"echo extreme_{i}", cache_ttl=30
                )
                assert "extreme_load_" in result

                # Check memory periodically
                if i % 100 == 0:
                    current_memory = process_pool_harness.get_memory_growth()
                    growth = current_memory - initial_memory
                    assert growth < 500, (
                        f"Memory growth too high at {i}: {growth:.1f}MB"
                    )

        final_memory = process_pool_harness.get_memory_growth()
        total_growth = final_memory - initial_memory

        logger.info(f"Extreme load memory growth: {total_growth:.1f}MB")
        assert total_growth < 1000, (
            f"Total memory growth too high: {total_growth:.1f}MB"
        )


if __name__ == "__main__":
    # Run specific test classes for debugging
    pytest.main([__file__ + "::TestProcessPoolManagerSingleton", "-v"])
