# Qt Warning Detection System

This document describes how ShotBot catches Qt signal/slot issues early through automated testing.

## Overview

Qt runtime warnings (like "unique connections require a pointer to member function") can indicate serious bugs but aren't caught by static analysis tools like basedpyright or ruff. This system ensures these issues fail tests immediately.

## Three-Layer Detection System

### 1. Unit Tests for Signal Infrastructure (`test_qt_signal_warnings.py`)

**What it tests**: Core `ThreadSafeWorker.safe_connect()` signal connection mechanism

**How it works**: Captures stderr during signal operations and asserts no Qt warnings appear

**Example**:
```python
def test_safe_connect_produces_no_qt_warnings(qapp: QApplication) -> None:
    """Fails if Qt emits unique connection warnings."""
    old_stderr = sys.stderr
    sys.stderr = captured_stderr = StringIO()

    try:
        worker = DummyWorker()
        worker.safe_connect(worker.test_signal, test_slot)
        worker.test_signal.emit("test")
        qapp.processEvents()

        # FAIL if Qt warnings present
        assert "unique connections require" not in captured_stderr.getvalue()
    finally:
        sys.stderr = old_stderr
```

**Catches**:
- `UniqueConnection` flag misuse with Python callables
- Incorrect signal connection patterns
- Signal disconnection failures

**Run**: `uv run pytest tests/unit/test_qt_signal_warnings.py -v`

---

### 2. Integration Tests for Real Components (`test_threede_controller_signals.py`)

**What it tests**: Full controller workflows (initialization, refresh, cleanup)

**How it works**: Exercises real ThreeDEController operations while monitoring stderr

**Example**:
```python
def test_threede_refresh_signals_no_warnings(qapp, threede_components):
    """Ensures controller refresh produces no Qt warnings."""
    old_stderr = sys.stderr
    sys.stderr = captured_stderr = StringIO()

    try:
        controller.refresh_threede_scenes()
        qapp.processEvents()

        # FAIL if Qt warnings during refresh
        assert "Failed to disconnect" not in captured_stderr.getvalue()
    finally:
        sys.stderr = old_stderr
```

**Catches**:
- Signal connection issues in controller workflows
- Worker cleanup problems
- Accumulated warnings from multiple operations

**Run**: `uv run pytest tests/unit/test_threede_controller_signals.py -v`

---

### 3. Pytest Warning Filters (Warnings-as-Errors)

**What it does**: Converts specific RuntimeWarnings into test failures

**Configuration** (`pyproject.toml`):
```toml
[tool.pytest.ini_options]
filterwarnings = [
    # Qt signal/slot warnings that should FAIL tests
    "error::RuntimeWarning:thread_safe_worker:.*Failed to disconnect.*",
    "error::RuntimeWarning:controllers.*:.*Failed to disconnect.*",

    # Allow other RuntimeWarnings (but log them)
    "default::RuntimeWarning",
]
```

**Catches**:
- Any `Failed to disconnect` warnings from worker or controller code
- Turns warnings into immediate test failures
- Works across ALL tests automatically

**Run**: Standard test runs automatically apply these filters

---

## Reusable Test Fixture

**`capture_qt_warnings` fixture** (`tests/conftest.py`):

Makes warning capture easy in any test:

```python
def test_my_feature(qapp, capture_qt_warnings):
    with capture_qt_warnings() as warnings:
        # Exercise code that might produce Qt warnings
        my_controller.do_something()
        qapp.processEvents()

    # Assert no warnings
    assert not any("unique connections" in w for w in warnings)
    assert not any("Failed to disconnect" in w for w in warnings)
```

---

## CI/CD Integration

### Full Test Suite

```bash
# Run all tests with Qt warning detection enabled
uv run pytest tests/unit/ -n auto --timeout=5

# Or with verbose output
uv run pytest tests/unit/test_qt_signal_warnings.py \
             tests/unit/test_threede_controller_signals.py -v
```

### Quick Validation During Development

```bash
# Check only Qt warning tests (fast feedback)
uv run pytest tests/unit/ -k "warning" -v

# Check specific component
uv run pytest tests/unit/test_threede_controller_signals.py::test_threede_refresh_signals_no_warnings -v
```

---

## What Gets Caught

### ✅ Caught by This System

- **UniqueConnection with Python callables**: Qt flag doesn't work with bound methods
- **Failed disconnections**: Signals not properly connected/tracked
- **Duplicate connections**: Connection tracking bugs
- **Worker cleanup issues**: Signals not disconnected on worker shutdown
- **Cross-thread signal problems**: Incorrect connection types

### ❌ NOT Caught (Still Need Manual Testing)

- **Visual Qt bugs**: QPainter rendering issues, layout problems
- **Signal logic errors**: Wrong slot connected (wrong behavior, no warning)
- **Performance issues**: Slow signal emission (no warning, just slow)
- **Memory leaks**: Undetected until profiling

---

## Common Qt Warnings and What They Mean

| Warning Message | Meaning | Fix |
|----------------|---------|-----|
| `unique connections require a pointer to member function` | Using `UniqueConnection` flag with Python callable | Remove `UniqueConnection` flag, use application-level deduplication |
| `Failed to disconnect (<method>)` | Trying to disconnect signal that was never connected or already disconnected | Check connection tracking, ensure signals are properly connected |
| `QObject::connect: Cannot connect (null)::signal to ...` | Connecting to deleted/null object | Check object lifecycle, use weak references if needed |

---

## Historical Context: The Bug This System Prevented

**Problem**: `ThreadSafeWorker.safe_connect()` used `Qt.ConnectionType.UniqueConnection` flag combined with queued connections:

```python
# WRONG - produces Qt warnings
unique_connection_type = (
    Qt.ConnectionType(connection_type.value | Qt.ConnectionType.UniqueConnection.value)
)
signal.connect(slot, unique_connection_type)
```

**Why it failed**:
- `UniqueConnection` requires C++ member function pointers
- Python bound methods don't have the same identity guarantees
- Qt couldn't determine uniqueness, produced warnings

**Fix**:
```python
# CORRECT - use application-level deduplication
if connection in self._connections:
    return  # Already connected, skip
self._connections.append(connection)
signal.connect(slot, connection_type)  # No UniqueConnection flag
```

**Test that would have caught it**:
```python
def test_safe_connect_produces_no_qt_warnings(qapp):
    # Captures stderr, asserts no "unique connections require" message
    # This test NOW EXISTS and will catch future issues
```

---

## Maintenance

### Adding New Components with Signal Connections

When creating new controllers or workers that use Qt signals:

1. **Add integration test** following `test_threede_controller_signals.py` pattern
2. **Exercise all signal paths**: initialization, operation, cleanup
3. **Run with warning detection**: Verify no Qt warnings produced

### When Tests Fail with Qt Warnings

1. **Check stderr output**: Test output shows exact Qt warning message
2. **Locate source**: Warning message includes file/line information
3. **Common fixes**:
   - Remove `UniqueConnection` flags
   - Fix signal tracking in `safe_connect()`
   - Ensure proper disconnection in cleanup
4. **Verify fix**: Re-run specific test to confirm warning gone

---

## Benefits

- **Early detection**: Catches issues immediately in tests, not runtime
- **Automated**: No manual inspection needed, CI fails automatically
- **Comprehensive**: Three layers catch issues at different levels
- **Maintainable**: Easy to add new tests following established patterns
- **Historical**: Documents bugs and their fixes for future developers

---

## See Also

- `thread_safe_worker.py`: Core signal connection infrastructure
- `controllers/threede_controller.py`: Example controller with proper signal management
- `UNIFIED_TESTING_GUIDE.md`: Overall testing strategy
- `pyproject.toml`: Pytest configuration with warning filters
