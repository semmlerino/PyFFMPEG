# Launcher System Error Handling Guide

## Current Pattern (As-Is)

The launcher system currently uses a **hybrid error handling pattern** combining:
1. **Qt Signals** for error notification to UI
2. **None returns** for operation failures
3. **Exceptions** for exceptional cases

### Pattern Usage

#### LauncherManager Methods

**Create/Update/Delete Operations:**
```python
# Returns: str (launcher_id) on success, None on failure
# Emits: validation_error signal with error details
launcher_id = launcher_manager.create_launcher(launcher_config)
if launcher_id is None:
    # Check validation_error signal for details
    # Error was already emitted to connected UI handlers
```

**Execute Operations:**
```python
# Returns: bool (True on success, False on failure)
# Emits: execution_started, execution_finished, command_error signals
success = launcher_manager.execute_in_shot_context(launcher_id, shot)
if not success:
    # Check command_error signal for details
```

#### Signal Connections

**Validation Errors (synchronous):**
```python
launcher_manager.validation_error.connect(self._on_validation_error)

def _on_validation_error(self, field: str, message: str) -> None:
    # Handle validation error
    QMessageBox.warning(self, "Validation Error", f"{field}: {message}")
```

**Execution Errors (asynchronous):**
```python
launcher_manager.command_error.connect(self._on_command_error)

def _on_command_error(self, launcher_id: str, error: str) -> None:
    # Handle execution error
    self.log_viewer.add_error(error)
```

## Recommended Pattern (Future)

For new code, use the **Result pattern** defined in `launcher/result_types.py`:

```python
from launcher.result_types import Result, LauncherCreationResult

def create_launcher_v2(self, launcher: CustomLauncher) -> LauncherCreationResult:
    """Create launcher (v2 with Result pattern).

    Returns:
        Result[str] containing launcher_id on success, errors on failure
    """
    # Validate
    valid, errors = self._validator.validate(launcher)
    if not valid:
        return Result.fail(*errors)

    # Create
    if not self._repository.create(launcher):
        return Result.fail("Failed to save launcher configuration")

    return Result.ok(launcher.id)
```

**Usage:**
```python
result = launcher_manager.create_launcher_v2(launcher_config)
if result:  # Result.__bool__ returns result.success
    launcher_id = result.value
    print(f"Created launcher: {launcher_id}")
else:
    for error in result.errors:
        print(f"Error: {error}")
```

## Error Handling Decision Tree

```
Is this an expected business logic failure?
├─ YES: Use Result pattern (new code) or None + signal (existing code)
│   └─ Examples: Validation failure, launcher not found, command whitelist violation
│
└─ NO: Is this a recoverable error?
    ├─ YES: Use Exception and let caller handle
    │   └─ Examples: Timeout, network error, disk full
    │
    └─ NO: Let it crash (unrecoverable system error)
        └─ Examples: Out of memory, corrupted data structures
```

## Qt Signal Best Practices

### DO ✅
- Use signals for **async notification** to UI
- Use signals for **broadcast events** (multiple listeners)
- Connect signals with `Qt.QueuedConnection` for cross-thread safety

### DON'T ❌
- Use signals for **error propagation** in synchronous calls
- Use signals as **return values** (return data directly instead)
- Mix signal emissions with None returns (causes confusion)

## Migration Strategy

To migrate from current pattern to Result pattern:

1. **Phase 1: Document** (✅ This file)
   - Document current pattern
   - Define future pattern
   - Provide examples

2. **Phase 2: Coexist** (New code only)
   - New methods use Result pattern
   - Old methods keep signal pattern
   - Mark old methods with `# TODO: Migrate to Result pattern`

3. **Phase 3: Migrate** (Breaking change - major version)
   - Update all launcher methods to use Result
   - Remove validation_error signals (redundant with Result.errors)
   - Keep execution signals for async notifications

## Example Refactor

**Before (Current):**
```python
def create_launcher(self, launcher: CustomLauncher) -> str | None:
    valid, errors = self._validator.validate(launcher)
    if not valid:
        for error in errors:
            self.validation_error.emit("general", error)
        return None

    if not self._repository.create(launcher):
        self.validation_error.emit("general", "Failed to save")
        return None

    self.launcher_added.emit(launcher.id)
    return launcher.id
```

**After (Result pattern):**
```python
def create_launcher(self, launcher: CustomLauncher) -> LauncherCreationResult:
    valid, errors = self._validator.validate(launcher)
    if not valid:
        return Result.fail(*errors)

    if not self._repository.create(launcher):
        return Result.fail("Failed to save launcher configuration")

    self.launcher_added.emit(launcher.id)
    return Result.ok(launcher.id)
```

**Caller update:**
```python
# Before
launcher_id = launcher_manager.create_launcher(config)
if launcher_id is None:
    # Error already shown via signal connection
    return

# After
result = launcher_manager.create_launcher(config)
if not result:
    for error in result.errors:
        QMessageBox.warning(self, "Error", error)
    return
launcher_id = result.value
```

## Summary

- **Current code:** Keep using signal + None pattern, ensure proper signal connections
- **New code:** Use Result pattern from `launcher/result_types.py`
- **Exceptions:** Reserve for truly exceptional errors, not business logic failures
- **Signals:** Use for async UI updates, not error propagation in sync methods
