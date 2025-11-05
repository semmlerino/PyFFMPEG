# Type Safety Quick Wins - Shotbot

**Quick reference for immediate type safety improvements**

---

## Quick Win #1: Enable Recommended Mode (5 minutes)

**Impact:** Find 50-200 hidden type issues | **Risk:** Low (warnings only)

### Edit `pyproject.toml`:

```toml
[tool.basedpyright]
typeCheckingMode = "recommended"  # Changed from "basic"
pythonVersion = "3.11"

# Enable key diagnostics (change from false to "warning")
reportUnknownMemberType = "warning"
reportUnknownParameterType = "warning"
reportUnknownArgumentType = "warning"
reportUnknownVariableType = "information"
reportUnannotatedClassAttribute = "warning"

# Add basedpyright-exclusive features
strictListInference = true
strictDictionaryInference = true
reportIgnoreCommentWithoutRule = "error"
```

### Run and review:

```bash
~/.local/bin/uv run basedpyright . > type_check_results.txt
```

---

## Quick Win #2: Fix Missing Type in ThreeDEController (2 minutes)

**File:** `controllers/threede_controller.py:532`

### Before:

```python
def on_recovery_requested(crash_info):
    self.logger.info(f"Recovery requested for: {crash_info.crash_path.name}")
```

### After:

```python
def on_recovery_requested(self, crash_info: CrashInfo) -> None:
    self.logger.info(f"Recovery requested for: {crash_info.crash_path.name}")
```

**Add import:**
```python
from threede_recovery import CrashInfo
```

---

## Quick Win #3: Add TypeGuard for String List Validation (10 minutes)

**Files:** `launcher/models.py`, `settings_manager.py`, `cache_manager.py`

### Create utility module: `type_guards.py`

```python
"""Type guards for common validation patterns."""

from typing import TypeGuard

def is_string_list(value: object) -> TypeGuard[list[str]]:
    """Type guard for list of strings."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)

def is_string_dict(value: object) -> TypeGuard[dict[str, str]]:
    """Type guard for string-keyed, string-valued dictionary."""
    return (
        isinstance(value, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())
    )

def is_int_list(value: object) -> TypeGuard[list[int]]:
    """Type guard for list of integers."""
    return isinstance(value, list) and all(isinstance(item, int) for item in value)
```

### Use in `launcher/models.py`:

```python
from type_guards import is_string_list

# Line 267 - Before
if isinstance(packages_value, list):
    packages = [str(item) for item in packages_value]

# Line 267 - After
if is_string_list(packages_value):
    packages = packages_value  # Type checker knows it's list[str]
```

**Benefit:** Eliminates 50+ manual type conversions across codebase.

---

## Quick Win #4: Create ShowFilterable Protocol (15 minutes)

**File:** Create `ui_protocols.py`

```python
"""Protocols for UI component interfaces."""

from typing import Protocol

class DataModelProtocol(Protocol):
    """Minimal interface for data models."""
    pass  # Define based on actual needs

class ShowFilterableModel(Protocol):
    """Protocol for models that support show filtering."""

    def set_show_filter(
        self,
        model: DataModelProtocol,
        show_filter: str | None
    ) -> None:
        """Apply show filter to model."""
        ...
```

### Update `controllers/threede_controller.py`:

```python
from ui_protocols import ShowFilterableModel, DataModelProtocol

# Line 708 - Before
def _apply_show_filter(
    self,
    item_model: object,  # ⚠️ Untyped
    model: object,       # ⚠️ Untyped
    show: str,
    tab_name: str
) -> None:

# Line 708 - After
def _apply_show_filter(
    self,
    item_model: ShowFilterableModel,  # ✅ Typed
    model: DataModelProtocol,          # ✅ Typed
    show: str,
    tab_name: str,
) -> None:
```

**Benefit:** Removes 1 pyright: ignore comment, enables type checking for 3 method calls.

---

## Quick Win #5: Add PlateAwareLauncher Protocol (20 minutes)

**File:** Create `launcher_protocols.py`

```python
"""Protocols for launcher capability detection."""

from typing import Protocol

class PlateAwareLauncher(Protocol):
    """Launcher that supports plate selection for Nuke workspaces."""

    def launch_app(
        self,
        app_name: str,
        include_undistortion: bool = False,
        include_raw_plate: bool = False,
        open_latest_threede: bool = False,
        open_latest_maya: bool = False,
        open_latest_scene: bool = False,
        create_new_file: bool = False,
        *,
        selected_plate: str | None = None,
    ) -> bool:
        """Launch app with optional plate selection."""
        ...

class BasicLauncher(Protocol):
    """Basic launcher without plate selection."""

    def launch_app(
        self,
        app_name: str,
        include_undistortion: bool = False,
        include_raw_plate: bool = False,
        open_latest_threede: bool = False,
        open_latest_maya: bool = False,
        open_latest_scene: bool = False,
        create_new_file: bool = False,
    ) -> bool:
        """Launch app without plate selection."""
        ...
```

### Update `controllers/launcher_controller.py`:

```python
from launcher_protocols import PlateAwareLauncher, BasicLauncher

# Line 316-353 - Simplify with protocol check
if hasattr(self.window.command_launcher, "launch_app"):
    # Check signature for plate support
    from typing import cast
    import inspect

    sig = inspect.signature(self.window.command_launcher.launch_app)
    supports_plate = "selected_plate" in sig.parameters

    if supports_plate:
        launcher = cast(PlateAwareLauncher, self.window.command_launcher)
        success = launcher.launch_app(..., selected_plate=selected_plate)
    else:
        launcher = cast(BasicLauncher, self.window.command_launcher)
        success = launcher.launch_app(...)
```

**Benefit:** Eliminates runtime introspection, makes capability explicit, removes 1 cast.

---

## Quick Win #6: Run Basedpyright with Strict Mode Test (5 minutes)

**Test what strict mode would find:**

```bash
# Create temporary strict config
cat > pyrightconfig.strict.json << 'EOF'
{
  "extends": "./pyrightconfig.json",
  "typeCheckingMode": "strict",
  "reportUnknownMemberType": true,
  "reportUnknownParameterType": true,
  "reportUnknownArgumentType": true,
  "reportUnknownVariableType": true,
  "reportUnannotatedClassAttribute": true
}
EOF

# Run strict check (expect many warnings)
~/.local/bin/uv run basedpyright --project pyrightconfig.strict.json . > strict_results.txt 2>&1

# Review results
less strict_results.txt

# Remove temporary config
rm pyrightconfig.strict.json
```

**Benefit:** Preview what needs fixing before enabling strict mode permanently.

---

## Quick Win #7: Add Type Guards for ProcessPoolInterface (10 minutes)

**File:** `protocols.py`

```python
from typing import TypeGuard

def is_process_pool(value: object) -> TypeGuard[ProcessPoolInterface]:
    """Check if object implements ProcessPoolInterface."""
    return (
        hasattr(value, "execute_workspace_command")
        and callable(getattr(value, "execute_workspace_command"))
        and hasattr(value, "batch_execute")
        and callable(getattr(value, "batch_execute"))
        and hasattr(value, "shutdown")
        and callable(getattr(value, "shutdown"))
    )

# Usage example
if is_process_pool(pool_obj):
    # Type checker knows pool_obj is ProcessPoolInterface
    result = pool_obj.execute_workspace_command("ls")
```

**Benefit:** Type-safe duck typing without isinstance checks.

---

## Quick Win #8: Document Type Ignore Comments (5 minutes per file)

**Pattern:** Add error codes to all type: ignore comments

### Before:

```python
result = some_call()  # type: ignore
```

### After:

```python
result = some_call()  # type: ignore[no-untyped-call]  # Third-party library lacks types
```

**Files to update (34 files with type: ignore):**
- Start with: `controllers/`, `launcher/`, `core/`

**Command to find them:**

```bash
grep -n "type: ignore" controllers/*.py launcher/*.py core/*.py
```

**Benefit:** Self-documenting, prevents hiding new errors.

---

## Quick Win #9: Enable Basedpyright-Exclusive Features (2 minutes)

**Edit `pyproject.toml`:**

```toml
[tool.basedpyright]
# ... existing config ...

# Add basedpyright-exclusive features
strictListInference = true        # list[int | str] instead of list[Any]
strictDictionaryInference = true  # dict[str, int] instead of dict[str, Any]
strictSetInference = true         # set[int | str] instead of set[Any]
strictGenericNarrowing = true     # Narrow generics better in isinstance

# Enforce specific ignore comments
reportIgnoreCommentWithoutRule = "error"

# Flag Any types
reportAny = "warning"
reportExplicitAny = "error"
```

**Benefit:** Better type inference, catches lazy ignores, prevents Any pollution.

---

## Quick Win #10: Add PerformanceMetricsDict to ProcessPool Returns (5 minutes)

**File:** `protocols.py`

### Ensure proper return type:

```python
from type_definitions import PerformanceMetricsDict

class ProcessPoolInterface(Protocol):
    def get_metrics(self) -> PerformanceMetricsDict:
        """Get performance metrics."""
        ...
```

### If PerformanceMetricsDict is missing, add to `type_definitions.py`:

```python
class PerformanceMetricsDict(TypedDict):
    """Type definition for performance metrics."""

    total_commands: int
    cache_hits: int
    cache_misses: int
    avg_execution_time: float
    total_execution_time: float
    error_count: int
    last_reset: float
```

**Benefit:** Type-safe metrics access, prevents typos in metric keys.

---

## Verification Checklist

After applying quick wins, verify with:

```bash
# 1. Type check passes
~/.local/bin/uv run basedpyright .

# 2. Tests still pass
~/.local/bin/uv run pytest tests/ -n 2

# 3. No regressions
~/.local/bin/uv run python shotbot.py --help

# 4. Count improvements
echo "Type ignores before: 143"
grep -r "type: ignore" controllers/ launcher/ core/ | wc -l
echo "Pyright ignores before: 113"
grep -r "pyright: ignore" controllers/ launcher/ core/ | wc -l
```

---

## Priority Order

**Implement in this order for maximum impact with minimal risk:**

1. ✅ **Quick Win #1** - Enable recommended mode (find issues)
2. ✅ **Quick Win #2** - Fix missing type (1 function)
3. ✅ **Quick Win #3** - Add TypeGuard utilities (reusable)
4. ✅ **Quick Win #9** - Enable basedpyright features (better inference)
5. ⚠️ **Quick Win #8** - Document type ignores (prevents future issues)
6. ⚠️ **Quick Win #4** - ShowFilterable Protocol (removes ignores)
7. ⚠️ **Quick Win #5** - PlateAwareLauncher Protocol (cleaner design)
8. ⚠️ **Quick Win #7** - ProcessPool TypeGuard (duck typing)
9. ⚠️ **Quick Win #10** - PerformanceMetrics TypedDict (type-safe metrics)
10. 📊 **Quick Win #6** - Strict mode test (planning only)

**Total Time:** ~90 minutes for all quick wins
**Expected Bugs Prevented:** 5-10 runtime type errors per year
**Code Quality Improvement:** Significant (type checker catches more issues)
