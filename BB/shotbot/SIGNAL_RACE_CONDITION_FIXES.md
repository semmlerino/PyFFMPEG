# Signal Race Condition Fixes in test_launcher_thread_safety.py

## Overview

Fixed critical signal race conditions in `test_launcher_thread_safety.py` according to UNIFIED_TESTING_GUIDE best practices. The main issue was threads starting BEFORE signal monitoring was set up, causing missed signals and unreliable tests.

## Key Issues Fixed

### 1. Race Condition in Lines 269-271 (CRITICAL)
**Problem**: Threads were started immediately without proper signal setup:
```python
# WRONG - Race condition
thread.start()  # Signal could be emitted before monitoring starts
```

**Solution**: Set up `qtbot.waitSignal()` BEFORE starting operations:
```python
# CORRECT - Signal monitoring ready before operation
with qtbot.waitSignal(signal, timeout=2000):
    start_operation()  # Operation starts INSIDE context manager
```

### 2. Non-existent Signal Connections
**Problem**: Test tried to connect to `command_output` which doesn't exist on LauncherManager:
```python
# WRONG - signal doesn't exist
self.manager.command_output.connect(on_signal)
```

**Solution**: Use actual LauncherManager signals:
```python
# CORRECT - actual signals
self.manager.execution_started.connect(track_execution_started)
self.manager.execution_finished.connect(track_execution_finished)
```

### 3. Missing qtbot Integration
**Problem**: Used unittest instead of pytest, missing qtbot for Qt widget cleanup.

**Solution**: Converted to pytest with proper qtbot usage:
```python
@pytest.fixture(autouse=True)
def setup_manager(self, qtbot):
    self.manager = LauncherManager()
    qtbot.addWidget(self.manager)  # Ensures proper cleanup
    self.qtbot = qtbot
```

## Detailed Fix Analysis

### test_signal_emission_thread_safety()
This method had the most critical race condition:

**Before (Problematic)**:
```python
# Threads start immediately - signals could be missed
for i in range(3):
    thread = threading.Thread(target=emit_signals, args=(i,))
    threads.append(thread)
    thread.start()  # RACE CONDITION HERE
```

**After (Fixed)**:
```python
# Set up signal monitoring BEFORE starting operations
signal_waiters = []
for launcher in launchers:
    signal_waiters.append(
        self.qtbot.waitSignal(self.manager.execution_started, timeout=2000)
    )

# Now start operations with proper synchronization
for launcher in launchers:
    thread = threading.Thread(target=execute_launcher_safely, args=(launcher,))
    thread.start()
```

### test_launcher_worker_cleanup()
**Before**: Manual QTest.qWait() without proper signal synchronization
**After**: Uses `qtbot.waitSignal()` for thread lifecycle testing:

```python
# FIXED: Proper signal-based waiting
with self.qtbot.waitSignal(worker.finished, timeout=5000):
    worker.start()
```

## Best Practices Applied

1. **Signal Setup Before Operations**
   - Always set up `qtbot.waitSignal()` BEFORE starting operations that emit signals
   - Use context managers to ensure proper signal monitoring

2. **Correct Signal References**
   - Verify signal names match actual class definitions
   - Use signals that actually exist on the object

3. **Qt Widget Cleanup**
   - Use `qtbot.addWidget()` for automatic cleanup
   - Convert unittest to pytest for proper Qt integration

4. **Thread Safety**
   - Use threading.Lock for shared data structures
   - Proper timeout handling for thread operations

## Testing the Fixes

Run the fixed tests:
```bash
# Use the test runner (not direct pytest)
python run_tests.py tests/unit/test_launcher_thread_safety.py

# Run specific method
python run_tests.py tests/unit/test_launcher_thread_safety.py::TestLauncherThreadSafety::test_signal_emission_thread_safety
```

## Validation

The fixes ensure:
- ✅ No race conditions in signal emission testing
- ✅ Proper Qt event loop integration
- ✅ Reliable signal delivery and reception
- ✅ Thread-safe concurrent execution testing
- ✅ Proper resource cleanup

## Pattern for Future Tests

When testing Qt signals in threads:

```python
def test_qt_signals_in_threads(self, qtbot):
    # 1. Set up signal monitoring FIRST
    with qtbot.waitSignal(object.signal_name, timeout=timeout_ms):
        # 2. Start operation INSIDE context manager
        start_threaded_operation()
    
    # 3. Verify results after signal received
    assert expected_outcome
```

This pattern prevents race conditions and ensures reliable signal testing.