# Plan to Fix Remaining Threading Issues

## Overview
This plan addresses the 3 critical threading issues discovered during verification of the THREADING_DEADLOCK_FIX_PLAN implementation.

## Critical Issues Identified

### 1. Signal Emission Inside Mutex in request_stop() (HIGH PRIORITY)
**File**: `thread_safe_worker.py` lines 145-166
**Problem**: Signals emitted inside mutex can cause deadlock if handlers call back
**Risk**: High - Could cause application freeze

### 2. Direct QTimer.singleShot Usage (MEDIUM PRIORITY) 
**File**: `launcher_manager.py` line 1617
**Problem**: Direct timer creation could cascade if called rapidly
**Risk**: Medium - Undermines cascading prevention fix

### 3. Worker Removal Race Condition (MEDIUM PRIORITY)
**File**: `launcher_manager.py` lines 1743-1777
**Problem**: Worker removed from dict before being fully stopped
**Risk**: Medium - Worker orphaning and resource leaks

## Implementation Plan

### Phase 1: Critical Threading Fixes (1-2 hours)

#### Fix 1: Signal Emission Inside Mutex in request_stop()
**File**: `thread_safe_worker.py` lines 145-166

```python
# CURRENT (PROBLEMATIC):
def request_stop(self) -> bool:
    with QMutexLocker(self._state_mutex):
        if current in [WorkerState.CREATED, WorkerState.STARTING]:
            self._state = WorkerState.STOPPED
            self.worker_stopped.emit()  # ❌ INSIDE MUTEX
            
# FIXED:
def request_stop(self) -> bool:
    signal_to_emit = None
    
    with QMutexLocker(self._state_mutex):
        current = self._state
        
        if current in [WorkerState.STOPPED, WorkerState.DELETED, WorkerState.STOPPING]:
            return False
            
        if current in [WorkerState.CREATED, WorkerState.STARTING]:
            self._state = WorkerState.STOPPED
            self._stop_requested = True
            signal_to_emit = self.worker_stopped
        elif current == WorkerState.RUNNING:
            self._state = WorkerState.STOPPING
            self._stop_requested = True
            signal_to_emit = self.worker_stopping
        else:
            return False
    
    # Emit signal OUTSIDE mutex (same pattern as set_state)
    if signal_to_emit:
        QTimer.singleShot(0, signal_to_emit.emit)
    
    return True
```

#### Fix 2: Replace Direct QTimer.singleShot
**File**: `launcher_manager.py` line 1617

```python
# CURRENT (line 1617):
QTimer.singleShot(1000, self._cleanup_finished_workers)

# ADD NEW METHOD:
def _schedule_cleanup_after_delay(self, delay_ms: int = 1000):
    """Schedule cleanup using managed approach to prevent cascading."""
    if self._cleanup_scheduled:
        logger.debug("Cleanup already scheduled, skipping duplicate")
        return
    
    self._cleanup_scheduled = True
    
    # Use the managed timer
    if not self._cleanup_retry_timer.isActive():
        self._cleanup_retry_timer.setInterval(delay_ms)
        self._cleanup_retry_timer.start()
    
# REPLACE line 1617 with:
self._schedule_cleanup_after_delay(1000)
```

#### Fix 3: Worker Removal Race Condition
**File**: `launcher_manager.py` lines 1743-1777

```python
# FIXED _remove_worker_safe method:
def _remove_worker_safe(self, worker_key: str):
    """Safely remove worker with proper cleanup."""
    with self._process_lock:
        worker = self._active_workers.get(worker_key)
        if not worker:
            return
        
        # First ensure worker is stopped (while still tracked)
        if worker.isRunning():
            logger.info(f"Stopping running worker {worker_key}")
            if hasattr(worker, 'safe_stop'):
                if not worker.safe_stop(timeout_ms=2000):
                    logger.warning(f"Worker {worker_key} failed to stop gracefully")
                    worker.terminate()
                    worker.wait(1000)
            else:
                worker.quit()
                if not worker.wait(2000):
                    worker.terminate()
                    worker.wait()
        
        # NOW remove from tracking (after stopped)
        self._active_workers.pop(worker_key, None)
        
        # Disconnect signals
        try:
            if hasattr(worker, 'disconnect_all'):
                worker.disconnect_all()
        except Exception:
            pass  # Already disconnected
        
        # Schedule for deletion
        worker.deleteLater()
        
        logger.debug(f"Worker {worker_key} removed successfully")
```

### Phase 2: Configuration Improvements (30 minutes)

#### Fix 4: Create Threading Configuration
**File**: `config.py` (add new class)

```python
class ThreadingConfig:
    """Threading and timeout configuration constants."""
    
    # Worker timeouts
    WORKER_STOP_TIMEOUT_MS = 2000
    WORKER_TERMINATE_TIMEOUT_MS = 1000
    WORKER_POLL_INTERVAL = 0.1
    
    # Cleanup timings
    CLEANUP_RETRY_DELAY_MS = 500
    CLEANUP_INITIAL_DELAY_MS = 1000
    
    # Process pool configuration
    SESSION_INIT_TIMEOUT = 2.0
    SESSION_MAX_RETRIES = 5
    SUBPROCESS_TIMEOUT = 30.0
    
    # Polling configuration
    INITIAL_POLL_INTERVAL = 0.01  # 10ms
    MAX_POLL_INTERVAL = 0.5  # 500ms
    POLL_BACKOFF_FACTOR = 1.5
    
    # Cache configuration
    CACHE_MAX_MEMORY_MB = 100
    CACHE_CLEANUP_INTERVAL = 30  # minutes
    
    # Thread pool settings
    MAX_WORKER_THREADS = 4
    THREAD_POOL_TIMEOUT = 5.0
```

### Phase 3: Unit Test Additions (1-2 hours)

#### Fix 5: Add Missing Unit Tests

**File**: `tests/unit/test_thread_safe_worker.py` (NEW)
- Test valid/invalid state transitions
- Test force parameter functionality
- Test signal emission outside mutex
- Test request_stop() behavior

**File**: `tests/unit/test_launcher_manager_threading.py` (NEW)
- Test cleanup scheduling prevents duplicates
- Test atomic state checking prevents deadlock
- Test worker removal race prevention

**File**: `tests/unit/test_cache_manager_threading.py` (NEW)
- Test ThumbnailCacheResult multiple completion prevention
- Test instance variable separation
- Test async/sync mode behavior

### Phase 4: Documentation (30 minutes)

#### Fix 6: Lock Ordering Documentation
**File**: `THREADING_ARCHITECTURE.md` (NEW)

Document:
- Lock ordering protocol
- Signal emission rules
- Worker lifecycle procedures
- Deadlock prevention guidelines

### Phase 5: Validation (1 hour)

#### Test Suite Execution
1. Run all threading tests
2. Run unit tests for affected components
3. Run stress tests
4. Check for deadlocks with thread sanitizer

## Implementation Order

1. **Hour 1**: Implement Critical Fixes 1-3
2. **Hour 2**: Configuration & Testing
3. **Hour 3**: Documentation & Validation

## Success Criteria

✅ All tests pass without warnings
✅ No deadlocks in stress tests
✅ Thread sanitizer reports no issues
✅ Code review confirms fixes are correct
✅ Performance benchmarks show no regression

## Risk Mitigation

- Create git branch before changes
- Run relevant tests after each fix
- Full test suite before merge
- Rollback plan available

Total estimated time: 3-4 hours implementation + 1 hour validation