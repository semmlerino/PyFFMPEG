# Qt Threading Fixes - Implementation Guide

## Fix #1: QtProgressReporter Thread Affinity

### Current Problem
`QtProgressReporter` is created in worker thread but receives calls from ThreadPoolExecutor threads.

### Solution
Create the reporter in the main thread and properly manage its lifecycle.

```python
# threede_scene_worker.py - FIXED VERSION

class ThreeDESceneWorker(ThreadSafeWorker):
    def __init__(self, ...):
        super().__init__()
        # ... existing init code ...

        # Create progress reporter in init (called from main thread)
        # This ensures proper thread affinity from the start
        self._progress_reporter = QtProgressReporter()
        # Don't move to thread yet - let it happen with the worker

    def run(self):
        """Override run to move reporter to worker thread."""
        # Move the reporter to this worker thread
        if self._progress_reporter:
            self._progress_reporter.moveToThread(self.thread())

        # Call parent run
        super().run()

    def do_work(self):
        # Remove reporter creation from here
        # self._progress_reporter = QtProgressReporter()  # DELETE THIS

        # Connect with explicit QueuedConnection since callbacks come from different threads
        if self._progress_reporter:
            self._progress_reporter.progress_update.connect(
                self._handle_progress_update,
                Qt.ConnectionType.QueuedConnection
            )
```

### Alternative Solution - Thread-Local Storage
```python
class ThreeDESceneWorker(ThreadSafeWorker):
    def __init__(self, ...):
        super().__init__()
        self._progress_reporter_lock = QMutex()
        self._progress_reporter = None

    def _get_or_create_reporter(self):
        """Thread-safe reporter creation with lazy initialization."""
        with QMutexLocker(self._progress_reporter_lock):
            if self._progress_reporter is None:
                # Create in the current thread
                self._progress_reporter = QtProgressReporter()
                # Ensure it's in the worker thread
                if QThread.currentThread() != self:
                    self._progress_reporter.moveToThread(self)
            return self._progress_reporter
```

## Fix #2: ProcessPoolManager Singleton Initialization

### Current Problem
`_initialized` flag is set before initialization completes, causing race condition.

### Solution
Set flag only after successful initialization.

```python
# process_pool_manager.py - FIXED VERSION

class ProcessPoolManager(LoggingMixin, QObject):
    _instance = None
    _lock = QMutex()

    def __new__(cls, *args, **kwargs):
        """Thread-safe singleton with double-checked locking."""
        if cls._instance is None:
            with QMutexLocker(cls._lock):
                if cls._instance is None:
                    instance = super().__new__(cls)
                    # Don't set _initialized here - do it in __init__
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self, max_workers: int = 4, sessions_per_type: int = 3):
        """Initialize with proper error handling."""
        with QMutexLocker(ProcessPoolManager._lock):
            if self._initialized:
                return

            # Don't set _initialized until everything succeeds
            try:
                # Initialize parent first
                super().__init__()

                # Create all components
                self._executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers
                )
                self._secure_executor = get_secure_executor()
                self._session_pools = {}
                self._session_round_robin = {}
                self._session_creation_in_progress = {}
                self._sessions_per_type = sessions_per_type
                self._cache = CommandCache(default_ttl=30)
                self._session_lock = threading.RLock()
                self._session_condition = threading.Condition(self._session_lock)
                self._metrics = ProcessMetrics()

                # Only NOW mark as initialized
                self._initialized = True
                self.logger.info(f"ProcessPoolManager initialized with {max_workers} workers")

            except Exception as e:
                # Initialization failed - reset state
                self._initialized = False
                # Clean up any partial initialization
                if hasattr(self, '_executor'):
                    try:
                        self._executor.shutdown(wait=False)
                    except:
                        pass
                self.logger.error(f"ProcessPoolManager initialization failed: {e}")
                raise
```

## Fix #3: Explicit Connection Types

### Current Problem
Missing explicit connection types for cross-thread signals.

### Solution
Always specify connection type for cross-thread signals.

```python
# launcher_manager.py - FIXED VERSION

class LauncherManager(LoggingMixin, QObject):
    def __init__(self, config_dir=None):
        super().__init__()
        # ... initialization ...

        # Connect with explicit QueuedConnection for thread safety
        # Process manager runs in different threads
        self._process_manager.process_started.connect(
            self.command_started,
            Qt.ConnectionType.QueuedConnection
        )
        self._process_manager.process_finished.connect(
            self.command_finished,
            Qt.ConnectionType.QueuedConnection
        )
        self._process_manager.process_error.connect(
            self.command_error,
            Qt.ConnectionType.QueuedConnection
        )
```

## Fix #4: ThumbnailLoader Lifecycle Management

### Current Problem
Signals object can be deleted while worker is still running.

### Solution
Use QPointer for weak references and proper parent-child relationships.

```python
# cache/thumbnail_loader.py - FIXED VERSION

from PySide6.QtCore import QPointer

class ThumbnailLoader(QRunnable):
    class Signals(QObject):
        """Signal definitions with proper parent."""
        loaded = Signal(str, str, str, Path)
        failed = Signal(str, str, str, str)

        def __init__(self, parent=None):
            # Accept parent for proper lifecycle
            super().__init__(parent)

    def __init__(self, ...):
        super().__init__()
        # Create signals with proper parent (though QRunnable isn't QObject)
        # Use QPointer for weak reference
        self._signals_obj = self.Signals()
        self.signals = QPointer(self._signals_obj)
        self.setAutoDelete(True)

    def run(self):
        """Process with safe signal emission."""
        try:
            # ... processing ...

            if success and self.cache_path.exists():
                self.result.set_result(self.cache_path)

                # Safe signal emission with QPointer check
                if self.signals:  # QPointer returns None if deleted
                    self.signals.loaded.emit(
                        self.show, self.sequence,
                        self.shot, self.cache_path
                    )
                else:
                    logger.debug("Signals deleted, skipping emission")

        except Exception as e:
            # Safe error signal emission
            if self.signals:
                self.signals.failed.emit(
                    self.show, self.sequence,
                    self.shot, str(e)
                )
```

## Fix #5: Lock Ordering Documentation

### Current Problem
Multiple locks without clear ordering could cause deadlock.

### Solution
Establish and document lock hierarchy.

```python
# thread_safe_worker.py - Add documentation

class ThreadSafeWorker(QThread):
    """Base class for thread-safe workers.

    LOCK ORDERING (to prevent deadlocks):
    1. _state_mutex (highest priority)
    2. _pause_mutex
    3. _finished_mutex (lowest priority)

    Always acquire locks in this order. Never acquire a higher
    priority lock while holding a lower priority one.
    """

    def _safe_multi_lock(self, *mutexes):
        """Acquire multiple locks in correct order."""
        # Sort mutexes by priority
        priority = {
            self._state_mutex: 1,
            self._pause_mutex: 2,
            self._finished_mutex: 3
        }

        sorted_mutexes = sorted(
            mutexes,
            key=lambda m: priority.get(m, 999)
        )

        # Acquire in order
        lockers = []
        for mutex in sorted_mutexes:
            lockers.append(QMutexLocker(mutex))

        return lockers
```

## Fix #6: Prevent Lost Wakeups

### Current Problem
QWaitCondition without counter can lose wakeups.

### Solution
Use counter pattern.

```python
# threede_scene_worker.py - FIXED VERSION

class ThreeDESceneWorker(ThreadSafeWorker):
    def __init__(self, ...):
        super().__init__()
        self._pause_mutex = QMutex()
        self._pause_condition = QWaitCondition()
        self._pause_counter = 0  # Add counter

    def pause(self):
        """Request pause with counter."""
        with QMutexLocker(self._pause_mutex):
            if not self._is_paused:
                self._is_paused = True
                self._pause_counter += 1  # Increment counter
                # Signal emitted outside lock

        if should_emit:
            self.paused.emit()

    def resume(self):
        """Resume with counter check."""
        with QMutexLocker(self._pause_mutex):
            if self._is_paused:
                self._is_paused = False
                if self._pause_counter > 0:
                    self._pause_counter -= 1
                self._pause_condition.wakeAll()

    def _check_pause_and_cancel(self):
        """Check pause with counter."""
        with QMutexLocker(self._pause_mutex):
            while self._is_paused and not self.should_stop():
                # Wait and check counter
                self._pause_condition.wait(
                    self._pause_mutex,
                    Config.WORKER_PAUSE_CHECK_INTERVAL_MS
                )
```

## Testing the Fixes

### Test for Fix #1 (Thread Affinity)
```python
def test_progress_reporter_thread_affinity():
    """Verify QtProgressReporter has correct thread affinity."""
    worker = ThreeDESceneWorker(shots=[], excluded_users=set())

    # Reporter should be in main thread initially
    assert worker._progress_reporter.thread() == QApplication.instance().thread()

    # Start worker
    worker.start()
    worker.wait(100)

    # After start, reporter should be in worker thread
    assert worker._progress_reporter.thread() == worker
```

### Test for Fix #2 (Singleton Race)
```python
def test_singleton_concurrent_init():
    """Test singleton under concurrent initialization."""
    import concurrent.futures

    # Clear existing instance
    ProcessPoolManager._instance = None

    def get_instance():
        return ProcessPoolManager.get_instance()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(get_instance) for _ in range(100)]
        instances = [f.result() for f in futures]

    # All should be same instance and initialized
    assert all(i is instances[0] for i in instances)
    assert instances[0]._initialized
```

## Verification Checklist

- [ ] QtProgressReporter created in main thread
- [ ] ProcessPoolManager._initialized set only after success
- [ ] All cross-thread signals use QueuedConnection
- [ ] ThumbnailLoader uses QPointer for signals
- [ ] Lock ordering documented and enforced
- [ ] Counter pattern for QWaitCondition
- [ ] No QPixmap operations in worker threads
- [ ] ThreadSafeWorker state transitions validated
- [ ] All tests pass with thread sanitizer
- [ ] No deadlocks under stress testing