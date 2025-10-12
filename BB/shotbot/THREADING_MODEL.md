# ShotBot Threading Model

**Last Updated**: 2025-10-11
**Version**: 1.0

## Overview

This document describes the threading model and synchronization primitives used throughout the ShotBot application. Following these guidelines prevents deadlocks, race conditions, and ensures thread-safe operation.

## Threading Primitives

### Qt Threading (Primary)

**Use for**: All Qt components (models, views, widgets)

```python
from PySide6.QtCore import QMutex, QMutexLocker

# Initialize
self._mutex = QMutex()

# Usage - always use QMutexLocker (RAII pattern)
with QMutexLocker(self._mutex):
    # Critical section - automatic cleanup even on exceptions
    self._shared_data = value
```

**Benefits**:
- Automatic cleanup via RAII pattern
- Integration with Qt's event system
- Cross-platform consistency
- No risk of deadlocks from forgotten unlocks

### Python Threading (Secondary)

**Use for**: Pure Python utilities that don't interact with Qt

```python
import threading

# Acceptable for standalone utilities
self._lock = threading.Lock()
self._rlock = threading.RLock()
```

**Restrictions**:
- ❌ **NEVER mix Qt and Python threading in the same class!**
- ✅ Only use for pure Python modules
- ✅ OK for utilities that don't interact with Qt objects

## Mutex Ordering (Deadlock Prevention)

**Critical Rule**: Always acquire mutexes in the same order. NEVER acquire mutexes in reverse order!

### Established Lock Hierarchy

From innermost (shortest hold time) to outermost (longest hold time):

1. **`_cache_mutex`** (innermost)
   - **Purpose**: Protects thumbnail cache and loading states
   - **Hold time**: Very short (dictionary lookups, state checks)
   - **Files**: `base_item_model.py`
   - **Example**:
     ```python
     with QMutexLocker(self._cache_mutex):
         return self._thumbnail_cache.get(item.full_name)
     ```

2. **`_scan_lock`** (middle)
   - **Purpose**: Protects scanning flags and worker state
   - **Hold time**: Short (flag checks, worker state)
   - **Files**: `previous_shots_model.py`, `threede_scene_model.py`
   - **Example**:
     ```python
     with QMutexLocker(self._scan_lock):
         if self._is_scanning:
             return False
         self._is_scanning = True
     ```

3. **Model Reset Locks** (outermost)
   - **Purpose**: Qt internal locks during `beginResetModel()`/`endResetModel()`
   - **Hold time**: Longest (entire model update)
   - **Files**: All models using QAbstractItemModel
   - **Managed by**: Qt framework (automatic)

### Deadlock Prevention Example

```python
# ✅ CORRECT: Acquire in order (cache → scan)
def update_with_scan(self):
    with QMutexLocker(self._cache_mutex):  # 1. Cache first
        cached_value = self._cache.get(key)

    with QMutexLocker(self._scan_lock):    # 2. Scan second
        if not self._is_scanning:
            self._start_scan(cached_value)

# ❌ WRONG: Reverse order causes deadlock risk!
def update_with_scan_wrong(self):
    with QMutexLocker(self._scan_lock):       # Wrong! Scan first
        with QMutexLocker(self._cache_mutex):  # Wrong! Cache inside scan
            # DEADLOCK RISK if another thread does it in correct order!
            value = self._cache.get(key)
```

## Fixed Issues

### Issue 1: Mixed Threading in `ProcessPoolManager`

**Problem** (Before):
```python
class ProcessPoolManager:
    def __init__(self):
        self._session_lock = threading.RLock()  # ❌ Python threading
        self._mutex = QMutex()                   # ❌ Qt threading
        # MIXING BOTH IN SAME CLASS!
```

**Solution** (After):
```python
class ProcessPoolManager:
    def __init__(self):
        self._session_lock = QMutex()  # ✅ Consistent Qt threading
        self._mutex = QMutex()         # ✅ Qt threading
        # All Qt mutexes - consistent and safe
```

**Impact**: Eliminates undefined behavior from mixing threading models.

### Issue 2: Race Condition in Thumbnail Loading

**Problem** (Before):
```python
# Check in one lock acquisition
with QMutexLocker(self._cache_mutex):
    if item.full_name in self._thumbnail_cache:
        continue
    state = self._loading_states.get(item.full_name)
    if state in ("loading", "failed"):
        continue
# ← RACE WINDOW: Another thread could start loading here!

# Mark in separate lock acquisition
self._load_thumbnail_async(row, item)
    with QMutexLocker(self._cache_mutex):
        self._loading_states[item.full_name] = "loading"
```

**Solution** (After):
```python
# Atomic check-and-mark in single lock acquisition
with QMutexLocker(self._cache_mutex):
    for row in range(start, end):
        item = self._items[row]

        if item.full_name in self._thumbnail_cache:
            continue
        state = self._loading_states.get(item.full_name)
        if state in ("loading", "failed"):
            continue

        # Mark as loading atomically (same lock)
        self._loading_states[item.full_name] = "loading"
        items_to_load.append((row, item))

# Load outside lock (already marked)
for row, item in items_to_load:
    self._load_thumbnail_async(row, item)
```

**Impact**: Eliminates duplicate thumbnail loads, improves performance.

## Best Practices

### 1. Always Use RAII Pattern

```python
# ✅ CORRECT: Use context manager (RAII)
with QMutexLocker(self._mutex):
    # Automatic cleanup on exception
    self._do_work()

# ❌ WRONG: Manual lock/unlock (forgetting unlock causes deadlock!)
self._mutex.lock()
try:
    self._do_work()
finally:
    self._mutex.unlock()  # Easy to forget or get wrong
```

### 2. Keep Lock Sections Short

```python
# ✅ CORRECT: Minimal lock duration
data_copy = None
with QMutexLocker(self._mutex):
    data_copy = self._data.copy()  # Quick copy

# Do expensive work outside lock
processed = expensive_computation(data_copy)

with QMutexLocker(self._mutex):
    self._result = processed

# ❌ WRONG: Holding lock during expensive operation
with QMutexLocker(self._mutex):
    data = self._data
    # Blocks other threads unnecessarily!
    processed = expensive_computation(data)
    self._result = processed
```

### 3. Document Lock Purpose

```python
class MyModel:
    def __init__(self):
        # Document what each lock protects
        self._cache_mutex = QMutex()  # Protects _thumbnail_cache and _loading_states
        self._scan_lock = QMutex()    # Protects _is_scanning flag
```

### 4. Use Helper Methods for Common Patterns

```python
# Create reusable helper for flag reset
def _reset_scanning_flag(self) -> None:
    """Reset scanning flag with proper locking."""
    with QMutexLocker(self._scan_lock):
        self._is_scanning = False

# Use in multiple places consistently
def _on_scan_finished(self):
    try:
        # Process results
        pass
    finally:
        self._reset_scanning_flag()  # Guaranteed cleanup
```

## Async Operations

For async operations (background workers), the lock must remain held for the ENTIRE operation:

```python
def refresh_shots(self):
    # Acquire lock at start
    with QMutexLocker(self._scan_lock):
        if self._is_scanning:
            return False
        self._is_scanning = True

    # Start async worker (lock released but flag stays True)
    self._worker.start()
    return True

def _on_worker_finished(self):
    # Reset flag when async work completes
    with QMutexLocker(self._scan_lock):
        self._is_scanning = False
```

**Note**: For async operations, context managers that auto-cleanup won't work. Use manual flag management with helper methods.

## Testing Thread Safety

```python
def test_concurrent_access(model, qtbot):
    """Test thread safety with concurrent access."""
    # Simulate rapid concurrent calls
    for _ in range(100):
        model.set_visible_range(0, 10)
        QApplication.processEvents()

    # Verify no race conditions (each item loaded exactly once)
    assert len(model._thumbnail_cache) <= len(model._items)
```

## References

- **Qt Documentation**: [QMutex](https://doc.qt.io/qt-6/qmutex.html)
- **Qt Documentation**: [QMutexLocker](https://doc.qt.io/qt-6/qmutexlocker.html)
- **RAII Pattern**: Resource Acquisition Is Initialization
- **Deadlock Prevention**: Lock ordering hierarchy

## Changelog

- **2025-10-11**: Initial version
  - Documented Qt vs Python threading guidelines
  - Established mutex ordering hierarchy
  - Fixed ProcessPoolManager mixed threading
  - Fixed thumbnail loading race condition
