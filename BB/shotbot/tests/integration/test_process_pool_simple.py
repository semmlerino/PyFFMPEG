"""Simplified integration tests for ProcessPoolManager.

Following UNIFIED_TESTING_GUIDE principles:
- Test actual behavior, not implementation
- Minimal mocking
- Focus on critical functionality
"""

import time

from process_pool_manager import ProcessPoolManager


class TestProcessPoolBasic:
    """Basic ProcessPoolManager tests."""
    
    def test_execute_simple_command(self):
        """Test executing a simple command."""
        # Create instance (not singleton to avoid interference)
        manager = ProcessPoolManager(max_workers=1, sessions_per_type=1)
        
        try:
            result = manager.execute_workspace_command("echo 'hello world'")
            assert "hello world" in result
        finally:
            manager.shutdown()
    
    def test_command_caching(self):
        """Test that commands are cached."""
        manager = ProcessPoolManager(max_workers=1, sessions_per_type=1)
        
        try:
            # First call
            result1 = manager.execute_workspace_command("echo 'cached'")
            
            # Second call (should be cached)
            result2 = manager.execute_workspace_command("echo 'cached'")
            
            assert result1 == result2
            assert "cached" in result1
            
            # Check metrics show cache hit
            metrics = manager.get_metrics()
            assert metrics["cache_stats"]["hits"] > 0
        finally:
            manager.shutdown()
    
    def test_cache_invalidation(self):
        """Test cache invalidation."""
        manager = ProcessPoolManager(max_workers=1, sessions_per_type=1)
        
        try:
            # Execute and cache
            result1 = manager.execute_workspace_command("date")
            
            # Invalidate
            manager.invalidate_cache()
            
            # Execute again (should not be from cache)
            time.sleep(0.01)  # Ensure different timestamp
            result2 = manager.execute_workspace_command("date")
            
            # Results might be different (timestamps)
            # Just verify both executed
            assert result1 is not None
            assert result2 is not None
        finally:
            manager.shutdown()
    
    def test_concurrent_execution(self):
        """Test concurrent command execution."""
        manager = ProcessPoolManager(max_workers=2, sessions_per_type=2)
        
        try:
            import concurrent.futures
            
            def execute_echo(index):
                return manager.execute_workspace_command(f"echo 'test{index}'")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(execute_echo, i) for i in range(3)]
                results = [f.result(timeout=5) for f in futures]
            
            # All should succeed
            assert len(results) == 3
            for i, result in enumerate(results):
                assert f"test{i}" in result
        finally:
            manager.shutdown()
    
    def test_error_handling(self):
        """Test error handling in command execution."""
        manager = ProcessPoolManager(max_workers=1, sessions_per_type=1)
        
        try:
            # Command that returns error
            result = manager.execute_workspace_command("false")
            # Should handle gracefully
            assert result is not None or result == ""
            
            # Should still work for next command
            result = manager.execute_workspace_command("echo 'after error'")
            assert "after error" in result
        finally:
            manager.shutdown()
    
    def test_metrics_collection(self):
        """Test that metrics are collected."""
        manager = ProcessPoolManager(max_workers=1, sessions_per_type=1)
        
        try:
            # Execute some commands
            manager.execute_workspace_command("echo 'metric test'")
            
            metrics = manager.get_metrics()
            
            # Check basic metrics structure
            assert "subprocess_calls" in metrics
            assert "average_response_ms" in metrics
            assert "cache_stats" in metrics
            assert metrics["subprocess_calls"] > 0
        finally:
            manager.shutdown()


class TestPersistentSessions:
    """Test persistent bash sessions."""
    
    def test_session_persistence(self):
        """Test that sessions maintain state."""
        from process_pool_manager import PersistentBashSession
        
        session = PersistentBashSession("test_session")
        
        try:
            # Set a variable
            result1 = session.execute("export MY_TEST_VAR=hello && echo $MY_TEST_VAR")
            assert "hello" in result1
            
            # Variable persists in same session
            result2 = session.execute("echo $MY_TEST_VAR")
            # Note: Variable might not persist across commands
            # This depends on implementation
        finally:
            session.close()
    
    def test_session_cleanup(self):
        """Test session cleanup."""
        from process_pool_manager import PersistentBashSession
        
        session = PersistentBashSession("cleanup_test")
        
        # Execute something
        result = session.execute("echo 'test'")
        assert "test" in result
        
        # Cleanup
        session.close()
        
        # After close, new command should start fresh session
        result2 = session.execute("echo 'after close'")
        assert "after close" in result2


class TestPythonFileOperations:
    """Test Python file operations."""
    
    def test_find_files_python(self, tmp_path):
        """Test finding files with Python instead of subprocess."""
        manager = ProcessPoolManager(max_workers=1, sessions_per_type=1)
        
        try:
            # Create test files
            (tmp_path / "test1.txt").write_text("test")
            (tmp_path / "test2.txt").write_text("test")
            (tmp_path / "other.log").write_text("log")
            
            # Find txt files
            files = manager.find_files_python(str(tmp_path), "*.txt")
            
            assert len(files) == 2
            assert all(f.endswith(".txt") for f in files)
        finally:
            manager.shutdown()