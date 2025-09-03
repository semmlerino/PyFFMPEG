"""Process Pool Manager for optimized subprocess handling.

This module provides centralized process management with pooling, caching,
and session reuse to reduce the overhead of repeated subprocess calls.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, List

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from config import ThreadingConfig
from persistent_bash_session import PersistentBashSession
from secure_command_executor import get_secure_executor
from type_definitions import PerformanceMetricsDict

# Import debug utilities
try:
    from debug_utils import (
        setup_enhanced_debugging,
        timing_profiler,
    )

    _has_debug_utils = True
except ImportError:
    _has_debug_utils = False

HAS_DEBUG_UTILS = _has_debug_utils

# Note: fcntl is not currently used, setting HAS_FCNTL to False
HAS_FCNTL = False

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
        self._cache: dict[
            str,
            tuple[Any, float, int, str],
        ] = {}  # key -> (result, timestamp, ttl, original_command)
        self._lock = threading.RLock()
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, command: str) -> Any | None:
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

    def set(self, command: str, result: Any, ttl: int | None = None):
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

    def invalidate(self, pattern: str | None = None):
        """Invalidate cache entries.

        Args:
            pattern: pattern to match (invalidates all if None)
        """
        with self._lock:
            if pattern is None:
                self._cache.clear()
                logger.info("Cleared entire command cache")
            else:
                # Check the original command (4th element in tuple) for pattern
                keys_to_remove: list[str] = []
                for key, value in self._cache.items():
                    if len(value) >= 4 and pattern in value[3]:
                        keys_to_remove.append(key)
                for key in keys_to_remove:
                    del self._cache[key]
                logger.info(
                    f"Invalidated {len(keys_to_remove)} cache entries matching '{pattern}'",
                )

    def get_stats(self) -> dict[str, Any]:
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
    _lock = threading.RLock()  # Use reentrant lock to prevent deadlock in nested calls

    # Qt signals
    command_completed = Signal(str, object)  # command_id, result
    command_failed = Signal(str, str)  # command_id, error

    def __new__(cls, *args, **kwargs):
        """Ensure singleton pattern with proper thread safety.

        Note: Double-checked locking is broken in Python due to GIL
        and memory model. We use lock-first approach for safety.
        """
        with cls._lock:
            if cls._instance is None:
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
            # Replace session pools with secure executor
            self._secure_executor = get_secure_executor()
            self._session_pools: dict[
                str, List[PersistentBashSession]
            ] = {}  # Deprecated, kept for compatibility
            self._session_round_robin: dict[str, int] = {}  # Track next session to use
            self._session_creation_in_progress: dict[
                str, bool
            ] = {}  # Prevent double creation
            self._sessions_per_type = sessions_per_type
            self._cache = CommandCache(default_ttl=30)
            self._session_lock = threading.RLock()
            # Add condition variable for proper thread synchronization
            self._session_condition = threading.Condition(self._session_lock)
            self._metrics = ProcessMetrics()
            self._initialized = True

        logger.info(f"ProcessPoolManager initialized with {max_workers} workers")

    @classmethod
    def get_instance(cls) -> ProcessPoolManager:
        """Get singleton instance.

        Thread safety is handled by __new__ method.

        Returns:
            ProcessPoolManager singleton
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def execute_workspace_command(
        self,
        command: str,
        cache_ttl: int = 30,
        timeout: int | None = None,
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

        # Use secure executor instead of bash session
        start_time = time.time()
        try:
            # Execute with secure validation
            result = self._secure_executor.execute(
                command,
                timeout=timeout,
                cache_ttl=0,  # Handle caching separately
                allow_workspace_function=True,  # Allow 'ws' commands
            )

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
        commands: list[str],
        cache_ttl: int = 30,
        session_type: str = "workspace",
    ) -> dict[str, str | None]:
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
        results: dict[str, str | None] = {}
        commands_to_execute: list[str] = []

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
        futures: dict[concurrent.futures.Future[str], str] = {}
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
        # Use secure executor for shell commands
        start_time = time.time()
        try:
            # Execute with secure validation
            result = self._secure_executor.execute(
                command,
                timeout=30,  # Default timeout for shell commands
                cache_ttl=0,  # No caching for general shell commands
                allow_workspace_function=False,  # Standard commands only
            )

            # Update metrics
            elapsed = (time.time() - start_time) * 1000
            self._metrics.update_response_time(elapsed)
            self._metrics.subprocess_calls += 1

            return result

        except Exception as e:
            logger.error(f"Session pool execution failed: {e}")
            raise

    def find_files_python(self, directory: str, pattern: str) -> list[str]:
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

    def _get_bash_session_deprecated(self, session_type: str) -> None:
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
                self._session_creation_in_progress[session_type] = False
                logger.info(f"Initialized empty pool for session type: {session_type}")
                if DEBUG_VERBOSE:
                    logger.debug("Pool structure created, no sessions yet (lazy init)")

            # Check if another thread is already creating sessions
            if self._session_creation_in_progress.get(session_type, False):
                logger.debug(
                    f"Waiting for another thread to finish creating {session_type} sessions"
                )
                # Wait for creation to complete using condition variable (thread-safe)
                while self._session_creation_in_progress.get(session_type, False):
                    # This atomically releases the lock and waits, then re-acquires when notified
                    self._session_condition.wait(timeout=0.1)

            # Get or create sessions as needed
            pool = self._session_pools[session_type]

            # Create sessions lazily if pool is empty
            if not pool and not self._session_creation_in_progress.get(
                session_type, False
            ):
                # Mark that we're creating sessions
                self._session_creation_in_progress[session_type] = True

                try:
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
                finally:
                    # Always clear the creation flag and notify waiting threads
                    self._session_creation_in_progress[session_type] = False
                    # Notify all threads waiting on this condition
                    self._session_condition.notify_all()

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

    def invalidate_cache(self, pattern: str | None = None):
        """Invalidate command cache.

        Args:
            pattern: pattern to match
        """
        self._cache.invalidate(pattern)

    def get_metrics(self) -> PerformanceMetricsDict:
        """Get performance metrics.

        Returns:
            Performance metrics dictionary
        """
        metrics = self._metrics.get_report()

        # Build proper PerformanceMetricsDict structure
        # Use defaults for any missing required fields
        result: PerformanceMetricsDict = {
            "total_shots": metrics.get("total_shots", 0),
            "total_refreshes": metrics.get("total_refreshes", 0),
            "last_refresh_time": metrics.get("last_refresh_time", 0.0),
            "cache_hits": metrics.get("cache_hits", 0),
            "cache_misses": metrics.get("cache_misses", 0),
            "cache_hit_rate": metrics.get("cache_hit_rate", 0.0),
            "cache_hit_count": metrics.get("cache_hit_count", 0),
            "cache_miss_count": metrics.get("cache_miss_count", 0),
            "loading_in_progress": metrics.get("loading_in_progress", False),
            "session_warmed": metrics.get("session_warmed", False),
        }

        return result

    def shutdown(self):
        """Shutdown the process pool manager."""
        # Clear round-robin tracking
        with self._session_lock:
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

    def get_report(self) -> dict[str, Any]:
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

        # Calculate cache hit rate
        total_cache_requests = self.cache_hits + self.cache_misses
        cache_hit_rate = (
            (self.cache_hits / total_cache_requests * 100)
            if total_cache_requests > 0
            else 0.0
        )

        return {
            "subprocess_calls": self.subprocess_calls,
            "python_operations": self.python_operations,
            "average_response_ms": avg_response,
            "uptime_seconds": uptime,
            "calls_per_minute": (self.subprocess_calls / uptime * 60)
            if uptime > 0
            else 0,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": cache_hit_rate,
        }


# Example usage
if __name__ == "__main__":
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
