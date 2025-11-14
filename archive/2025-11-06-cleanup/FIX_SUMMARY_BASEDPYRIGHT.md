# Basedpyright Error Fix Summary

**Date:** 2025-11-02
**Issue:** 4 critical errors in multiple inheritance
**Status:** ✅ **FIXED**

---

## Problem

After enabling basedpyright standard mode, we encountered 4 errors:

```
/home/gabrielh/projects/shotbot/threede_recovery_dialog.py:34:7 - error:
  Base classes for class "ThreeDERecoveryDialog" define method "closeEvent" in incompatible way
  Parameter 2 mismatch: base parameter "event" is keyword parameter,
  override parameter is position-only (reportIncompatibleMethodOverride)

/home/gabrielh/projects/shotbot/threede_recovery_dialog.py:34:7 - error:
  Base classes for class "ThreeDERecoveryDialog" define method "keyPressEvent" in incompatible way
  Parameter 2 mismatch: base parameter "event" is keyword parameter,
  override parameter is position-only (reportIncompatibleMethodOverride)

# Same 2 errors for ThreeDERecoveryResultDialog at line 279
```

---

## Root Cause

Multiple inheritance with incompatible method signatures:

```python
# threede_recovery_dialog.py
class ThreeDERecoveryDialog(QDialog, QtWidgetMixin, LoggingMixin):
                            #  ^           ^
                            #  |           |
                            #  Both define closeEvent() and keyPressEvent()
                            #  but with different parameter calling conventions
```

**The Issue:**
- `QDialog` (from PySide6) defines methods with **position-only** parameters
- `QtWidgetMixin` had methods with **normal** parameters (can be positional or keyword)
- Type checker detected incompatibility in multiple inheritance

**Example of the mismatch:**
```python
# QDialog (PySide6 C++ binding)
def closeEvent(self, event, /):  # position-only parameter
    pass

# QtWidgetMixin (our code)
def closeEvent(self, event: QCloseEvent):  # normal parameter
    pass

# Result: Incompatible when both are in MRO!
```

---

## Solution

Made `QtWidgetMixin` methods match Qt's signature by using **position-only parameters**:

### File: `qt_widget_mixin.py`

**Before:**
```python
def closeEvent(self, event: QCloseEvent) -> None:
    """Handle close event with cleanup."""
    # ...

def keyPressEvent(self, event: QKeyEvent) -> None:
    """Handle key press events with standard shortcuts."""
    # ...
```

**After:**
```python
def closeEvent(self, event: QCloseEvent, /) -> None:
    """Handle close event with cleanup.

    Args:
        event: Close event (position-only to match Qt signature)
    """
    # ...

def keyPressEvent(self, event: QKeyEvent, /) -> None:
    """Handle key press events with standard shortcuts.

    Args:
        event: Key event (position-only to match Qt signature)
    """
    # ...
```

**Key Change:** Added `/` after the `event` parameter to mark it as **position-only**.

---

## Position-Only Parameters Explained

Python 3.8+ introduced position-only parameters using `/` syntax:

```python
def function(arg1, arg2, /):
    #                    ^
    #                    |
    #          Everything before / is position-only
    pass

# Valid calls:
function(1, 2)

# Invalid calls (raises TypeError):
function(arg1=1, arg2=2)  # ❌ Can't use keyword syntax
```

This matches Qt's C++ API which doesn't support keyword arguments for event handlers.

---

## Why This Matters

### Without the Fix
```python
# Multiple inheritance creates incompatible MRO
class ThreeDERecoveryDialog(QDialog, QtWidgetMixin, LoggingMixin):
    pass

# Type checker error:
# "Methods closeEvent and keyPressEvent have incompatible signatures"
```

### With the Fix
```python
# Both QDialog and QtWidgetMixin now use position-only params
class ThreeDERecoveryDialog(QDialog, QtWidgetMixin, LoggingMixin):
    pass

# Type checker: ✅ Compatible signatures!
```

---

## Verification

### Before Fix
```bash
$ basedpyright
4 errors, 878 warnings, 0 notes
```

### After Fix
```bash
$ basedpyright
0 errors, 878 warnings, 0 notes
```

✅ **All 4 errors resolved!**

---

## Technical Details

### Method Resolution Order (MRO)

For the class:
```python
class ThreeDERecoveryDialog(QDialog, QtWidgetMixin, LoggingMixin):
    pass
```

The MRO is:
1. `ThreeDERecoveryDialog`
2. `QDialog`
3. `QtWidgetMixin`
4. `LoggingMixin`
5. `object`

When `closeEvent()` is called:
1. Looks in `ThreeDERecoveryDialog` (not found)
2. Looks in `QDialog` (found!)
3. But `QtWidgetMixin` also has it - **signatures must match!**

---

## Why Position-Only Parameters?

Qt (written in C++) doesn't support keyword arguments. When PySide6 generates Python bindings, it marks event handler parameters as position-only to match C++ behavior:

```cpp
// C++ (Qt)
void QDialog::closeEvent(QCloseEvent *event) {
    // Parameters in C++ are inherently positional
}
```

```python
# Python binding (PySide6)
def closeEvent(self, event: QCloseEvent, /) -> None:
    # Position-only to match C++ behavior
    pass
```

Our `QtWidgetMixin` needs to match this to be compatible in multiple inheritance.

---

## Other Files Affected

The fix only required changes to **1 file**:
- `qt_widget_mixin.py` - Updated method signatures

**No changes needed** to:
- `threede_recovery_dialog.py` - Automatically compatible after mixin fix
- Any other files using `QtWidgetMixin` - All benefit from the fix

---

## Lessons Learned

### 1. Multiple Inheritance Requires Compatible Signatures

When using multiple inheritance in Python, all base classes that define the same method must have compatible signatures. This includes:
- Parameter names
- Parameter types
- Parameter calling conventions (position-only, normal, keyword-only)
- Return types

### 2. Match Framework Conventions

When creating mixins for framework classes (like Qt), match the framework's parameter conventions exactly. Don't assume normal parameters are safe.

### 3. Type Checkers Find These Issues

Without strict type checking (`standard` or `recommended` mode), this incompatibility would not have been detected until runtime - or worse, could cause subtle bugs in method calls.

### 4. Position-Only Parameters Are Your Friend

For event handlers and callbacks that match C/C++ APIs, using position-only parameters prevents:
- Accidental keyword argument usage
- Signature mismatches in inheritance
- Documentation confusion about calling conventions

---

## Best Practices Going Forward

### For Event Handlers (Qt, etc.)

Always use position-only parameters:
```python
def closeEvent(self, event: QCloseEvent, /) -> None:
    """Handle close event."""
    pass

def keyPressEvent(self, event: QKeyEvent, /) -> None:
    """Handle key press event."""
    pass
```

### For Mixins with Framework Classes

1. Check framework signatures before creating mixin methods
2. Match parameter calling conventions exactly
3. Add docstring notes about why position-only is used
4. Test with type checking enabled

### Example Template

```python
class QtEventMixin:
    """Mixin for Qt event handlers.

    Note: All event methods use position-only parameters (/) to match
    Qt's C++ API calling conventions and ensure compatibility with
    multiple inheritance from QWidget/QDialog classes.
    """

    def closeEvent(self, event: QCloseEvent, /) -> None:
        """Handle close event.

        Args:
            event: Close event (position-only to match Qt)
        """
        pass
```

---

## Testing

To test this fix works:

```bash
# 1. Type checking should pass
~/.local/bin/uv run basedpyright
# Expected: 0 errors

# 2. Run tests to ensure runtime behavior unchanged
~/.local/bin/uv run pytest tests/unit/test_threede_recovery_dialog.py -v
# Expected: All tests pass

# 3. Test multiple inheritance explicitly
python3 << 'EOF'
from threede_recovery_dialog import ThreeDERecoveryDialog
from qt_widget_mixin import QtWidgetMixin
from PySide6.QtWidgets import QDialog

# Check MRO
print("MRO:")
for cls in ThreeDERecoveryDialog.__mro__:
    print(f"  {cls.__name__}")

print("\nMethods:")
print(f"  closeEvent: {ThreeDERecoveryDialog.closeEvent}")
print(f"  keyPressEvent: {ThreeDERecoveryDialog.keyPressEvent}")
EOF
```

---

## Impact

### Files Modified
- `qt_widget_mixin.py` (2 method signatures)

### Lines Changed
- 2 lines (added `/` to parameter lists)
- 4 lines (added docstring explanations)

### Errors Fixed
- 4 critical type checking errors

### Side Benefits
- Better documentation of calling conventions
- More robust multiple inheritance
- Matches Qt conventions more accurately

---

## Related Documentation

- [PEP 570 - Position-Only Parameters](https://peps.python.org/pep-0570/)
- [Qt Event Handling](https://doc.qt.io/qt-6/eventsandfilters.html)
- [Python MRO (Method Resolution Order)](https://www.python.org/download/releases/2.3/mro/)
- [PySide6 QCloseEvent](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QCloseEvent.html)

---

**Fix completed:** 2025-11-02
**Verified by:** basedpyright type checking
**Status:** ✅ Production ready
