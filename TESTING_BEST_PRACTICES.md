# Testing Best Practices for ShotBot

## Executive Summary

This document outlines best practices for maintaining and running the ShotBot test suite, based on Phase 3A fixes that resolved test isolation issues and enabled efficient parallel test execution.

## Key Principles

1. **Test What Exists**: Tests must match the actual implementation, not imagined interfaces
2. **Avoid Anti-patterns**: No `time.sleep()` or `QApplication.processEvents()` in tests
3. **Test Isolation**: Tests must not share state or depend on execution order
4. **Parallel Safety**: Qt tests require special handling for parallel execution

## Running Tests

### Quick Validation
```bash
~/.local/bin/uv run python tests/utilities/quick_test.py
```

### Serial Execution (slower but reliable)
```bash
~/.local/bin/uv run pytest tests/ -p no:xdist
```

### Parallel Execution (faster but requires proper markers)
```bash
~/.local/bin/uv run pytest tests/  # Uses -n auto from pytest.ini
```

### Specific Test Categories
```bash
# Unit tests only
~/.local/bin/uv run pytest tests/unit/

# Integration tests
~/.local/bin/uv run pytest tests/integration/

# Fast tests (<100ms)
~/.local/bin/uv run pytest tests/ -m fast

# Qt tests (run serially for stability)
~/.local/bin/uv run pytest tests/ -m qt -p no:xdist
```

## Anti-Pattern Replacements

### ❌ DON'T: Use time.sleep()
```python
# WRONG - blocks parallel execution
time.sleep(0.1)
```

### ✅ DO: Use synchronization helpers
```python
# RIGHT - non-blocking simulation
from tests.helpers.synchronization import simulate_work_without_sleep
simulate_work_without_sleep(100)  # milliseconds
```

### ❌ DON'T: Use QApplication.processEvents()
```python
# WRONG - causes race conditions
app.processEvents()
```

### ✅ DO: Use process_qt_events()
```python
# RIGHT - thread-safe event processing
from tests.helpers.synchronization import process_qt_events
process_qt_events(app, 10)  # milliseconds
```

### ❌ DON'T: Use bare waits
```python
# WRONG - unreliable timing
widget.do_something()
time.sleep(1)
assert widget.is_done
```

### ✅ DO: Use condition-based waiting
```python
# RIGHT - waits only as long as needed
from tests.helpers.synchronization import wait_for_condition
widget.do_something()
wait_for_condition(lambda: widget.is_done, timeout_ms=1000)
```

## Test Markers for Parallel Execution

### Required Markers for Qt Tests
```python
pytestmark = [
    pytest.mark.unit,
    pytest.mark.qt,
    pytest.mark.xdist_group("qt_state")  # CRITICAL for parallel safety
]
```

The `xdist_group` marker ensures Qt tests that share QApplication state run in the same worker, preventing crashes and race conditions.

### Available Markers
- `fast`: Tests completing in <100ms
- `slow`: Tests taking >1s
- `unit`: Unit tests
- `integration`: Integration tests
- `qt`: Tests requiring Qt event loop
- `gui`: GUI tests requiring display
- `gui_mainwindow`: Tests creating MainWindow (must be serialized)
- `xdist_group(name)`: Tests that must run in same worker

## GUI Popup Prevention

### Automatic Popup Prevention
Tests run with comprehensive popup prevention implemented at module import time in `conftest.py`:

1. **Offscreen Qt Platform**: Set before any Qt imports
```python
os.environ["QT_QPA_PLATFORM"] = "offscreen"
```

2. **Complete Widget Show Prevention**: All Qt show/visibility methods are patched
```python
# Virtual visibility tracking for tests
_virtually_visible_widgets = set()

# Patched methods:
QWidget.show = _mock_widget_show         # Prevents actual display
QWidget.hide = _mock_widget_hide         # Manages virtual visibility
QWidget.setVisible = _mock_widget_setVisible
QWidget.isVisible = _mock_widget_isVisible  # Returns virtual state
QMainWindow.show = _mock_widget_show
QDialog.exec = _mock_dialog_exec         # Returns without blocking
QEventLoop.exec = _mock_eventloop_exec   # Processes events without blocking
```

3. **QRunnable Signal Support**: Event loop mock processes events properly
```python
def _mock_eventloop_exec(self):
    """Process events for QThreadPool signals without blocking."""
    # Processes events for up to 100ms
    # Allows QRunnable signals to propagate from worker threads
    # Calls QCoreApplication.sendPostedEvents() for deferred deletions
```

### Best Practices for Qt Widget Tests
- **DON'T** call `widget.show()` in tests - it's not needed
- **DO** use `qtbot.addWidget(widget)` for proper lifecycle management
- **DON'T** use `QMessageBox` directly - it's automatically mocked
- **DO** trust that widgets are testable without being visible

### Testing Widget Visibility
```python
# CORRECT - Test visibility state without showing
widget = MyWidget()
qtbot.addWidget(widget)  # Manages lifecycle
assert not widget.isVisible()  # Initially hidden
widget.setVisible(True)  # Set state without actual popup
assert widget.isVisible()  # State changed

# WRONG - Attempting to show actual window
widget = MyWidget()
widget.show()  # Don't do this - automatically prevented anyway
```

## Common Issues and Solutions

### Issue: Tests Pass Individually but Fail in Parallel
**Cause**: Test isolation problems - tests share state
**Solution**: Add `pytest.mark.xdist_group("shared_state")` to related tests

### Issue: AttributeError with Mock Objects
**Cause**: Mock missing required attributes
**Solution**: Ensure mocks include all class-level attributes:
```python
MockProcessPoolManagerClass = type(
    "MockProcessPoolManager",
    (),
    {
        "_instance": None,
        "_lock": QMutex(),
        "_initialized": False,  # Don't forget class attributes!
        "get_instance": staticmethod(lambda: test_pool),
    },
)
```

### Issue: Qt Tests Crashing with xdist
**Cause**: Multiple workers trying to create QApplication
**Solution**: Mark all Qt tests with same xdist_group

### Issue: Tests Testing Non-Existent Methods
**Cause**: Tests written for different implementation
**Solution**: Skip or rewrite to match actual code:
```python
def test_old_implementation(self):
    """Test for old widget-based implementation."""
    pytest.skip("ThreeDEGridView uses Model/View architecture")
```

## Synchronization Helper Reference

Available in `tests/helpers/synchronization.py`:

```python
# Simulate work without blocking
simulate_work_without_sleep(duration_ms: int)

# Wait for condition with timeout
wait_for_condition(
    condition: Callable[[], bool],
    timeout_ms: int = 1000,
    poll_interval_ms: int = 10
) -> bool

# Process Qt events safely
process_qt_events(app: QApplication, duration_ms: int = 10)

# Wait for Qt signal
wait_for_qt_signal(
    qtbot,
    signal,
    timeout: int = 1000,
    raising: bool = True
)
```

## Configuration

### pytest.ini Settings
```ini
[pytest]
addopts =
    # Enable parallel by default
    -n auto

    # Use loadgroup distribution for marked tests
    --dist=loadgroup

    # Show test durations
    --durations=20

    # Stop after 5 failures
    --maxfail=5
```

To disable parallel execution temporarily:
```bash
# Command line override
~/.local/bin/uv run pytest -p no:xdist

# Or edit pytest.ini and comment out:
# -n auto
# --dist=loadgroup
```

## Best Practices Summary

1. **Always use synchronization helpers** instead of sleep/processEvents
2. **Mark Qt tests with xdist_group** for parallel safety
3. **Test actual implementation**, not imagined interfaces
4. **Skip broken tests** with clear explanations rather than leaving them failing
5. **Run tests frequently** during development to catch issues early
6. **Use parallel execution** for faster feedback, serial for debugging
7. **Keep tests isolated** - no shared state between tests
8. **Fix the root cause** - don't patch over test failures

## Maintenance Guidelines

### When Adding New Tests
1. Check if testing actual implementation
2. Add appropriate markers (qt, unit, slow, etc.)
3. Use synchronization helpers for timing
4. Ensure test isolation
5. Run both serial and parallel to verify

### When Tests Fail
1. Run individually to check for isolation issues
2. Check for missing mock attributes
3. Verify testing actual implementation
4. Look for anti-patterns (sleep, processEvents)
5. Add xdist_group if Qt state is shared

### When Refactoring Code
1. Update tests to match new implementation
2. Skip obsolete tests with explanations
3. Don't test implementation details
4. Focus on behavior, not structure

---

**Last Updated**: 2025-10-28
**Comprehensive test suite with best practices for parallel execution and Qt testing**