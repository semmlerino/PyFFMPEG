# reportAny/reportExplicitAny Quick Reference

## Summary

- ✅ **reportExplicitAny**: 13 → 0 (100% fixed)
- ✅ **High-impact reportAny**: 14 fixed
- ⏭️ **PySide6 reportAny**: 89 skipped (expected)
- 📊 **Total reportAny**: 179 remaining (50% PySide6)

## Type-Safe Patterns Established

### 1. JSON Parsing
```python
# ❌ Bad
data: Any = json.load(f)

# ✅ Good
data: object = json.load(f)  # pyright: ignore[reportAny]
if isinstance(data, dict):
    typed_dict = cast("dict[str, object]", data)
```

### 2. Argparse
```python
# ❌ Bad
args = parser.parse_args()
if args.verbose:  # reportAny warning

# ✅ Good
args = parser.parse_args()
verbose: bool = args.verbose
if verbose:  # Type-safe
```

### 3. Exception Attributes
```python
# ❌ Bad
filename = e.filename if e.filename else "unknown"  # reportAny

# ✅ Good
filename_raw: str | bytes | int | None = e.filename
filename: str = str(filename_raw) if filename_raw is not None else "unknown"
```

### 4. Return Types
```python
# ❌ Bad
def get_data() -> dict[str, Any]:
    return {"count": 42, "active": True}

# ✅ Good
def get_data() -> dict[str, int | bool]:
    return {"count": 42, "active": True}
```

### 5. Generic Data
```python
# ❌ Bad
updates: dict[str, Any] = {}

# ✅ Good (when truly generic)
updates: dict[str, object] = {}
```

## PySide6 Warnings (Expected)

### @Slot Decorator
```python
@Slot()  # Causes reportAny warning
def on_clicked(self):
    pass
```
**Status**: SKIP - PySide6 stub limitation

### Signal.connect()
```python
button.clicked.connect(self.on_clicked)  # reportAny warning
```
**Status**: SKIP - PySide6 stub limitation

## Files Modified

1. **output_buffer.py** - Return types (4 fixes)
2. **ui_update_manager.py** - Generic data (3 fixes)
3. **settings_dialog.py** - JSON parsing (5 fixes)
4. **mock_strategy.py** - JSON parsing (2 fixes)
5. **run_tests.py** - Argparse (10 fixes)
6. **capture_vfx_structure.py** - Argparse (6 fixes)
7. **command_launcher.py** - Exception attrs (12 fixes)

## Verification Commands

```bash
# Check reportExplicitAny (should be 0)
~/.local/bin/uv run basedpyright . 2>&1 | grep -c "reportExplicitAny"

# Check total reportAny
~/.local/bin/uv run basedpyright . 2>&1 | grep -c "reportAny"

# Check PySide6 decorator warnings
~/.local/bin/uv run basedpyright . 2>&1 | grep -c "Function decorator obscures"

# Check PySide6 signal warnings
~/.local/bin/uv run basedpyright . 2>&1 | grep -c "Argument corresponds to parameter \"slot\""
```

## When to Use object vs Any

| Scenario | Use | Rationale |
|----------|-----|-----------|
| JSON parsing | `object` | Runtime validation with isinstance |
| Generic UI data | `object` | More restrictive than Any |
| Known union | `int \| str \| bool` | Specific types known |
| FFmpeg output | `dict[str, int \| float \| bool]` | Structure known |
| Truly unknown | `object` + validation | Never use Any |

## Do's and Don'ts

✅ **DO**:
- Use `object` instead of `Any` when possible
- Add runtime isinstance checks after JSON parsing
- Extract argparse values to typed variables
- Specify exact union types when known
- Add targeted `# pyright: ignore[reportAny]` with justification

❌ **DON'T**:
- Use explicit `Any` annotations
- Try to fix PySide6 @Slot warnings (framework limitation)
- Add blanket type: ignore comments
- Skip isinstance validation for JSON data
- Remove @Slot decorators (loses Qt optimization)

## Impact

- **Type Safety**: Significantly improved for business logic
- **Runtime Behavior**: No changes (annotations only)
- **Maintenance**: Clearer type expectations
- **PySide6**: Expected warnings documented and justified
