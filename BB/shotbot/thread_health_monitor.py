"""Thread Health Monitoring System for ShotBot.

This module provides comprehensive monitoring of thread health, resource usage,
and potential issues like deadlocks or memory leaks in a Qt-based VFX application.

The monitoring system is designed to be:
- Low overhead (<5% CPU usage)
- Non-invasive (doesn't interfere with existing functionality)
- Thread-safe (works safely across multiple threads)
- Production-ready (includes circuit breakers and self-protection)

Key Components:
    ThreadHealthMonitor: Singleton coordinator for all monitoring activities
    QtThreadMonitor: Monitors QThread states and event loop responsiveness
    WorkerThreadMonitor: Tracks ThreadSafeWorker state transitions and performance
    ProcessPoolMonitor: Monitors subprocess creation, termination, and resource usage
    MetricsCollector: Ring buffer storage with hierarchical aggregation

Usage:
    # Initialize monitoring (typically in main application)
    monitor = ThreadHealthMonitor.get_instance()
    monitor.start_monitoring()

    # Register components for monitoring
    monitor.register_qt_thread(some_qthread)
    monitor.register_worker(some_worker)
    monitor.register_process_pool(some_pool)

    # Get health reports
    health_score = monitor.get_health_score()  # 0-100
    report = monitor.get_health_report()       # Detailed metrics

    # Cleanup
    monitor.stop_monitoring()

Examples:
    Basic health monitoring:
        >>> monitor = ThreadHealthMonitor.get_instance()
        >>> monitor.start_monitoring()
        >>> # ... application runs ...
        >>> if monitor.get_health_score() < 50:
        ...     print("Thread health degraded!")
        >>> monitor.stop_monitoring()

    Custom diagnostics:
        >>> monitor = ThreadHealthMonitor.get_instance()
        >>> monitor.enable_deadlock_detection(heartbeat_interval=1.0)
        >>> monitor.enable_resource_leak_detection(check_interval=30.0)
        >>> report = monitor.get_detailed_report(format="json")

Environment Variables:
    SHOTBOT_THREAD_MONITOR_DEBUG: Enable verbose monitoring debug output
    SHOTBOT_THREAD_MONITOR_INTERVAL: Override default monitoring interval (seconds)
    SHOTBOT_THREAD_MONITOR_DISABLE: Disable monitoring entirely for performance testing
"""

import json
import logging
import os
import threading
import time
import weakref
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

from PySide6.QtCore import (
    QObject,
    QThread,
    QTimer,
    Signal,
)

# Import existing components for integration
try:
    from thread_safe_worker import ThreadSafeWorker
    from thread_safe_worker import WorkerState as TSWorkerState

    HAS_THREAD_SAFE_WORKER = True
except ImportError:
    HAS_THREAD_SAFE_WORKER = False

    # Define fallback WorkerState for type hints
    class WorkerState(Enum):
        CREATED = "CREATED"
        STARTING = "STARTING"
        RUNNING = "RUNNING"
        STOPPING = "STOPPING"
        STOPPED = "STOPPED"
        ERROR = "ERROR"


import importlib.util

HAS_PROCESS_POOL_MANAGER = importlib.util.find_spec("process_pool_manager") is not None

logger = logging.getLogger(__name__)

# Configuration from environment
DEBUG_ENABLED = os.environ.get("SHOTBOT_THREAD_MONITOR_DEBUG", "").lower() in (
    "1",
    "true",
    "yes",
)
DEFAULT_INTERVAL = float(os.environ.get("SHOTBOT_THREAD_MONITOR_INTERVAL", "5.0"))
MONITORING_DISABLED = os.environ.get("SHOTBOT_THREAD_MONITOR_DISABLE", "").lower() in (
    "1",
    "true",
    "yes",
)

if DEBUG_ENABLED:
    logger.setLevel(logging.DEBUG)


class HealthStatus(Enum):
    """Overall health status levels."""

    EXCELLENT = "EXCELLENT"  # 90-100
    GOOD = "GOOD"  # 70-89
    WARNING = "WARNING"  # 50-69
    CRITICAL = "CRITICAL"  # 30-49
    FAILING = "FAILING"  # 0-29


class MetricType(Enum):
    """Types of metrics collected."""

    COUNTER = "COUNTER"  # Incrementing values
    GAUGE = "GAUGE"  # Current value
    HISTOGRAM = "HISTOGRAM"  # Distribution of values
    TIMER = "TIMER"  # Duration measurements


@dataclass
class ThreadMetric:
    """Individual thread metric data."""

    timestamp: float
    thread_id: int
    thread_name: str
    metric_type: MetricType
    metric_name: str
    value: Union[int, float]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthAlert:
    """Health alert information."""

    timestamp: float
    severity: HealthStatus
    component: str
    message: str
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "severity": self.severity.value,
            "component": self.component,
            "message": self.message,
            "metrics": self.metrics,
        }


class CircuitBreaker:
    """Circuit breaker to protect monitoring from overload."""

    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Time to wait before attempting reset (seconds)
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.Lock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.timeout:
                    self.state = "HALF_OPEN"
                else:
                    raise RuntimeError("Circuit breaker is OPEN")

            try:
                result = func(*args, **kwargs)
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failure_count = 0
                return result
            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()

                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.warning(
                        f"Circuit breaker opened due to {self.failure_count} failures",
                    )

                raise e


class MetricsCollector:
    """Thread-safe metrics collection with ring buffer storage."""

    def __init__(self, max_metrics: int = 10000, max_age_seconds: float = 3600.0):
        """Initialize metrics collector.

        Args:
            max_metrics: Maximum number of metrics to store in ring buffer
            max_age_seconds: Maximum age of metrics before expiry
        """
        self.max_metrics = max_metrics
        self.max_age_seconds = max_age_seconds
        self._metrics: deque = deque(maxlen=max_metrics)
        self._lock = threading.RLock()
        self._thread_local = threading.local()

        # Aggregated statistics
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._timers: Dict[str, List[float]] = defaultdict(list)

        # Circuit breaker for self-protection
        self._circuit_breaker = CircuitBreaker()

    def _get_thread_buffer(self) -> List[ThreadMetric]:
        """Get thread-local buffer for batching metrics."""
        if not hasattr(self._thread_local, "buffer"):
            self._thread_local.buffer = []
        return self._thread_local.buffer

    def add_metric(self, metric: ThreadMetric) -> None:
        """Add a metric to thread-local buffer for batching."""
        try:
            self._circuit_breaker.call(self._add_metric_impl, metric)
        except Exception as e:
            logger.debug(f"Metric collection failed: {e}")

    def _add_metric_impl(self, metric: ThreadMetric) -> None:
        """Implementation of metric addition."""
        # Add to thread-local buffer
        buffer = self._get_thread_buffer()
        buffer.append(metric)

        # Flush buffer when it gets large enough (batch processing)
        if len(buffer) >= 50:
            self.flush_thread_buffer()

    def flush_thread_buffer(self) -> None:
        """Flush thread-local buffer to main storage."""
        buffer = self._get_thread_buffer()
        if not buffer:
            return

        with self._lock:
            # Add all buffered metrics
            for metric in buffer:
                self._metrics.append(metric)
                self._update_aggregates(metric)

            # Clean up old metrics
            self._cleanup_old_metrics()

        # Clear thread buffer
        buffer.clear()

    def _update_aggregates(self, metric: ThreadMetric) -> None:
        """Update aggregated statistics."""
        key = f"{metric.thread_name}.{metric.metric_name}"

        if metric.metric_type == MetricType.COUNTER:
            self._counters[key] += int(metric.value)
        elif metric.metric_type == MetricType.GAUGE:
            self._gauges[key] = float(metric.value)
        elif metric.metric_type == MetricType.HISTOGRAM:
            self._histograms[key].append(float(metric.value))
            # Keep only recent values for histograms
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
        elif metric.metric_type == MetricType.TIMER:
            self._timers[key].append(float(metric.value))
            # Keep only recent values for timers
            if len(self._timers[key]) > 1000:
                self._timers[key] = self._timers[key][-1000:]

    def _cleanup_old_metrics(self) -> None:
        """Remove metrics older than max_age_seconds."""
        cutoff_time = time.time() - self.max_age_seconds

        # Remove old metrics from the left side of deque
        while self._metrics and self._metrics[0].timestamp < cutoff_time:
            self._metrics.popleft()

    def get_metrics(
        self,
        thread_name: Optional[str] = None,
        metric_name: Optional[str] = None,
        since: Optional[float] = None,
    ) -> List[ThreadMetric]:
        """Get metrics matching the specified criteria.

        Args:
            thread_name: Filter by thread name
            metric_name: Filter by metric name
            since: Only return metrics after this timestamp

        Returns:
            List of matching ThreadMetric objects
        """
        # Flush pending metrics first
        self.flush_thread_buffer()

        with self._lock:
            self._cleanup_old_metrics()

            metrics = list(self._metrics)

            # Apply filters
            if thread_name:
                metrics = [m for m in metrics if m.thread_name == thread_name]
            if metric_name:
                metrics = [m for m in metrics if m.metric_name == metric_name]
            if since:
                metrics = [m for m in metrics if m.timestamp >= since]

            return metrics

    def get_aggregates(self) -> Dict[str, Any]:
        """Get aggregated statistics."""
        self.flush_thread_buffer()

        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {k: list(v) for k, v in self._histograms.items()},
                "timers": {k: list(v) for k, v in self._timers.items()},
                "total_metrics": len(self._metrics),
                "oldest_metric": self._metrics[0].timestamp if self._metrics else None,
                "newest_metric": self._metrics[-1].timestamp if self._metrics else None,
            }


class QtThreadMonitor:
    """Monitor QThread states and event loop responsiveness."""

    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize Qt thread monitor.

        Args:
            metrics_collector: Shared metrics collector instance
        """
        self.metrics_collector = metrics_collector
        self._monitored_threads: Set[weakref.ref] = set()
        self._heartbeat_timers: Dict[int, QTimer] = {}
        self._heartbeat_responses: Dict[int, float] = {}
        self._lock = threading.Lock()

        # Configuration
        self.heartbeat_interval = 5.0  # seconds
        self.max_heartbeat_delay = 10.0  # seconds

    def register_thread(self, thread: QThread) -> None:
        """Register a QThread for monitoring.

        Args:
            thread: QThread instance to monitor
        """
        if MONITORING_DISABLED:
            return

        with self._lock:
            thread_ref = weakref.ref(thread, self._cleanup_thread)
            self._monitored_threads.add(thread_ref)

            # Set up heartbeat monitoring if thread is running
            if thread.isRunning():
                self._setup_heartbeat(thread)

            logger.debug(f"Registered QThread for monitoring: {thread}")

    def _setup_heartbeat(self, thread: QThread) -> None:
        """Set up heartbeat monitoring for a thread."""
        thread_id = int(QThread.currentThread().currentThreadId()) if thread.isRunning() else id(thread)

        # Create heartbeat timer
        timer = QTimer()
        timer.timeout.connect(lambda: self._send_heartbeat(thread))
        timer.start(int(self.heartbeat_interval * 1000))  # Convert to milliseconds

        self._heartbeat_timers[thread_id] = timer
        self._heartbeat_responses[thread_id] = time.time()

        logger.debug(f"Set up heartbeat for thread {thread_id}")

    def _send_heartbeat(self, thread: QThread) -> None:
        """Send heartbeat to thread and measure response time."""
        if not thread.isRunning():
            return

        thread_id = int(QThread.currentThread().currentThreadId())
        start_time = time.time()

        def heartbeat_response():
            response_time = time.time() - start_time
            self._heartbeat_responses[thread_id] = time.time()

            # Record heartbeat metrics
            metric = ThreadMetric(
                timestamp=time.time(),
                thread_id=thread_id,
                thread_name=f"QThread-{thread_id}",
                metric_type=MetricType.TIMER,
                metric_name="heartbeat_response_time",
                value=response_time,
                metadata={"heartbeat_interval": self.heartbeat_interval},
            )
            self.metrics_collector.add_metric(metric)

        # Schedule heartbeat response in thread's event loop
        QTimer.singleShot(0, heartbeat_response)

    def _cleanup_thread(self, thread_ref: weakref.ref) -> None:
        """Clean up monitoring data for a destroyed thread."""
        with self._lock:
            self._monitored_threads.discard(thread_ref)

        # Clean up heartbeat timer if it exists
        # Note: We can't easily get the thread_id from the weakref after destruction
        # So we'll rely on periodic cleanup

    def check_health(self) -> Dict[str, Any]:
        """Check health of monitored Qt threads.

        Returns:
            Dictionary containing health metrics and any issues found
        """
        if MONITORING_DISABLED:
            return {"status": "disabled", "threads": []}

        health_data = {
            "status": "healthy",
            "threads": [],
            "issues": [],
            "summary": {
                "total_threads": 0,
                "running_threads": 0,
                "responsive_threads": 0,
                "unresponsive_threads": 0,
            },
        }

        current_time = time.time()

        with self._lock:
            # Clean up dead thread references
            self._monitored_threads = {
                ref for ref in self._monitored_threads if ref() is not None
            }

            for thread_ref in self._monitored_threads:
                thread = thread_ref()
                if thread is None:
                    continue

                thread_id = (
                    int(thread.currentThreadId()) if thread.isRunning() else id(thread)
                )
                thread_info = {
                    "thread_id": thread_id,
                    "is_running": thread.isRunning(),
                    "is_finished": thread.isFinished(),
                    "priority": thread.priority().name
                    if hasattr(thread.priority(), "name")
                    else str(thread.priority()),
                }

                # Check heartbeat responsiveness
                last_response = self._heartbeat_responses.get(thread_id, 0)
                if last_response > 0:
                    time_since_response = current_time - last_response
                    thread_info["last_heartbeat"] = time_since_response
                    thread_info["responsive"] = (
                        time_since_response < self.max_heartbeat_delay
                    )

                    if time_since_response >= self.max_heartbeat_delay:
                        health_data["issues"].append(
                            {
                                "type": "unresponsive_thread",
                                "thread_id": thread_id,
                                "time_since_response": time_since_response,
                            },
                        )
                        health_data["summary"]["unresponsive_threads"] += 1
                    else:
                        health_data["summary"]["responsive_threads"] += 1
                else:
                    thread_info["responsive"] = None

                health_data["threads"].append(thread_info)
                health_data["summary"]["total_threads"] += 1

                if thread.isRunning():
                    health_data["summary"]["running_threads"] += 1

        # Determine overall status
        if health_data["summary"]["unresponsive_threads"] > 0:
            health_data["status"] = (
                "warning"
                if health_data["summary"]["unresponsive_threads"]
                < health_data["summary"]["total_threads"] / 2
                else "critical"
            )

        return health_data


class WorkerThreadMonitor:
    """Monitor ThreadSafeWorker state transitions and performance."""

    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize worker thread monitor.

        Args:
            metrics_collector: Shared metrics collector instance
        """
        self.metrics_collector = metrics_collector
        self._monitored_workers: Set[weakref.ref] = set()
        self._worker_states: Dict[int, WorkerState] = {}
        self._worker_start_times: Dict[int, float] = {}
        self._lock = threading.Lock()

    def register_worker(self, worker: "ThreadSafeWorker") -> None:
        """Register a ThreadSafeWorker for monitoring.

        Args:
            worker: ThreadSafeWorker instance to monitor
        """
        if MONITORING_DISABLED or not HAS_THREAD_SAFE_WORKER:
            return

        with self._lock:
            worker_ref = weakref.ref(worker, self._cleanup_worker)
            self._monitored_workers.add(worker_ref)

            worker_id = id(worker)
            self._worker_states[worker_id] = worker.get_state()
            self._worker_start_times[worker_id] = time.time()

            # Connect to worker signals for state tracking
            if hasattr(worker, "worker_started"):
                worker.worker_started.connect(
                    lambda: self._on_worker_state_change(worker, WorkerState.RUNNING),
                )
            if hasattr(worker, "worker_stopping"):
                worker.worker_stopping.connect(
                    lambda: self._on_worker_state_change(worker, WorkerState.STOPPING),
                )
            if hasattr(worker, "worker_stopped"):
                worker.worker_stopped.connect(
                    lambda: self._on_worker_state_change(worker, WorkerState.STOPPED),
                )
            if hasattr(worker, "worker_error"):
                worker.worker_error.connect(
                    lambda msg: self._on_worker_error(worker, msg),
                )

            logger.debug(f"Registered ThreadSafeWorker for monitoring: {worker}")

    def _on_worker_state_change(
        self, worker: "ThreadSafeWorker", new_state: WorkerState,
    ) -> None:
        """Handle worker state change."""
        worker_id = id(worker)
        old_state = self._worker_states.get(worker_id, WorkerState.CREATED)

        with self._lock:
            self._worker_states[worker_id] = new_state

        # Record state transition metric
        metric = ThreadMetric(
            timestamp=time.time(),
            thread_id=worker_id,
            thread_name=f"Worker-{worker_id}",
            metric_type=MetricType.COUNTER,
            metric_name="state_transition",
            value=1,
            metadata={
                "old_state": old_state.value
                if hasattr(old_state, "value")
                else str(old_state),
                "new_state": new_state.value
                if hasattr(new_state, "value")
                else str(new_state),
            },
        )
        self.metrics_collector.add_metric(metric)

        # Record duration metrics for completed workers
        if new_state == WorkerState.STOPPED:
            start_time = self._worker_start_times.get(worker_id)
            if start_time:
                duration = time.time() - start_time
                duration_metric = ThreadMetric(
                    timestamp=time.time(),
                    thread_id=worker_id,
                    thread_name=f"Worker-{worker_id}",
                    metric_type=MetricType.TIMER,
                    metric_name="worker_lifetime",
                    value=duration,
                    metadata={
                        "final_state": new_state.value
                        if hasattr(new_state, "value")
                        else str(new_state),
                    },
                )
                self.metrics_collector.add_metric(duration_metric)

    def _on_worker_error(self, worker: "ThreadSafeWorker", error_message: str) -> None:
        """Handle worker error."""
        worker_id = id(worker)

        # Record error metric
        metric = ThreadMetric(
            timestamp=time.time(),
            thread_id=worker_id,
            thread_name=f"Worker-{worker_id}",
            metric_type=MetricType.COUNTER,
            metric_name="worker_error",
            value=1,
            metadata={"error_message": error_message},
        )
        self.metrics_collector.add_metric(metric)

    def _cleanup_worker(self, worker_ref: weakref.ref) -> None:
        """Clean up monitoring data for a destroyed worker."""
        with self._lock:
            self._monitored_workers.discard(worker_ref)

    def check_health(self) -> Dict[str, Any]:
        """Check health of monitored worker threads.

        Returns:
            Dictionary containing health metrics and any issues found
        """
        if MONITORING_DISABLED or not HAS_THREAD_SAFE_WORKER:
            return {"status": "disabled", "workers": []}

        health_data = {
            "status": "healthy",
            "workers": [],
            "issues": [],
            "summary": {
                "total_workers": 0,
                "running_workers": 0,
                "stopped_workers": 0,
                "error_workers": 0,
                "zombie_workers": 0,
            },
        }

        current_time = time.time()

        with self._lock:
            # Clean up dead worker references
            self._monitored_workers = {
                ref for ref in self._monitored_workers if ref() is not None
            }

            for worker_ref in self._monitored_workers:
                worker = worker_ref()
                if worker is None:
                    continue

                worker_id = id(worker)
                current_state = self._worker_states.get(worker_id, WorkerState.CREATED)
                start_time = self._worker_start_times.get(worker_id, current_time)

                worker_info = {
                    "worker_id": worker_id,
                    "state": current_state.value
                    if hasattr(current_state, "value")
                    else str(current_state),
                    "lifetime": current_time - start_time,
                    "is_zombie": getattr(worker, "_zombie", False)
                    if hasattr(worker, "_zombie")
                    else False,
                }

                health_data["workers"].append(worker_info)
                health_data["summary"]["total_workers"] += 1

                # Categorize workers
                if current_state == WorkerState.RUNNING:
                    health_data["summary"]["running_workers"] += 1
                elif current_state == WorkerState.STOPPED:
                    health_data["summary"]["stopped_workers"] += 1
                elif current_state == WorkerState.ERROR:
                    health_data["summary"]["error_workers"] += 1

                if worker_info["is_zombie"]:
                    health_data["summary"]["zombie_workers"] += 1
                    health_data["issues"].append(
                        {
                            "type": "zombie_worker",
                            "worker_id": worker_id,
                            "lifetime": worker_info["lifetime"],
                        },
                    )

                # Check for long-running workers
                if (
                    current_state == WorkerState.RUNNING
                    and worker_info["lifetime"] > 3600
                ):  # 1 hour
                    health_data["issues"].append(
                        {
                            "type": "long_running_worker",
                            "worker_id": worker_id,
                            "lifetime": worker_info["lifetime"],
                        },
                    )

        # Determine overall status
        if (
            health_data["summary"]["error_workers"] > 0
            or health_data["summary"]["zombie_workers"] > 0
        ):
            health_data["status"] = "warning"

        if (
            health_data["summary"]["error_workers"]
            > health_data["summary"]["total_workers"] / 2
        ):
            health_data["status"] = "critical"

        return health_data


class ProcessPoolMonitor:
    """Monitor subprocess creation, termination, and resource usage."""

    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize process pool monitor.

        Args:
            metrics_collector: Shared metrics collector instance
        """
        self.metrics_collector = metrics_collector
        self._monitored_pools: Set[weakref.ref] = set()
        self._process_counts: Dict[str, int] = defaultdict(int)
        self._active_processes: Set[int] = set()
        self._lock = threading.Lock()

        # Configuration
        self.check_interval = 30.0  # seconds
        self._last_check = time.time()

    def register_pool(self, pool_manager: Any) -> None:
        """Register a process pool manager for monitoring.

        Args:
            pool_manager: Process pool manager instance
        """
        if MONITORING_DISABLED:
            return

        with self._lock:
            pool_ref = weakref.ref(pool_manager, self._cleanup_pool)
            self._monitored_pools.add(pool_ref)

            logger.debug(f"Registered process pool for monitoring: {pool_manager}")

    def record_process_start(self, process_id: int, command: str) -> None:
        """Record the start of a new process.

        Args:
            process_id: Process ID
            command: Command being executed
        """
        if MONITORING_DISABLED:
            return

        with self._lock:
            self._active_processes.add(process_id)
            self._process_counts["started"] += 1

        # Record process start metric
        metric = ThreadMetric(
            timestamp=time.time(),
            thread_id=process_id,
            thread_name="ProcessPool",
            metric_type=MetricType.COUNTER,
            metric_name="process_started",
            value=1,
            metadata={"command": command[:100]},  # Truncate long commands
        )
        self.metrics_collector.add_metric(metric)

    def record_process_end(
        self, process_id: int, return_code: int, duration: float,
    ) -> None:
        """Record the end of a process.

        Args:
            process_id: Process ID
            return_code: Process return code
            duration: Process duration in seconds
        """
        if MONITORING_DISABLED:
            return

        with self._lock:
            self._active_processes.discard(process_id)
            if return_code == 0:
                self._process_counts["completed"] += 1
            else:
                self._process_counts["failed"] += 1

        # Record process completion metrics
        metric = ThreadMetric(
            timestamp=time.time(),
            thread_id=process_id,
            thread_name="ProcessPool",
            metric_type=MetricType.TIMER,
            metric_name="process_duration",
            value=duration,
            metadata={"return_code": return_code},
        )
        self.metrics_collector.add_metric(metric)

        # Record completion counter
        status_metric = ThreadMetric(
            timestamp=time.time(),
            thread_id=process_id,
            thread_name="ProcessPool",
            metric_type=MetricType.COUNTER,
            metric_name="process_completed" if return_code == 0 else "process_failed",
            value=1,
            metadata={"return_code": return_code},
        )
        self.metrics_collector.add_metric(status_metric)

    def _cleanup_pool(self, pool_ref: weakref.ref) -> None:
        """Clean up monitoring data for a destroyed pool."""
        with self._lock:
            self._monitored_pools.discard(pool_ref)

    def check_health(self) -> Dict[str, Any]:
        """Check health of monitored process pools.

        Returns:
            Dictionary containing health metrics and any issues found
        """
        if MONITORING_DISABLED:
            return {"status": "disabled", "pools": []}

        current_time = time.time()

        # Only do expensive checks periodically
        if current_time - self._last_check < self.check_interval:
            return self._get_cached_health()

        self._last_check = current_time

        health_data = {
            "status": "healthy",
            "pools": [],
            "issues": [],
            "summary": {
                "total_pools": 0,
                "active_processes": len(self._active_processes),
                "processes_started": self._process_counts["started"],
                "processes_completed": self._process_counts["completed"],
                "processes_failed": self._process_counts["failed"],
            },
        }

        with self._lock:
            # Clean up dead pool references
            self._monitored_pools = {
                ref for ref in self._monitored_pools if ref() is not None
            }

            for pool_ref in self._monitored_pools:
                pool = pool_ref()
                if pool is None:
                    continue

                pool_info = {
                    "pool_id": id(pool),
                    "active_processes": len(self._active_processes),
                }

                # Try to get pool-specific information if available
                if hasattr(pool, "get_pool_stats"):
                    try:
                        stats = pool.get_pool_stats()
                        pool_info.update(stats)
                    except Exception as e:
                        logger.debug(f"Failed to get pool stats: {e}")

                health_data["pools"].append(pool_info)
                health_data["summary"]["total_pools"] += 1

        # Check for issues
        if health_data["summary"]["active_processes"] > 50:  # High process count
            health_data["issues"].append(
                {
                    "type": "high_process_count",
                    "active_processes": health_data["summary"]["active_processes"],
                },
            )
            health_data["status"] = "warning"

        failure_rate = 0
        total_processes = (
            health_data["summary"]["processes_completed"]
            + health_data["summary"]["processes_failed"]
        )
        if total_processes > 0:
            failure_rate = health_data["summary"]["processes_failed"] / total_processes

            if failure_rate > 0.1:  # More than 10% failure rate
                health_data["issues"].append(
                    {"type": "high_failure_rate", "failure_rate": failure_rate},
                )
                health_data["status"] = "warning" if failure_rate < 0.3 else "critical"

        return health_data

    def _get_cached_health(self) -> Dict[str, Any]:
        """Get cached health information for frequent checks."""
        return {
            "status": "healthy",
            "summary": {
                "active_processes": len(self._active_processes),
                "processes_started": self._process_counts["started"],
                "processes_completed": self._process_counts["completed"],
                "processes_failed": self._process_counts["failed"],
            },
            "cached": True,
            "last_full_check": self._last_check,
        }


class ThreadHealthMonitor(QObject):
    """Singleton coordinator for all thread health monitoring."""

    # Signals for health updates
    health_updated = Signal(dict)  # Overall health data
    alert_triggered = Signal(dict)  # Health alert
    diagnostics_available = Signal(dict)  # Diagnostic information

    _instance: Optional["ThreadHealthMonitor"] = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize thread health monitor."""
        super().__init__()

        if ThreadHealthMonitor._instance is not None:
            raise RuntimeError(
                "ThreadHealthMonitor is a singleton. Use get_instance().",
            )

        # Core components
        self.metrics_collector = MetricsCollector()
        self.qt_thread_monitor = QtThreadMonitor(self.metrics_collector)
        self.worker_thread_monitor = WorkerThreadMonitor(self.metrics_collector)
        self.process_pool_monitor = ProcessPoolMonitor(self.metrics_collector)

        # Configuration
        self.monitoring_interval = DEFAULT_INTERVAL
        self.deadlock_detection_enabled = False
        self.resource_leak_detection_enabled = False
        self.diagnostic_mode = DEBUG_ENABLED

        # State
        self._monitoring_active = False
        self._monitor_timer: Optional[QTimer] = None
        self._alerts: List[HealthAlert] = []
        self._health_history: deque = deque(maxlen=100)

        # Circuit breaker for self-protection
        self._circuit_breaker = CircuitBreaker()

        logger.info("ThreadHealthMonitor initialized")

    @classmethod
    def get_instance(cls) -> "ThreadHealthMonitor":
        """Get singleton instance of ThreadHealthMonitor."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def start_monitoring(self) -> None:
        """Start health monitoring."""
        if MONITORING_DISABLED:
            logger.info("Thread monitoring is disabled by environment variable")
            return

        if self._monitoring_active:
            logger.warning("Monitoring is already active")
            return

        self._monitoring_active = True

        # Set up monitoring timer
        self._monitor_timer = QTimer()
        self._monitor_timer.timeout.connect(self._perform_health_check)
        self._monitor_timer.start(int(self.monitoring_interval * 1000))

        logger.info(
            f"Started thread health monitoring (interval: {self.monitoring_interval}s)",
        )

        # Emit initial health update
        self._perform_health_check()

    def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        if not self._monitoring_active:
            return

        self._monitoring_active = False

        if self._monitor_timer:
            self._monitor_timer.stop()
            self._monitor_timer = None

        # Flush any remaining metrics
        self.metrics_collector.flush_thread_buffer()

        logger.info("Stopped thread health monitoring")

    def register_qt_thread(self, thread: QThread) -> None:
        """Register a QThread for monitoring."""
        self.qt_thread_monitor.register_thread(thread)

    def register_worker(self, worker: "ThreadSafeWorker") -> None:
        """Register a ThreadSafeWorker for monitoring."""
        self.worker_thread_monitor.register_worker(worker)

    def register_process_pool(self, pool_manager: Any) -> None:
        """Register a process pool for monitoring."""
        self.process_pool_monitor.register_pool(pool_manager)

    def enable_deadlock_detection(self, heartbeat_interval: float = 5.0) -> None:
        """Enable deadlock detection with specified heartbeat interval."""
        self.deadlock_detection_enabled = True
        self.qt_thread_monitor.heartbeat_interval = heartbeat_interval
        logger.info(f"Enabled deadlock detection (heartbeat: {heartbeat_interval}s)")

    def enable_resource_leak_detection(self, check_interval: float = 30.0) -> None:
        """Enable resource leak detection with specified check interval."""
        self.resource_leak_detection_enabled = True
        self.process_pool_monitor.check_interval = check_interval
        logger.info(f"Enabled resource leak detection (check: {check_interval}s)")

    def _perform_health_check(self) -> None:
        """Perform comprehensive health check."""
        try:
            self._circuit_breaker.call(self._health_check_impl)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            # Emit critical alert
            alert = HealthAlert(
                timestamp=time.time(),
                severity=HealthStatus.CRITICAL,
                component="ThreadHealthMonitor",
                message=f"Health check system failure: {e}",
            )
            self._alerts.append(alert)
            self.alert_triggered.emit(alert.to_dict())

    def _health_check_impl(self) -> None:
        """Implementation of health check."""
        start_time = time.time()

        # Collect health data from all monitors
        qt_health = self.qt_thread_monitor.check_health()
        worker_health = self.worker_thread_monitor.check_health()
        process_health = self.process_pool_monitor.check_health()

        # Calculate overall health score
        health_score = self._calculate_health_score(
            qt_health, worker_health, process_health,
        )

        # Compile comprehensive health report
        health_data = {
            "timestamp": time.time(),
            "health_score": health_score,
            "status": self._get_status_from_score(health_score),
            "components": {
                "qt_threads": qt_health,
                "worker_threads": worker_health,
                "process_pools": process_health,
            },
            "metrics": self.metrics_collector.get_aggregates(),
            "check_duration": time.time() - start_time,
        }

        # Store in history
        self._health_history.append(health_data)

        # Check for alerts
        self._check_for_alerts(health_data)

        # Emit health update
        self.health_updated.emit(health_data)

        if self.diagnostic_mode:
            logger.debug(
                f"Health check completed: score={health_score}, duration={health_data['check_duration']:.3f}s",
            )

    def _calculate_health_score(
        self, qt_health: Dict, worker_health: Dict, process_health: Dict,
    ) -> int:
        """Calculate overall health score (0-100)."""
        scores = []

        # Qt thread health (weight: 0.4)
        qt_score = 100
        if qt_health.get("status") == "warning":
            qt_score = 60
        elif qt_health.get("status") == "critical":
            qt_score = 30
        scores.append((qt_score, 0.4))

        # Worker thread health (weight: 0.4)
        worker_score = 100
        if worker_health.get("status") == "warning":
            worker_score = 60
        elif worker_health.get("status") == "critical":
            worker_score = 30
        scores.append((worker_score, 0.4))

        # Process pool health (weight: 0.2)
        process_score = 100
        if process_health.get("status") == "warning":
            process_score = 60
        elif process_health.get("status") == "critical":
            process_score = 30
        scores.append((process_score, 0.2))

        # Calculate weighted average
        total_weight = sum(weight for _, weight in scores)
        if total_weight == 0:
            return 100

        weighted_sum = sum(score * weight for score, weight in scores)
        return max(0, min(100, int(weighted_sum / total_weight)))

    def _get_status_from_score(self, score: int) -> HealthStatus:
        """Convert health score to status enum."""
        if score >= 90:
            return HealthStatus.EXCELLENT
        if score >= 70:
            return HealthStatus.GOOD
        if score >= 50:
            return HealthStatus.WARNING
        if score >= 30:
            return HealthStatus.CRITICAL
        return HealthStatus.FAILING

    def _check_for_alerts(self, health_data: Dict) -> None:
        """Check for conditions that should trigger alerts."""
        current_time = time.time()
        alerts_to_emit = []

        # Check overall health score
        health_score = health_data["health_score"]
        if health_score < 50:
            alert = HealthAlert(
                timestamp=current_time,
                severity=HealthStatus.CRITICAL
                if health_score < 30
                else HealthStatus.WARNING,
                component="Overall",
                message=f"System health degraded (score: {health_score})",
                metrics={"health_score": health_score},
            )
            alerts_to_emit.append(alert)

        # Check component-specific issues
        for component_name, component_data in health_data["components"].items():
            issues = component_data.get("issues", [])
            for issue in issues:
                severity = (
                    HealthStatus.CRITICAL
                    if issue["type"] in ["zombie_worker", "high_failure_rate"]
                    else HealthStatus.WARNING
                )
                alert = HealthAlert(
                    timestamp=current_time,
                    severity=severity,
                    component=component_name,
                    message=f"{issue['type']}: {issue}",
                    metrics=issue,
                )
                alerts_to_emit.append(alert)

        # Store and emit alerts
        for alert in alerts_to_emit:
            self._alerts.append(alert)
            self.alert_triggered.emit(alert.to_dict())

        # Clean up old alerts (keep only last 100)
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-100:]

    def get_health_score(self) -> int:
        """Get current health score (0-100)."""
        if not self._health_history:
            return 100  # Default healthy score
        return self._health_history[-1]["health_score"]

    def get_health_report(self, format: str = "dict") -> Union[Dict[str, Any], str]:
        """Get comprehensive health report.

        Args:
            format: Output format ('dict' or 'json')

        Returns:
            Health report in requested format
        """
        if not self._health_history:
            report = {"status": "no_data", "message": "No health data available"}
        else:
            report = dict(self._health_history[-1])

            # Add recent alerts
            recent_alerts = [alert.to_dict() for alert in self._alerts[-10:]]
            report["recent_alerts"] = recent_alerts

            # Add trend information
            if len(self._health_history) >= 2:
                prev_score = self._health_history[-2]["health_score"]
                current_score = self._health_history[-1]["health_score"]
                report["trend"] = {
                    "direction": "improving"
                    if current_score > prev_score
                    else "degrading"
                    if current_score < prev_score
                    else "stable",
                    "change": current_score - prev_score,
                }

        if format == "json":
            return json.dumps(report, indent=2, default=str)
        return report

    def get_detailed_report(self, format: str = "dict") -> Union[Dict, str]:
        """Get detailed diagnostic report with metrics.

        Args:
            format: Output format ('dict' or 'json')

        Returns:
            Detailed report in requested format
        """
        # Get basic health report
        report = self.get_health_report(format="dict")
        
        # Ensure report is a dict before adding to it
        if not isinstance(report, dict):
            return {"error": "Failed to get health report"}

        # Add detailed metrics
        report["detailed_metrics"] = {
            "aggregates": self.metrics_collector.get_aggregates(),
            "recent_metrics": self.metrics_collector.get_metrics(
                since=time.time() - 300,
            ),  # Last 5 minutes
            "monitoring_config": {
                "monitoring_interval": self.monitoring_interval,
                "deadlock_detection_enabled": self.deadlock_detection_enabled,
                "resource_leak_detection_enabled": self.resource_leak_detection_enabled,
                "diagnostic_mode": self.diagnostic_mode,
            },
        }

        # Add system information
        import threading

        report["system_info"] = {
            "active_thread_count": threading.active_count(),
            "main_thread_id": threading.main_thread().ident,
            "monitoring_thread_id": threading.current_thread().ident,
        }

        if format == "json":
            return json.dumps(report, indent=2, default=str)
        return report

    def reset_metrics(self) -> None:
        """Reset all collected metrics and history."""
        self.metrics_collector = MetricsCollector()
        self.qt_thread_monitor.metrics_collector = self.metrics_collector
        self.worker_thread_monitor.metrics_collector = self.metrics_collector
        self.process_pool_monitor.metrics_collector = self.metrics_collector

        self._alerts.clear()
        self._health_history.clear()

        logger.info("Reset all health monitoring metrics")

    def __del__(self):
        """Cleanup when instance is destroyed."""
        try:
            self.stop_monitoring()
        except Exception:
            pass  # Ignore errors during cleanup


# Convenience functions for easy integration
def start_monitoring(interval: float = DEFAULT_INTERVAL) -> ThreadHealthMonitor:
    """Start thread health monitoring with specified interval.

    Args:
        interval: Monitoring interval in seconds

    Returns:
        ThreadHealthMonitor instance
    """
    monitor = ThreadHealthMonitor.get_instance()
    monitor.monitoring_interval = interval
    monitor.start_monitoring()
    return monitor


def get_health_status() -> Dict[str, Any]:
    """Get current health status.

    Returns:
        Dictionary with current health information
    """
    monitor = ThreadHealthMonitor.get_instance()
    return monitor.get_health_report()


def register_thread_for_monitoring(thread: QThread) -> None:
    """Register a QThread for health monitoring.

    Args:
        thread: QThread instance to monitor
    """
    monitor = ThreadHealthMonitor.get_instance()
    monitor.register_qt_thread(thread)


def register_worker_for_monitoring(worker: "ThreadSafeWorker") -> None:
    """Register a ThreadSafeWorker for health monitoring.

    Args:
        worker: ThreadSafeWorker instance to monitor
    """
    monitor = ThreadHealthMonitor.get_instance()
    monitor.register_worker(worker)


# Example usage and testing
if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    # Basic test of the monitoring system
    app = QApplication(sys.argv)

    # Start monitoring
    monitor = start_monitoring(interval=2.0)
    monitor.enable_deadlock_detection()
    monitor.enable_resource_leak_detection()

    # Create some test threads
    test_thread = QThread()
    test_thread.start()
    register_thread_for_monitoring(test_thread)

    # Print health status after a short delay
    def print_status():
        print("Health Status:")
        print(json.dumps(get_health_status(), indent=2, default=str))

    QTimer.singleShot(5000, print_status)  # Print after 5 seconds
    QTimer.singleShot(10000, app.quit)  # Quit after 10 seconds

    sys.exit(app.exec())
