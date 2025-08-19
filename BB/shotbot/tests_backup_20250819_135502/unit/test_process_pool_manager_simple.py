"""Simplified unit tests for ProcessPoolManager that avoid hanging issues.

Tests core functionality without creating real interactive bash sessions.
"""

import threading
import time
from unittest.mock import Mock, patch

from process_pool_manager import (
    CommandCache,
    ProcessMetrics,
    ProcessPoolManager,
)


class TestCommandCacheSimple:
    """Test CommandCache without any subprocess operations."""

    def test_cache_basic_operations(self):
        """Test basic cache operations."""
        cache = CommandCache(default_ttl=2)

        # Test set and get
        cache.set("echo test", "test output", ttl=5)
        assert cache.get("echo test") == "test output"

        # Test cache miss
        assert cache.get("unknown command") is None

        # Test stats
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_cache_expiration(self):
        """Test cache TTL expiration."""
        cache = CommandCache(default_ttl=1)

        cache.set("echo test", "output", ttl=1)
        assert cache.get("echo test") == "output"

        # Wait for expiration
        time.sleep(1.1)
        assert cache.get("echo test") is None

    def test_cache_invalidation(self):
        """Test cache invalidation."""
        cache = CommandCache()

        cache.set("cmd1", "output1")
        cache.set("cmd2", "output2")
        cache.set("test_cmd", "test_output")

        # Invalidate by substring pattern (not glob)
        cache.invalidate(pattern="test_")
        assert cache.get("cmd1") == "output1"
        assert cache.get("cmd2") == "output2"
        assert cache.get("test_cmd") is None

        # Invalidate all
        cache.invalidate()
        assert cache.get("cmd1") is None
        assert cache.get("cmd2") is None


class TestProcessMetricsSimple:
    """Test ProcessMetrics tracking."""

    def test_metrics_initialization(self):
        """Test metrics initialization."""
        metrics = ProcessMetrics()

        assert metrics.subprocess_calls == 0
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0
        assert metrics.python_operations == 0

    def test_metrics_update(self):
        """Test metrics updates."""
        metrics = ProcessMetrics()

        metrics.subprocess_calls += 1
        metrics.cache_hits += 2
        metrics.update_response_time(100.5)

        report = metrics.get_report()
        assert report["subprocess_calls"] == 1
        # cache_hits is not in the report - it's tracked separately
        assert metrics.cache_hits == 2
        assert report["average_response_ms"] == 100.5


class TestProcessPoolManagerSimple:
    """Test ProcessPoolManager without creating real bash sessions."""

    def test_singleton_pattern(self):
        """Test singleton pattern implementation."""
        # Reset singleton for test
        ProcessPoolManager._instance = None

        manager1 = ProcessPoolManager(max_workers=2)
        manager2 = ProcessPoolManager(max_workers=4)

        assert manager1 is manager2

        # Cleanup
        manager1.shutdown()
        ProcessPoolManager._instance = None

    def test_find_files_python(self, tmp_path):
        """Test Python-based file finding (no subprocess needed)."""
        # Reset singleton
        ProcessPoolManager._instance = None

        manager = ProcessPoolManager()

        # Create test files
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file1.txt").touch()
        (test_dir / "file2.txt").touch()
        (test_dir / "other.log").touch()

        # Find txt files
        txt_files = manager.find_files_python(str(test_dir), "*.txt")
        assert len(txt_files) == 2
        assert any("file1.txt" in f for f in txt_files)
        assert any("file2.txt" in f for f in txt_files)

        # Find log files
        log_files = manager.find_files_python(str(test_dir), "*.log")
        assert len(log_files) == 1
        assert any("other.log" in f for f in log_files)

        # Cleanup
        manager.shutdown()
        ProcessPoolManager._instance = None

    @patch("process_pool_manager.PersistentBashSession")
    def test_execute_workspace_command_with_cache(self, mock_session_class):
        """Test command execution with caching (mocked session)."""
        # Reset singleton
        ProcessPoolManager._instance = None

        # Setup mock
        mock_session = Mock()
        mock_session.execute.return_value = "test output"
        mock_session_class.return_value = mock_session

        manager = ProcessPoolManager()

        # First call - should execute
        result1 = manager.execute_workspace_command("echo test", cache_ttl=10)
        assert result1 == "test output"
        assert mock_session.execute.call_count == 1

        # Second call - should use cache
        result2 = manager.execute_workspace_command("echo test", cache_ttl=10)
        assert result2 == "test output"
        assert mock_session.execute.call_count == 1  # Still 1, used cache

        # Check metrics
        metrics = manager.get_metrics()
        assert metrics["cache_stats"]["hits"] == 1
        assert metrics["cache_stats"]["misses"] == 1

        # Cleanup
        manager.shutdown()
        ProcessPoolManager._instance = None

    def test_thread_safety(self):
        """Test thread-safe singleton access."""
        # Reset singleton
        ProcessPoolManager._instance = None

        managers = []

        def create_manager():
            manager = ProcessPoolManager()
            managers.append(manager)

        threads = [threading.Thread(target=create_manager) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should be the same instance
        assert all(m is managers[0] for m in managers)

        # Cleanup
        managers[0].shutdown()
        ProcessPoolManager._instance = None

    @patch("process_pool_manager.PersistentBashSession")
    def test_batch_execute(self, mock_session_class):
        """Test batch command execution (mocked)."""
        # Reset singleton
        ProcessPoolManager._instance = None

        # Setup mock
        mock_session = Mock()
        mock_session.execute.side_effect = ["output1", "output2", "output3"]
        mock_session_class.return_value = mock_session

        manager = ProcessPoolManager()

        commands = ["echo 1", "echo 2", "echo 3"]
        results = manager.batch_execute(commands)

        assert len(results) == 3
        # batch_execute returns a dict mapping command -> output
        assert results["echo 1"] == "output1"
        assert results["echo 2"] == "output2"
        assert results["echo 3"] == "output3"

        # Cleanup
        manager.shutdown()
        ProcessPoolManager._instance = None


class TestEdgeCasesSimple:
    """Test edge cases without real subprocess execution."""

    @patch("process_pool_manager.PersistentBashSession")
    def test_empty_command(self, mock_session_class):
        """Test handling of empty commands."""
        ProcessPoolManager._instance = None

        mock_session = Mock()
        mock_session.execute.return_value = ""
        mock_session_class.return_value = mock_session

        manager = ProcessPoolManager()

        result = manager.execute_workspace_command("", cache_ttl=1)
        assert result == ""

        # Cleanup
        manager.shutdown()
        ProcessPoolManager._instance = None

    def test_nonexistent_directory_search(self):
        """Test file search in nonexistent directory."""
        ProcessPoolManager._instance = None

        manager = ProcessPoolManager()

        results = manager.find_files_python("/nonexistent/path", "*.txt")
        assert results == []

        # Cleanup
        manager.shutdown()
        ProcessPoolManager._instance = None
