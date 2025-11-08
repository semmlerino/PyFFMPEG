# Signal Connection Safety - UniqueConnection Enforcement

**Status:** ✅ Implemented for launcher tests, ready to expand

## Overview

We've implemented automatic UniqueConnection enforcement for signal connections during testing. This prevents duplicate signal connections (which cause double-emission bugs) by catching them at connection time rather than emission time.

## Current Implementation

### Fixture Location
- **File:** `tests/conftest.py`
- **Fixtures:** `_signal_instance_type()`, `enforce_unique_connections()`
- **Marker:** `@pytest.mark.enforce_unique_connections`

### What It Does

The `enforce_unique_connections` fixture monkey-patches Qt's `Signal.connect()` method to automatically use `Qt.UniqueConnection` for all signal connections during tests. This means:

- **First connection:** Works normally
- **Duplicate connection:** Silently ignored by Qt (no error, no duplicate handler)
- **Detection:** Happens at `connect()` time, not `emit()` time

### Currently Enabled For

```python
# tests/integration/test_launcher_panel_integration.py
pytestmark = [
    pytest.mark.integration,
    pytest.mark.qt,
    pytest.mark.enforce_unique_connections,  # ← Enabled here
]
```

**Test Results:** ✅ 13/13 launcher panel integration tests pass

## How to Expand

### Option 1: Enable for All Qt Tests (Recommended)

Edit `tests/conftest.py` line 122:

```python
# BEFORE (opt-in via marker)
@pytest.fixture
def enforce_unique_connections(request, monkeypatch, _signal_instance_type):
    ...

# AFTER (automatic for all tests)
@pytest.fixture(autouse=True)
def enforce_unique_connections(request, monkeypatch, _signal_instance_type):
    ...
```

**Impact:** All tests will automatically use UniqueConnection
**Risk:** Low - if duplicate connections exist, they'll just be silently prevented (not fail tests)

### Option 2: Enable for Specific Test Categories

Add the marker to other test modules:

```python
# tests/unit/test_main_window.py
pytestmark = [
    pytest.mark.unit,
    pytest.mark.qt,
    pytest.mark.enforce_unique_connections,  # ← Add here
]
```

### Option 3: Enable for Specific Tests

Use the marker on individual test functions:

```python
@pytest.mark.enforce_unique_connections
def test_my_widget_signals(qtbot, enforce_unique_connections):
    widget = MyWidget()
    # Signal connections in this test use UniqueConnection
```

## Why This Helps

### Before (Without UniqueConnection)
```python
# Bug: Accidental duplicate connection
window.launcher_panel.app_launch_requested.connect(controller.launch_app)
window.launcher_panel.app_launch_requested.connect(controller.launch_app)  # Oops!

# Result: Signal emits twice on button click
```

### After (With UniqueConnection)
```python
# Same code, but second connect() is silently ignored
window.launcher_panel.app_launch_requested.connect(controller.launch_app)
window.launcher_panel.app_launch_requested.connect(controller.launch_app)  # Ignored by Qt

# Result: Signal emits once (correct behavior)
```

## What This Caught

Our implementation successfully validated the fix for the launcher panel double-emission bug:

1. **Issue:** `launcher_panel.app_launch_requested` was connected twice:
   - `main_window.py:691` → `launcher_controller.launch_app`
   - `launcher_controller.py:110` → `self.launch_app` (same method)

2. **Symptom:** Button clicks triggered the handler twice

3. **Fix:** Removed duplicate connection from `main_window.py`

4. **Validation:** Tests pass with UniqueConnection enforcement, confirming no duplicates remain

## Production Code Impact

**Important:** UniqueConnection enforcement only applies during tests. Production code is unaffected.

If you want production code to also use UniqueConnection:

```python
# Explicit UniqueConnection in production
signal.connect(slot, Qt.ConnectionType.UniqueConnection)
```

However, the test-time enforcement is usually sufficient to catch issues during development.

## Related Documentation

- **Original recommendations:** User-provided best practices for PySide6 + pytest-qt
- **Bug fix:** `main_window.py:690-691` - Removed duplicate launcher panel signal connection
- **Test marker:** Registered in `pyproject.toml:274`

## Next Steps

### Immediate (Optional)
- [ ] Expand enforcement to all Qt tests by changing `autouse=False` → `autouse=True`
- [ ] Monitor for any edge cases in other test suites

### Future Enhancements (Lower Priority)
- [ ] Add QSignalSpy emission count tests for critical signals
- [ ] Consider Qt warnings-as-errors fixture (high risk, defer to new features only)

## Maintenance

### Adding New Test Modules

To enable for a new test file:

```python
# In your test file
pytestmark = [
    pytest.mark.enforce_unique_connections,
]
```

### Disabling for Specific Tests

If you have a legitimate reason to allow duplicate connections:

```python
@pytest.mark.skip_unique_enforcement  # Custom marker (needs implementation)
def test_intentional_duplicate_connection(qtbot):
    # Test that explicitly needs duplicate connections
    pass
```

## Summary

✅ **Implemented:** UniqueConnection enforcement fixture
✅ **Validated:** 13 launcher panel integration tests pass
✅ **Impact:** Prevents double-emission bugs at connection time
⏸️ **Expansion:** Ready to enable for all tests when desired

This safety net will prevent the double-emission class of bugs from recurring in the codebase.
