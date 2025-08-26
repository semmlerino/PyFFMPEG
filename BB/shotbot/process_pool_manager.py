"""Process Pool Manager for optimized subprocess handling.

This module provides centralized process management with pooling, caching,
and session reuse to reduce the overhead of repeated subprocess calls.
"""

import concurrent.futures
import hashlib
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Try to import fcntl for non-blocking I/O (Unix-only)
try:
    import fcntl

    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False
    logging.warning("fcntl module not available - will use blocking I/O")

from PySide6.QtCore import QObject, Signal

from config import ThreadingConfig
from persistent_bash_session import PersistentBashSession

# Import debug utilities
try:
    from debug_utils import (
        CommandTracer,
        deadlock_detector,
        setup_enhanced_debugging,
        state_tracker,
        timing_profiler,
    )

    HAS_DEBUG_UTILS = True
except ImportError:
    HAS_DEBUG_UTILS = False

logger = logging.getLogger(__name__)

# Enable verbose debug logging if environment variable is set
DEBUG_VERBOSE = os.environ.get("SHOTBOT_DEBUG_VERBOSE", "").lower() in (
    "1",
    "true",
    "yes",
)
if DEBUG_VERBOSE:
    logger.setLevel(logging.DEBUG)
    logger.info("VERBOSE DEBUG MODE ENABLED for ProcessPoolManager")

# Setup enhanced debugging if available
if HAS_DEBUG_UTILS:
    setup_enhanced_debugging()


class CommandCache:
    """TTL-based cache for command results."""

    def __init__(self, default_ttl: int = 30):
        """Initialize command cache.

        Args:
            default_ttl: Default time-to-live in seconds
        """
        super().__init__()
        self._cache: Dict[
            str,
            Tuple[Any, float, int, str],
        ] = {}  # key -> (result, timestamp, ttl, original_command)
        self._lock = threading.RLock()
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, command: str) -> Optional[Any]:
        """Get cached result if not expired.

        Args:
            command: Command string to look up

        Returns:
            Cached result or None if not found/expired
        """
        key = self._make_key(command)

        with self._lock:
            if key in self._cache:
                result, timestamp, ttl, _ = self._cache[key]
                if time.time() - timestamp < ttl:
                    self._hits += 1
                    logger.debug(f"Cache hit for command: {command[:50]}...")
                    return result
                del self._cache[key]

            self._misses += 1
            return None

    def set(self, command: str, result: Any, ttl: Optional[int] = None):
        """Cache command result with TTL.

        Args:
            command: Command string
            result: Result to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        if ttl is None:
            ttl = self._default_ttl

        key = self._make_key(command)

        with self._lock:
            self._cache[key] = (result, time.time(), ttl, command)
            self._cleanup_expired()

    def invalidate(self, pattern: Optional[str] = None):
        """Invalidate cache entries.

        Args:
            pattern: Optional pattern to match (invalidates all if None)
        """
        with self._lock:
            if pattern is None:
                self._cache.clear()
                logger.info("Cleared entire command cache")
            else:
                # Check the original command (4th element in tuple) for pattern
                keys_to_remove: List[str] = []
                for key, value in self._cache.items():
                    if len(value) >= 4 and pattern in value[3]:
                        keys_to_remove.append(key)
                for key in keys_to_remove:
                    del self._cache[key]
                logger.info(
                    f"Invalidated {len(keys_to_remove)} cache entries matching '{pattern}'",
                )

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "size": len(self._cache),
                "total_requests": total,
            }

    def _make_key(self, command: str) -> str:
        """Generate cache key from command.

        Args:
            command: Command string

        Returns:
            SHA256 hash of command
        """
        return hashlib.sha256(command.encode()).hexdigest()

    def _cleanup_expired(self):
        """Remove expired entries."""
        if len(self._cache) <= 100:  # Don't cleanup small caches
            return

        current_time = time.time()
        expired = [
            key
            for key, (_, timestamp, ttl, _) in self._cache.items()
            if current_time - timestamp >= ttl
        ]
        for key in expired:
            del self._cache[key]

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired cache entries")


class ProcessPoolManager(QObject):
    """Centralized process management with pooling and caching.

    This singleton class manages all subprocess operations for the application,
    providing session reuse, command caching, and parallel execution.
    """

    # Singleton instance
    _instance = None
    _lock = threading.Lock()

    # Qt signals
    command_completed = Signal(str, object)  # command_id, result
    command_failed = Signal(str, str)  # command_id, error

    def __new__(cls, *args, **kwargs):
        """Ensure singleton pattern."""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_workers: int = 4, sessions_per_type: int = 3):
        """Initialize process pool manager.

        Args:
            max_workers: Maximum concurrent workers
            sessions_per_type: Number of sessions to maintain per type for parallelism
        """
        # Only initialize once
        with ProcessPoolManager._lock:
            if hasattr(self, "_initialized"):
                return

            super().__init__()

            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers,
            )
            # Session pools: type -> list of sessions
            self._session_pools: Dict[str, List[PersistentBashSession]] = {}
            self._session_round_robin: Dict[str, int] = {}  # Track next session to use
            self._sessions_per_type = sessions_per_type
            self._cache = CommandCache(default_ttl=30)
            self._session_lock = threading.RLock()
            self._metrics = ProcessMetrics()
            self._initialized = True

        logger.info(f"ProcessPoolManager initialized with {max_workers} workers")

    @classmethod
    def get_instance(cls) -> "ProcessPoolManager":
        """Get singleton instance.

        Returns:
            ProcessPoolManager singleton
        """
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def execute_workspace_command(
        self,
        command: str,
        cache_ttl: int = 30,
        timeout: Optional[int] = None,
    ) -> str:
        """Execute workspace command with caching and session reuse.

        Args:
            command: Command to execute
            cache_ttl: Cache time-to-live in seconds
            timeout: Command execution timeout in seconds (default 120s)

        Returns:
            Command output
        """
        if timeout is None:
            timeout = int(ThreadingConfig.SUBPROCESS_TIMEOUT)

        if DEBUG_VERBOSE:
            logger.debug(f"execute_workspace_command called: {command[:50]}...")

        # Check cache first
        cached = self._cache.get(command)
        if cached is not None:
            self._metrics.cache_hits += 1
            if DEBUG_VERBOSE:
                logger.debug(f"Cache HIT for command: {command[:50]}...")
            return cached

        if DEBUG_VERBOSE:
            logger.debug(f"Cache MISS for command: {command[:50]}... - will execute")

        self._metrics.cache_misses += 1
        self._metrics.subprocess_calls += 1

        # Get or create bash session
        session = self._get_bash_session("workspace")

        # Execute command
        start_time = time.time()
        try:
            result = session.execute(command, timeout=timeout)

            # Cache result
            self._cache.set(command, result, ttl=cache_ttl)

            # Update metrics
            elapsed = (time.time() - start_time) * 1000
            self._metrics.update_response_time(elapsed)

            # Emit completion signal
            self.command_completed.emit(command, result)

            return result

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            self.command_failed.emit(command, str(e))
            raise

    def batch_execute(
        self,
        commands: List[str],
        cache_ttl: int = 30,
        session_type: str = "workspace",
    ) -> Dict[str, Optional[str]]:
        """Execute multiple commands in parallel using session pool.

        Leverages multiple sessions for true parallel execution.

        Args:
            commands: List of commands to execute
            cache_ttl: Cache time-to-live in seconds
            session_type: Type of session pool to use

        Returns:
            Dictionary mapping commands to results
        """
        # Check cache first and separate cached from non-cached
        results: Dict[str, Optional[str]] = {}
        commands_to_execute: List[str] = []

        for cmd in commands:
            cached = self._cache.get(cmd)
            if cached is not None:
                results[cmd] = cached
                self._metrics.cache_hits += 1
                logger.debug(f"Batch: cache hit for {cmd[:50]}...")
            else:
                commands_to_execute.append(cmd)
                self._metrics.cache_misses += 1

        if not commands_to_execute:
            return results  # All results were cached

        # Execute non-cached commands in parallel
        futures: Dict[concurrent.futures.Future[str], str] = {}
        for cmd in commands_to_execute:
            future = self._executor.submit(
                self._execute_with_session_pool,
                cmd,
                cache_ttl,
                session_type,
            )
            futures[future] = cmd

        # Collect results
        for future in concurrent.futures.as_completed(futures):
            cmd = futures[future]
            try:
                result = future.result()
                results[cmd] = result
                # Cache successful results
                self._cache.set(cmd, result, ttl=cache_ttl)
            except Exception as e:
                logger.error(f"Batch command failed: {cmd} - {e}")
                results[cmd] = None

        return results

    def _execute_with_session_pool(
        self,
        command: str,
        cache_ttl: int,
        session_type: str,
    ) -> str:
        """Execute command using session pool for true parallelism.

        This method is designed to be called in parallel threads.

        Args:
            command: Command to execute
            cache_ttl: Cache time-to-live
            session_type: Type of session pool

        Returns:
            Command output
        """
        # Get next available session from pool
        session = self._get_bash_session(session_type)

        # Execute command
        start_time = time.time()
        try:
            result = session.execute(command)

            # Update metrics
            elapsed = (time.time() - start_time) * 1000
            self._metrics.update_response_time(elapsed)
            self._metrics.subprocess_calls += 1

            return result

        except Exception as e:
            logger.error(f"Session pool execution failed: {e}")
            raise

    def find_files_python(self, directory: str, pattern: str) -> List[str]:
        """Find files using Python instead of subprocess.

        Args:
            directory: Directory to search
            pattern: File pattern to match

        Returns:
            List of matching file paths
        """
        # Use Python pathlib instead of subprocess find
        self._metrics.python_operations += 1

        try:
            path = Path(directory)
            if not path.exists():
                return []

            # Use rglob for recursive search
            files = list(path.rglob(pattern))
            return [str(f) for f in files]

        except Exception as e:
            logger.error(f"File search failed: {e}")
            return []

    def _get_bash_session(self, session_type: str) -> PersistentBashSession:
        """Get next available bash session from pool using round-robin.

        Creates sessions lazily on first use to avoid conflicts with Qt initialization.

        Args:
            session_type: Type of session (workspace, general, etc.)

        Returns:
            PersistentBashSession instance
        """
        if DEBUG_VERBOSE:
            logger.debug(f"Getting bash session for type: {session_type}")

        with self._session_lock:
            # Initialize pool structure if needed (but don't create sessions yet)
            if session_type not in self._session_pools:
                self._session_pools[session_type] = []
                self._session_round_robin[session_type] = 0
                logger.info(f"Initialized empty pool for session type: {session_type}")
                if DEBUG_VERBOSE:
                    logger.debug("Pool structure created, no sessions yet (lazy init)")

            # Get or create sessions as needed
            pool = self._session_pools[session_type]

            # Create sessions lazily if pool is empty
            if not pool:
                logger.info(
                    f"LAZY INIT: Creating {self._sessions_per_type} sessions for pool type: {session_type}",
                )
                if DEBUG_VERBOSE:
                    logger.debug(
                        f"This is the FIRST use of {session_type} pool - creating sessions now",
                    )

                for i in range(self._sessions_per_type):
                    session_id = f"{session_type}_{i}"
                    try:
                        if DEBUG_VERBOSE:
                            logger.debug(
                                f"Creating session {i + 1}/{self._sessions_per_type}: {session_id}",
                            )

                        # Time session creation
                        if HAS_DEBUG_UTILS:
                            with timing_profiler.measure(
                                f"create_session_{session_id}",
                            ):
                                session = PersistentBashSession(session_id)
                        else:
                            session = PersistentBashSession(session_id)

                        pool.append(session)
                        logger.info(f"Created session {session_id} in pool")

                        # Delay between creating sessions to avoid resource contention
                        if i < self._sessions_per_type - 1:
                            time.sleep(0.3)  # Increased from 0.1 to 0.3
                            if DEBUG_VERBOSE:
                                logger.debug(
                                    "Pause before creating next session (0.3s)...",
                                )
                    except Exception as e:
                        logger.error(f"Failed to create session {session_id}: {e}")
                        # Continue with fewer sessions if some fail

                if not pool:
                    raise RuntimeError(
                        f"Failed to create any sessions for type {session_type}",
                    )

            # Get next session using round-robin
            index = self._session_round_robin[session_type]
            session = pool[index]

            if DEBUG_VERBOSE:
                logger.debug(
                    f"Selected session {session.session_id} (index {index}/{len(pool)})",
                )

            # Update round-robin counter
            self._session_round_robin[session_type] = (index + 1) % len(pool)

            # Check if session is alive, restart if needed
            # Access private method safely - this is internal to our module
            if not session._is_alive():  # type: ignore[reportPrivateUsage]
                logger.warning(f"Session {session.session_id} dead, restarting")
                if DEBUG_VERBOSE:
                    logger.debug(
                        f"Session {session.session_id} needs restart (process dead)",
                    )
                session._start_session()  # type: ignore[reportPrivateUsage]
            elif DEBUG_VERBOSE:
                logger.debug(f"Session {session.session_id} is alive and ready")

            return session

    def invalidate_cache(self, pattern: Optional[str] = None):
        """Invalidate command cache.

        Args:
            pattern: Optional pattern to match
        """
        self._cache.invalidate(pattern)

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics.

        Returns:
            Dictionary with metrics
        """
        metrics = self._metrics.get_report()
        metrics["cache_stats"] = self._cache.get_stats()

        # Add session stats for all pools
        session_stats = {}
        with self._session_lock:
            for session_type, pool in self._session_pools.items():
                pool_stats: List[Dict[str, Any]] = []
                for session in pool:
                    pool_stats.append(session.get_stats())
                session_stats[session_type] = {
                    "pool_size": len(pool),
                    "sessions": pool_stats,
                }

        metrics["sessions"] = session_stats

        return metrics

    def shutdown(self):
        """Shutdown the process pool manager."""
        # Close all bash sessions in all pools
        with self._session_lock:
            for session_type, pool in self._session_pools.items():
                logger.info(
                    f"Shutting down {len(pool)} sessions in {session_type} pool",
                )
                for session in pool:
                    session.close()
            self._session_pools.clear()
            self._session_round_robin.clear()

        # Shutdown executor
        self._executor.shutdown(wait=True)

        logger.info("ProcessPoolManager shutdown complete")


class ProcessMetrics:
    """Track process optimization metrics."""

    def __init__(self):
        """Initialize process metrics tracking."""
        super().__init__()
        self.subprocess_calls = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.python_operations = 0
        self.total_response_time = 0.0
        self.response_count = 0
        self.start_time = time.time()

    def update_response_time(self, time_ms: float):
        """Update response time metrics.

        Args:
            time_ms: Response time in milliseconds
        """
        self.total_response_time += time_ms
        self.response_count += 1

    def get_report(self) -> Dict[str, Any]:
        """Generate performance report.

        Returns:
            Dictionary with performance metrics
        """
        avg_response = (
            self.total_response_time / self.response_count
            if self.response_count > 0
            else 0
        )

        uptime = time.time() - self.start_time

        return {
            "subprocess_calls": self.subprocess_calls,
            "python_operations": self.python_operations,
            "average_response_ms": avg_response,
            "uptime_seconds": uptime,
            "calls_per_minute": (self.subprocess_calls / uptime * 60)
            if uptime > 0
            else 0,
        }


# Example usage
if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Get singleton instance
    pool = ProcessPoolManager.get_instance()

    # Test workspace command with caching
    result1 = pool.execute_workspace_command("echo 'test'", cache_ttl=5)
    print(f"First call: {result1}")

    result2 = pool.execute_workspace_command("echo 'test'", cache_ttl=5)
    print(f"Second call (cached): {result2}")

    # Test batch execution
    commands = ["echo 'one'", "echo 'two'", "echo 'three'"]
    results = pool.batch_execute(commands)
    print(f"Batch results: {results}")

    # Test file finding with Python
    files = pool.find_files_python("/tmp", "*.txt")
    print(f"Found files: {files}")

    # Print metrics
    metrics = pool.get_metrics()
    print(f"\nMetrics: {metrics}")

    # Cleanup
    pool.shutdown()

    sys.exit(0)
