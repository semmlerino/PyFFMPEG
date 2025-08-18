"""Thread-safe fixes for launcher_manager.py - Critical Qt threading violations."""

# This file contains the critical fixes for launcher_manager.py
# Apply these changes to prevent deadlocks and race conditions

import logging
import time
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QRecursiveMutex, Qt, Signal

logger = logging.getLogger(__name__)

class LauncherManagerFixed(QObject):
    """Fixed version of LauncherManager with proper Qt threading."""
    
    # Qt signals
    launchers_changed = Signal()
    launcher_added = Signal(str)  # launcher_id
    launcher_updated = Signal(str)  # launcher_id
    launcher_deleted = Signal(str)  # launcher_id
    validation_error = Signal(str, str)  # field, error_message
    execution_started = Signal(str)  # launcher_id
    execution_finished = Signal(str, bool)  # launcher_id, success
    
    def __init__(self):
        super().__init__()
        
        # Use Qt mutexes instead of Python threading primitives
        self._process_mutex = QRecursiveMutex()  # Replaces threading.RLock
        self._cleanup_mutex = QMutex()
        
        # Ensure we're in the main thread
        from PySide6.QtCore import QCoreApplication
        if QCoreApplication.instance():
            self.moveToThread(QCoreApplication.instance().thread())
        
        self._active_processes: Dict[str, Any] = {}
        self._active_workers: Dict[str, Any] = {}
        self._cleanup_in_progress = False
        self._cleanup_scheduled = False
        self._shutting_down = False
    
    def execute_launcher(
        self,
        launcher_id: str,
        custom_vars: Optional[Dict[str, str]] = None,
        dry_run: bool = False,
        use_worker: bool = True,
    ) -> bool:
        """Execute launcher with proper Qt thread safety."""
        
        # Check limits and collect error info under lock
        error_msg = None
        can_proceed = False
        
        with QMutexLocker(self._process_mutex):
            if len(self._active_processes) < self.MAX_CONCURRENT_PROCESSES:
                can_proceed = True
            else:
                error_msg = f"Maximum concurrent processes ({self.MAX_CONCURRENT_PROCESSES}) reached"
        
        # Emit signals OUTSIDE the lock to prevent deadlocks
        if error_msg:
            logger.warning(error_msg)
            self.validation_error.emit("general", error_msg)
            return False
        
        if not can_proceed:
            return False
        
        # Continue with execution...
        # (rest of the method implementation)
        return True
    
    def _execute_with_worker(
        self,
        launcher_id: str,
        launcher_name: str,
        command: str,
        working_dir: Optional[str] = None,
    ) -> bool:
        """Execute command using worker thread with proper lifecycle management."""
        try:
            from launcher_manager import LauncherWorker
            
            # Create and configure worker
            worker = LauncherWorker(launcher_id, command, working_dir)
            worker_key = f"{launcher_id}_{int(time.time() * 1000)}"
            
            # Connect signals BEFORE starting (with explicit connection types)
            worker.safe_connect(
                worker.command_started,
                lambda lid, cmd: logger.debug(f"Worker started: {lid} - {cmd}"),
                Qt.ConnectionType.QueuedConnection
            )
            worker.safe_connect(
                worker.command_finished,
                self._on_worker_finished,
                Qt.ConnectionType.QueuedConnection
            )
            worker.safe_connect(
                worker.command_error,
                lambda lid, error: logger.error(f"Worker error [{lid}]: {error}"),
                Qt.ConnectionType.QueuedConnection
            )
            
            # Start worker FIRST (before adding to tracking)
            worker.start()
            
            # THEN add to tracking after successful start
            with QMutexLocker(self._process_mutex):
                # Double-check worker is still running
                if worker.isRunning():
                    self._active_workers[worker_key] = worker
                    logger.info(f"Started worker thread for launcher '{launcher_name}'")
                    return True
                else:
                    logger.warning(f"Worker {worker_key} stopped before tracking")
                    worker.deleteLater()
                    return False
            
        except Exception as e:
            logger.error(f"Failed to start worker thread: {e}")
            # Emit signal outside any locks
            self.execution_finished.emit(launcher_id, False)
            return False
    
    def _check_worker_state_safe(self, worker_key: str) -> Tuple[str, bool]:
        """Check worker state without nested locking (prevents deadlock)."""
        # Get worker reference and immediately release lock
        worker = None
        with QMutexLocker(self._process_mutex):
            worker = self._active_workers.get(worker_key)
        
        if not worker:
            return ("DELETED", False)
        
        # Access worker state WITHOUT holding process lock
        # This prevents lock ordering issues
        try:
            state = worker.get_state()
            state_str = state.value if hasattr(state, 'value') else str(state)
            is_running = worker.isRunning()
            return (state_str, is_running)
        except Exception as e:
            logger.error(f"Failed to check worker {worker_key}: {e}")
            return ("ERROR", False)
    
    def _cleanup_finished_workers(self):
        """Thread-safe cleanup without cascading or deadlocks."""
        # Prevent cascading cleanup requests
        if self._cleanup_scheduled:
            logger.debug("Cleanup already scheduled, skipping duplicate request")
            return
        
        # Try to acquire cleanup lock without blocking
        if not self._cleanup_mutex.tryLock():
            self._cleanup_scheduled = True
            logger.debug("Cleanup in progress, will retry later")
            # Schedule retry using Qt timer (not shown for brevity)
            return
        
        try:
            self._cleanup_in_progress = True
            self._cleanup_scheduled = False
            
            # Get snapshot of workers WITHOUT holding lock during state checks
            worker_keys = []
            with QMutexLocker(self._process_mutex):
                worker_keys = list(self._active_workers.keys())
            
            finished_workers = []
            
            # Check each worker WITHOUT holding process lock
            for worker_key in worker_keys:
                state, is_running = self._check_worker_state_safe(worker_key)
                
                if state in ["STOPPED", "DELETED", "ERROR"] and not is_running:
                    finished_workers.append(worker_key)
                elif state == "CREATED" and not is_running:
                    # Never started
                    finished_workers.append(worker_key)
            
            # Remove finished workers
            for worker_key in finished_workers:
                self._remove_worker_safe(worker_key)
            
            if finished_workers:
                logger.debug(f"Cleaned up {len(finished_workers)} finished workers")
                
        finally:
            self._cleanup_in_progress = False
            self._cleanup_scheduled = False
            self._cleanup_mutex.unlock()
    
    def _remove_worker_safe(self, worker_key: str):
        """Safely remove worker with proper Qt cleanup sequence."""
        # Get worker reference
        worker = None
        with QMutexLocker(self._process_mutex):
            worker = self._active_workers.get(worker_key)
        
        if not worker:
            return
        
        # Stop worker OUTSIDE the lock to prevent deadlocks
        if worker.isRunning():
            logger.info(f"Stopping running worker {worker_key}")
            
            # Request stop using ThreadSafeWorker's method
            if worker.request_stop():
                # Wait for graceful stop
                if not worker.wait(5000):  # 5 second timeout
                    logger.warning(f"Worker {worker_key} didn't stop gracefully")
                    # Use Qt's interruption mechanism (safer than terminate)
                    worker.requestInterruption()
                    worker.quit()
                    if not worker.wait(2000):  # 2 more seconds
                        logger.error(f"Worker {worker_key} failed to stop, abandoning")
                        # Mark as zombie but don't terminate (crashes Qt)
        
        # Disconnect all signals
        try:
            if hasattr(worker, 'disconnect_all'):
                worker.disconnect_all()
        except RuntimeError:
            pass  # Already disconnected
        
        # NOW remove from tracking
        with QMutexLocker(self._process_mutex):
            self._active_workers.pop(worker_key, None)
        
        # Schedule for deletion via Qt's event loop (safe cleanup)
        worker.deleteLater()
        logger.debug(f"Worker {worker_key} removed successfully")
    
    def _on_worker_finished(self, launcher_id: str, success: bool, return_code: int):
        """Handle worker completion with deferred cleanup."""
        launcher_name = launcher_id  # Simplified for example
        
        if success:
            logger.info(f"Launcher '{launcher_name}' completed successfully")
        else:
            logger.warning(f"Launcher '{launcher_name}' failed with code {return_code}")
        
        # Emit signal (safe - we're in main thread via QueuedConnection)
        self.execution_finished.emit(launcher_id, success)
        
        # Schedule cleanup after a delay to avoid race conditions
        # Use QTimer::singleShot for delayed execution (not shown)
        # QTimer.singleShot(100, self._cleanup_finished_workers)
    
    def shutdown(self):
        """Gracefully shutdown with proper Qt cleanup."""
        logger.info("LauncherManager shutting down...")
        self._shutting_down = True
        
        # Stop all workers with Qt-safe methods
        worker_keys = []
        with QMutexLocker(self._process_mutex):
            worker_keys = list(self._active_workers.keys())
        
        for worker_key in worker_keys:
            self._remove_worker_safe(worker_key)
        
        # Final check
        with QMutexLocker(self._process_mutex):
            remaining = len(self._active_workers)
            if remaining > 0:
                logger.warning(f"Shutdown with {remaining} workers remaining")
            else:
                logger.info("All workers cleaned up successfully")

# Example of proper signal emission patterns
class SignalEmissionPatterns:
    """Examples of correct signal emission to avoid deadlocks."""
    
    def pattern_1_collect_then_emit(self):
        """Collect data under lock, emit after releasing."""
        data_to_emit = []
        
        with QMutexLocker(self.mutex):
            # Collect data while holding lock
            for item in self.items:
                if item.needs_signal:
                    data_to_emit.append(item.data)
        
        # Emit signals AFTER releasing lock
        for data in data_to_emit:
            self.data_ready.emit(data)
    
    def pattern_2_conditional_emission(self):
        """Check condition under lock, emit outside."""
        should_emit = False
        emit_data = None
        
        with QMutexLocker(self.mutex):
            if self.state == "ready":
                should_emit = True
                emit_data = self.current_data.copy()
        
        if should_emit:
            self.state_changed.emit("ready", emit_data)
    
    def pattern_3_atomic_state_change(self):
        """Atomic state change with signal emission."""
        old_state = None
        new_state = None
        
        with QMutexLocker(self.mutex):
            old_state = self.state
            self.state = "new_state"
            new_state = self.state
        
        # Emit transition signal outside lock
        if old_state != new_state:
            self.state_transition.emit(old_state, new_state)