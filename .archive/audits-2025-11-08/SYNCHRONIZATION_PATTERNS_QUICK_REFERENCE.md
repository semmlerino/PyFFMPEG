# Qt Synchronization Patterns - Quick Reference

**Use this guide when writing or reviewing tests that use Qt signals and async operations.**

---

## Pattern 1: Wait for Signal with Trigger

**When to use**: Testing that a signal is emitted when an operation starts

### ✅ CORRECT
```python
def test_worker_starts_on_refresh(qtbot: QtBot, controller: MyController) -> None:
    """Verify worker signal is emitted when refresh starts."""
    with qtbot.waitSignal(controller.worker_started, timeout=5000):
        controller.refresh()  # Trigger operation
    # Test continues only after signal received
    # If timeout → test fails
```

**Why good**:
- Explicitly waits for signal
- Fails if signal never emitted
- No arbitrary timing/sleeping
- Intent is clear

### ❌ WRONG
```python
def test_worker_starts_on_refresh(qapp: QApplication, controller: MyController) -> None:
    """Verify worker starts."""
    controller.refresh()
    qapp.processEvents()        # ❌ No guarantee signal has arrived
    time.sleep(0.1)             # ❌ Arbitrary delay
    assert controller.is_active # ❌ Fragile - timing-dependent
```

**Why bad**:
- No guarantee signal was emitted
- Compensates with arbitrary sleep
- Flaky under high CPU load
- Intent is unclear

---

## Pattern 2: Wait for State Change

**When to use**: Testing that some state changes after an operation

### ✅ CORRECT
```python
def test_window_hides_on_close(qtbot: QtBot, window: QMainWindow) -> None:
    """Verify window closes when requested."""
    window.show()
    
    # Wait explicitly for visible state to change
    qtbot.waitUntil(lambda: window.isVisible(), timeout=2000)  # Ensure shown
    
    window.close()
    
    # Wait for state change
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=2000)
    # Test continues only after window is hidden
```

**Why good**:
- Explicitly waits for desired state
- Readable condition (lambda)
- No sleeping or magic delays
- Fails if condition never met

### ❌ WRONG
```python
def test_window_hides_on_close(qapp: QApplication, window: QMainWindow) -> None:
    """Verify window closes."""
    window.close()
    time.sleep(0.2)  # ❌ Arbitrary delay
    assert not window.isVisible()  # ❌ Timing-dependent
```

---

## Pattern 3: Verify Signal NOT Emitted

**When to use**: Testing that an operation does NOT trigger a signal

### ✅ CORRECT
```python
def test_safe_operation_no_errors(qtbot: QtBot, app: MyApp) -> None:
    """Verify safe operation doesn't emit error signal."""
    with qtbot.assertNotEmitted(app.error_signal, wait=500):
        app.do_safe_operation()  # Should NOT trigger error signal
    # Test continues only after 500ms with no signal
```

**Why good**:
- Explicitly verifies negative condition
- Clear intent (should NOT happen)
- Prevents false positives

### ❌ WRONG
```python
def test_safe_operation_no_errors(app: MyApp) -> None:
    """Verify safe operation doesn't error."""
    app.do_safe_operation()
    time.sleep(0.5)
    # ❌ No guarantee error signal wasn't emitted
```

---

## Pattern 4: Multiple Signals

**When to use**: Waiting for multiple async events to complete

### ✅ CORRECT - Option A (Sequential)
```python
def test_worker_lifecycle(qtbot: QtBot, worker: MyWorker) -> None:
    """Verify worker emits signals in correct sequence."""
    with qtbot.waitSignal(worker.started, timeout=5000):
        worker.start()
    # Worker has started
    
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.do_work()
    # Worker has finished
```

**Why good**:
- Clear sequence of events
- Each signal is verified
- Fails if any signal missing

### ✅ CORRECT - Option B (Parallel)
```python
def test_batch_operations_complete(qtbot: QtBot, batch: BatchWorker) -> None:
    """Verify all operations complete."""
    waiter = create_async_waiter(qtbot)
    waiter.add_signal(batch.task1_done)
    waiter.add_signal(batch.task2_done)
    waiter.add_signal(batch.task3_done)
    
    batch.start_all()
    
    assert waiter.wait_for_all(timeout_ms=5000)
    # All tasks have completed
```

**Why good**:
- Readable API
- All conditions must be met
- Explicit timeout

### ❌ WRONG
```python
def test_worker_completes(qapp: QApplication, worker: MyWorker) -> None:
    """Verify worker completes."""
    worker.start()
    time.sleep(1.0)  # ❌ Hope it finishes in 1 second
    # ❌ No guarantee it actually finished
```

---

## Pattern 5: File System Synchronization

**When to use**: Waiting for file operations to complete

### ✅ CORRECT
```python
def test_file_written(tmp_path: Path) -> None:
    """Verify file is written by operation."""
    test_file = tmp_path / "output.json"
    
    write_operation(test_file)
    
    # Wait for file to appear
    assert wait_for_file_operation(test_file, "exists", timeout_ms=1000)
    assert test_file.read_text() == expected_content
```

**Why good**:
- Explicit wait for file to appear
- Helper abstracts timing logic
- No arbitrary sleeps

### ❌ WRONG
```python
def test_file_written(tmp_path: Path) -> None:
    """Verify file is written."""
    test_file = tmp_path / "output.json"
    write_operation(test_file)
    time.sleep(0.1)  # ❌ Arbitrary - what if it takes longer?
    assert test_file.exists()
```

---

## Pattern 6: Thread Operations

**When to use**: Testing code that spawns threads

### ✅ CORRECT
```python
def test_background_work(qtbot: QtBot) -> None:
    """Verify background work completes."""
    worker = BackgroundWorker()
    
    # Wait for thread to start
    with wait_for_threads_to_start():
        worker.start()
    
    # Wait for work to complete
    with qtbot.waitSignal(worker.finished, timeout=5000):
        pass  # Signal from worker.finished
    
    assert worker.result == expected_value
```

**Why good**:
- Explicit wait for thread to start
- Signal verifies completion
- No timing assumptions

### ❌ WRONG
```python
def test_background_work() -> None:
    """Verify background work."""
    worker = BackgroundWorker()
    worker.start()
    time.sleep(0.5)  # ❌ Hope thread finishes in 0.5s
    assert worker.result == expected_value
```

---

## Common Mistakes

### ❌ Mistake 1: Bare processEvents() without condition

```python
# ❌ BAD - No guarantee events have arrived
controller.refresh()
qapp.processEvents()
time.sleep(0.1)  # Compensating with sleep
qapp.processEvents()

# ✅ GOOD - Wait for signal
with qtbot.waitSignal(controller.worker_started, timeout=1000):
    controller.refresh()
```

### ❌ Mistake 2: time.sleep() for synchronization

```python
# ❌ BAD - Arbitrary delay, flaky under load
widget.show()
time.sleep(0.2)
assert widget.isVisible()

# ✅ GOOD - Explicit wait
widget.show()
qtbot.waitUntil(lambda: widget.isVisible(), timeout=2000)
```

### ❌ Mistake 3: No timeout

```python
# ❌ BAD - Can hang forever
with qtbot.waitSignal(signal):  # No timeout!
    trigger_operation()

# ✅ GOOD - Always specify timeout
with qtbot.waitSignal(signal, timeout=5000):
    trigger_operation()
```

### ❌ Mistake 4: Triggering outside waitSignal context

```python
# ❌ BAD - May miss signal
with qtbot.waitSignal(signal):
    pass
trigger_operation()  # Too late!

# ✅ GOOD - Trigger inside context
with qtbot.waitSignal(signal, timeout=5000):
    trigger_operation()  # Signal will be caught
```

---

## Available Synchronization Helpers

**Location**: `tests/helpers/synchronization.py`

```python
from tests.helpers.synchronization import (
    wait_for_condition,
    wait_for_qt_signal,
    wait_for_file_operation,
    process_qt_events,
    wait_for_threads_to_start,
    create_async_waiter,
)

# General-purpose polling
wait_for_condition(lambda: widget.isVisible(), timeout_ms=1000)

# Qt signal wrapper
wait_for_qt_signal(qtbot, signal, timeout_ms=1000, trigger=func)

# File system wait
wait_for_file_operation(path, "exists", timeout_ms=100)

# Controlled event processing
process_qt_events(qapp, duration_ms=10)

# Thread count synchronization
with wait_for_threads_to_start():
    thread.start()

# Multiple signals
waiter = create_async_waiter(qtbot)
waiter.add_signal(model.started)
waiter.add_signal(model.finished)
waiter.wait_for_all(timeout_ms=1000)
```

---

## Qt Cleanup Fixtures

**For tests that create windows/widgets:**

```python
# tests/conftest.py provides automatic cleanup via:
# - qt_cleanup fixture (autouse=True)
# - cleanup_state fixture (autouse=True)

# These handle:
# 1. Waiting for threads to complete
# 2. Processing deleteLater() calls
# 3. Clearing Qt caches
# 4. Resetting singletons

# You just need to add widgets to qtbot:
def test_my_widget(qtbot: QtBot) -> None:
    widget = MyWidget()
    qtbot.addWidget(widget)  # Cleanup happens automatically
```

---

## Checklist for Code Review

When reviewing tests, verify:

- [ ] No `time.sleep()` for synchronization (only work simulation)
- [ ] No bare `qapp.processEvents()` without condition
- [ ] `qtbot.waitSignal()` used for async operations
- [ ] `qtbot.waitUntil()` used for state changes
- [ ] All waits have explicit timeout
- [ ] Signal triggers are inside `waitSignal()` context
- [ ] Widgets are added to qtbot: `qtbot.addWidget(widget)`
- [ ] No shared state between tests

---

## References

- **UNIFIED_TESTING_V2.MD** - Complete testing guide
- **pytest-qt documentation** - https://pytest-qt.readthedocs.io/
- **Qt Test Framework** - https://doc.qt.io/qt-6/qtest.html

