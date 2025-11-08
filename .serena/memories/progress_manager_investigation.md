# ProgressManager Singleton Investigation Report

## Problem Summary
- Test `test_main_window_creates_all_components` fails when run in full suite
- Error: `AttributeError: type object 'ProgressManager' has no attribute 'get_instance'`
- Test PASSES when run alone
- Stack trace shows: `main_window.py:215: AttributeError`

## Investigation Findings

### 1. ProgressManager Singleton Implementation
**Location**: `/home/gabrielh/projects/shotbot/progress_manager.py`

**Pattern Used**: `__new__()` method with ClassVar storage
```python
class ProgressManager:
    _instance: ClassVar[ProgressManager | None] = None
    _operation_stack: ClassVar[list[ProgressOperation]] = []
    _status_bar: ClassVar[QStatusBar | None] = None
    
    def __new__(cls) -> ProgressManager:
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

**Public Methods Available**:
- `ProgressManager()` - Direct instantiation (creates singleton via __new__)
- `ProgressManager.initialize(status_bar)` - Initialize with UI references
- `ProgressManager.operation(...)` - Context manager for operations
- `ProgressManager.start_operation(config)` - Manual operation start
- `ProgressManager.finish_operation(success)` - Finish current operation
- `ProgressManager.get_current_operation()` - Get top operation
- `ProgressManager.cancel_current_operation()` - Cancel current
- `ProgressManager.is_operation_active()` - Check if active
- `ProgressManager.clear_all_operations()` - Emergency cleanup
- `ProgressManager.reset()` - Reset for testing

### 2. Key Finding: NO `get_instance()` method exists!
- ProgressManager does NOT have a `get_instance()` classmethod
- ProgressManager uses `__new__()` pattern → call directly as `ProgressManager()`
- By contrast, NotificationManager also doesn't have public `get_instance()`
- Both use `__new__()` pattern requiring direct instantiation

### 3. How main_window.py Accesses ProgressManager
**Location**: `/home/gabrielh/projects/shotbot/main_window.py:215`

```python
super().__init__(parent)  # This is line 215 - NOT related to ProgressManager!
```

The actual ProgressManager initialization happens later in the file:
```python
_ = ProgressManager.initialize(self.status_bar)
```

This uses `initialize()` classmethod, which internally calls `cls()` to get the singleton.

### 4. Test Setup/Teardown Behavior
**Location**: `/home/gabrielh/projects/shotbot/tests/conftest.py:380-384`

The `cleanup_state` fixture properly resets ProgressManager:
```python
try:
    ProgressManager.reset()
except (RuntimeError, AttributeError):
    # Qt objects may already be deleted
    pass
```

### 5. Why Test Fails in Full Suite But Passes Alone
- When test runs alone: ProgressManager is fresh, no pollution
- When test runs in suite: Previous test may leave ProgressManager in inconsistent state
- If `reset()` fails to properly restore the singleton, __new__() may break
- The `_instance` might be partially initialized, causing state issues

### 6. Comparison with NotificationManager
NotificationManager (`notification_manager.py:303`):
- Has `_get_instance()` (PRIVATE method, not public)
- Uses same `__new__()` pattern as ProgressManager
- Also properly implements `reset()` for testing
- Both are singletons meant to be used as `ProgressManager()` or `NotificationManager()`

## Root Cause Analysis

The error message suggests code somewhere is trying to call:
```python
ProgressManager.get_instance()  # This method doesn't exist!
```

But this call doesn't appear in:
- progress_manager.py itself
- main_window.py
- Any integration tests reviewed

### Possible Causes:
1. **State Corruption During Reset**: If ProgressManager._instance becomes corrupted during reset, subsequent `__new__()` calls fail
2. **Race Condition in Parallel Tests**: If running with pytest-xdist, cross-process state issues
3. **Missing Reset in Some Test Path**: A test path doesn't properly clean up ProgressManager

## Solution Path
1. Check if any code is calling the non-existent `get_instance()` method
2. Ensure `ProgressManager.reset()` properly restores all ClassVar state
3. Verify `__new__()` works correctly after reset
4. Check for cross-test pollution when running in parallel

## Code Pattern Summary

**Correct Usage**:
```python
# Get singleton instance (via __new__)
pm = ProgressManager()

# Or initialize with UI references
pm = ProgressManager.initialize(status_bar)

# Use classmethods
ProgressManager.start_operation(config)
ProgressManager.finish_operation(success=True)
```

**Incorrect Usage** (that would cause AttributeError):
```python
pm = ProgressManager.get_instance()  # WRONG - method doesn't exist!
```
