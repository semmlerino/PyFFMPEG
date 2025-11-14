# Type Safety Improvement Examples - Shotbot

**Concrete before/after examples showing type safety improvements**

---

## Example 1: Type Guards for JSON Validation

### Current Code (cache_manager.py, line 103)

```python
def _shot_to_dict(shot: Shot | ShotDict) -> ShotDict:
    """Convert Shot object or ShotDict to ShotDict."""
    if isinstance(shot, dict):
        return shot  # Type checker doesn't know this is ShotDict
    return shot.to_dict()
```

**Issue:** Type checker sees `dict` not `ShotDict` - unsafe operations could pass.

### Improved Code with TypeGuard

```python
from typing import TypeGuard

def is_shot_dict(value: object) -> TypeGuard[ShotDict]:
    """Type guard for ShotDict validation."""
    return (
        isinstance(value, dict)
        and all(key in value for key in ["show", "sequence", "shot", "workspace_path"])
        and isinstance(value.get("show"), str)
        and isinstance(value.get("sequence"), str)
        and isinstance(value.get("shot"), str)
        and isinstance(value.get("workspace_path"), str)
    )

def _shot_to_dict(shot: Shot | ShotDict) -> ShotDict:
    """Convert Shot object or ShotDict to ShotDict."""
    if is_shot_dict(shot):
        return shot  # ✅ Type checker knows this is ShotDict
    return shot.to_dict()
```

**Benefits:**
- Type checker validates ShotDict structure
- Runtime validation catches malformed data
- Self-documenting validation logic

---

## Example 2: Protocol for Generic UI Models

### Current Code (controllers/threede_controller.py, line 708)

```python
def _apply_show_filter(
    self,
    item_model: object,  # ⚠️ Any object accepted
    model: object,       # ⚠️ Any object accepted
    show: str,
    tab_name: str
) -> None:
    """Generic show filter handler for all tabs."""
    show_filter = show if show else None
    # Type checker cannot validate this call
    item_model.set_show_filter(model, show_filter)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

    self.logger.info(
        f"Applied {tab_name} show filter: {show if show else 'All Shows'}"
    )
```

**Issues:**
1. Type checker cannot validate method existence
2. Type checker cannot validate method signature
3. Requires pyright: ignore comment
4. No IDE autocomplete support

### Improved Code with Protocols

```python
# Create ui_protocols.py
from typing import Protocol

class DataModelProtocol(Protocol):
    """Protocol for data models used in filtering."""
    # Add common interface methods here
    pass

class ShowFilterableModel(Protocol):
    """Protocol for item models that support show filtering."""

    def set_show_filter(
        self,
        model: DataModelProtocol,
        show_filter: str | None
    ) -> None:
        """Apply show filter to the model."""
        ...

# Update threede_controller.py
from ui_protocols import ShowFilterableModel, DataModelProtocol

def _apply_show_filter(
    self,
    item_model: ShowFilterableModel,  # ✅ Typed protocol
    model: DataModelProtocol,          # ✅ Typed protocol
    show: str,
    tab_name: str,
) -> None:
    """Generic show filter handler for all tabs."""
    show_filter = show if show else None
    # ✅ Type checker validates this call
    item_model.set_show_filter(model, show_filter)

    self.logger.info(
        f"Applied {tab_name} show filter: {show if show else 'All Shows'}"
    )
```

**Benefits:**
- Removes pyright: ignore comment
- Type checker validates method call
- IDE provides autocomplete
- Clear interface documentation
- Compile-time error if protocol not satisfied

---

## Example 3: Capability-Based Protocols Instead of cast()

### Current Code (controllers/launcher_controller.py, line 316-353)

```python
# Type-safe launch handling for union type (CommandLauncher | SimplifiedLauncher)
# Check if launcher supports selected_plate parameter using inspect
import inspect
from collections.abc import Callable as CallableABC

launcher_method: CallableABC[..., bool] | None = getattr(
    self.window.command_launcher, "launch_app", None
)

if launcher_method is None or not callable(launcher_method):
    success = False
else:
    # Runtime introspection
    sig = inspect.signature(launcher_method)
    supports_selected_plate = "selected_plate" in sig.parameters

    if supports_selected_plate and selected_plate and app_name == "nuke":
        # ⚠️ Cast bypasses type safety
        launcher = cast("CommandLauncher", self.window.command_launcher)
        success = launcher.launch_app(
            app_name,
            include_undistortion,
            include_raw_plate,
            open_latest_threede,
            open_latest_maya,
            open_latest_scene,
            create_new_file,
            selected_plate=selected_plate,
        )
    else:
        # SimplifiedLauncher or no plate selected
        success = self.window.command_launcher.launch_app(
            app_name,
            include_undistortion,
            include_raw_plate,
            open_latest_threede,
            open_latest_maya,
            open_latest_scene,
            create_new_file,
        )
```

**Issues:**
1. Runtime introspection bypasses type checking
2. cast() assumes type without verification
3. Complex branching logic
4. Easy to introduce bugs when signatures change

### Improved Code with Capability Protocols

```python
# Create launcher_protocols.py
from typing import Protocol, TypeIs

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
    ) -> bool: ...

class PlateAwareLauncher(BasicLauncher, Protocol):
    """Launcher with plate selection support."""

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
    ) -> bool: ...

# Type guard for capability detection (Python 3.13+)
def supports_plate_selection(
    launcher: object
) -> TypeIs[PlateAwareLauncher]:
    """Check if launcher supports plate selection."""
    import inspect
    if not hasattr(launcher, "launch_app"):
        return False
    sig = inspect.signature(launcher.launch_app)
    return "selected_plate" in sig.parameters

# Update launcher_controller.py
from launcher_protocols import (
    BasicLauncher,
    PlateAwareLauncher,
    supports_plate_selection,
)

# Simplified logic with type safety
if supports_plate_selection(self.window.command_launcher):
    # ✅ Type checker knows it's PlateAwareLauncher
    success = self.window.command_launcher.launch_app(
        app_name,
        include_undistortion,
        include_raw_plate,
        open_latest_threede,
        open_latest_maya,
        open_latest_scene,
        create_new_file,
        selected_plate=selected_plate,
    )
else:
    # ✅ Type checker knows it's BasicLauncher
    success = self.window.command_launcher.launch_app(
        app_name,
        include_undistortion,
        include_raw_plate,
        open_latest_threede,
        open_latest_maya,
        open_latest_scene,
        create_new_file,
    )
```

**Benefits:**
- Eliminates cast()
- Type checker validates all method calls
- Clearer capability-based design
- Easier to understand and maintain
- Type errors caught at compile time

---

## Example 4: TypedDict with ReadOnly Fields (Python 3.13+)

### Current Code (launcher/models.py, line 20)

```python
class ProcessInfoDict(TypedDict):
    """Type definition for process information dictionary."""

    type: str           # Could be accidentally modified
    key: str            # Could be accidentally modified
    launcher_id: str    # Could be accidentally modified
    launcher_name: str  # Could be accidentally modified
    command: str        # Should be mutable?
    pid: int            # Could be accidentally modified
    running: bool       # Status changes - should be mutable
    start_time: float   # Could be accidentally modified
```

**Issue:** All fields are mutable - accidental modifications not caught.

### Improved Code with ReadOnly (Python 3.13+)

```python
from typing import TypedDict, ReadOnly

class ProcessInfoDict(TypedDict):
    """Type definition for process information dictionary.

    Immutable fields (ReadOnly):
    - type, key, launcher_id, launcher_name: Process identity
    - pid, start_time: Process metadata
    - command: Executed command

    Mutable fields:
    - running: Status changes during process lifecycle
    """

    type: ReadOnly[str]           # ✅ Immutable identity
    key: ReadOnly[str]            # ✅ Immutable identity
    launcher_id: ReadOnly[str]    # ✅ Immutable identity
    launcher_name: ReadOnly[str]  # ✅ Immutable identity
    command: ReadOnly[str]        # ✅ Immutable command
    pid: ReadOnly[int]            # ✅ Immutable process ID
    running: bool                 # Mutable status
    start_time: ReadOnly[float]   # ✅ Immutable timestamp

# Type checker now prevents accidental modifications
info: ProcessInfoDict = {
    "type": "subprocess",
    "key": "abc123",
    "launcher_id": "nuke_launcher",
    "launcher_name": "Nuke",
    "command": "nuke",
    "pid": 12345,
    "running": True,
    "start_time": 1234567890.0,
}

info["running"] = False  # ✅ OK - mutable field
info["pid"] = 99999      # ✗ Error - ReadOnly field cannot be modified
info["command"] = "foo"  # ✗ Error - ReadOnly field cannot be modified
```

**Benefits:**
- Prevents accidental modification of immutable data
- Self-documenting (clear which fields change)
- Caught at compile time, not runtime
- No performance overhead

---

## Example 5: Generic Protocols for Flexible Interfaces

### Current Code (protocols.py, line 62)

```python
@runtime_checkable
class ProcessPoolInterface(Protocol):
    """Protocol for process pool implementations."""

    def execute_workspace_command(
        self,
        command: str,
        cache_ttl: int = 30,
        timeout: int | None = None,
    ) -> str:  # ⚠️ Always returns str - inflexible
        """Execute workspace command."""
        ...

    def batch_execute(
        self,
        commands: list[str],
        cache_ttl: int = 30,
        session_type: str = "workspace",
    ) -> dict[str, str | None]:  # ⚠️ Must be str | None
        """Execute multiple commands in parallel."""
        ...
```

**Issue:** Return types are fixed - cannot support different result types.

### Improved Code with Generic Protocol

```python
from typing import Protocol, TypeVar

T = TypeVar('T')

@runtime_checkable
class ProcessPoolInterface(Protocol[T]):
    """Generic protocol for process pool implementations.

    Type parameter T determines the return type of commands.
    Common instantiations:
    - ProcessPoolInterface[str]: Command output as string
    - ProcessPoolInterface[dict[str, Any]]: Parsed JSON output
    - ProcessPoolInterface[Path]: File path results
    """

    def execute_workspace_command(
        self,
        command: str,
        cache_ttl: int = 30,
        timeout: int | None = None,
    ) -> T:
        """Execute workspace command with typed result."""
        ...

    def batch_execute(
        self,
        commands: list[str],
        cache_ttl: int = 30,
        session_type: str = "workspace",
    ) -> dict[str, T | None]:
        """Execute multiple commands with typed results."""
        ...

# Usage examples

# String results (current usage)
string_pool: ProcessPoolInterface[str] = get_string_pool()
output: str = string_pool.execute_workspace_command("ls")
batch: dict[str, str | None] = string_pool.batch_execute(["ls", "pwd"])

# JSON results (future usage)
json_pool: ProcessPoolInterface[dict[str, Any]] = get_json_pool()
data: dict[str, Any] = json_pool.execute_workspace_command("get_metadata")
batch_data: dict[str, dict[str, Any] | None] = json_pool.batch_execute([...])

# Path results (future usage)
path_pool: ProcessPoolInterface[Path] = get_path_pool()
file_path: Path = path_pool.execute_workspace_command("find_latest")
```

**Benefits:**
- Flexible return types without breaking existing code
- Type-safe for different use cases
- Self-documenting through type parameters
- Enables future extensions without API changes

---

## Example 6: Type Narrowing with TypeIs (Python 3.13+)

### Current Code (utils.py pattern)

```python
def process_item(item: Shot | ThreeDEScene | dict) -> None:
    """Process different item types."""
    if isinstance(item, dict):
        # Type checker sees: dict (too broad)
        show = item.get("show")  # Could be Any
        # ... process dict
    elif isinstance(item, Shot):
        # Type checker sees: Shot
        show = item.show
        # ... process shot
    else:
        # Type checker sees: ThreeDEScene
        show = item.show
        # ... process scene
```

**Issue:** dict type is too broad - no structure validation.

### Improved Code with TypeIs

```python
from typing import TypeIs

def is_shot_dict(value: object) -> TypeIs[ShotDict]:
    """Narrow to ShotDict with validation."""
    return (
        isinstance(value, dict)
        and "show" in value
        and "sequence" in value
        and "shot" in value
        and isinstance(value["show"], str)
        and isinstance(value["sequence"], str)
        and isinstance(value["shot"], str)
    )

def is_scene_dict(value: object) -> TypeIs[ThreeDESceneData]:
    """Narrow to ThreeDESceneData with validation."""
    return (
        isinstance(value, dict)
        and "show" in value
        and "user" in value
        and "plate" in value
        and isinstance(value["show"], str)
        and isinstance(value["user"], str)
        and isinstance(value["plate"], str)
    )

def process_item(item: Shot | ThreeDEScene | ShotDict | ThreeDESceneData) -> None:
    """Process different item types with type safety."""
    if is_shot_dict(item):
        # ✅ Type checker knows: ShotDict
        show: str = item["show"]  # Type-safe access
        # ... process shot dict
    elif isinstance(item, Shot):
        # ✅ Type checker knows: Shot
        show = item.show
        # ... process shot
    elif is_scene_dict(item):
        # ✅ Type checker knows: ThreeDESceneData
        show = item["show"]
        user = item["user"]
        # ... process scene dict
    else:
        # ✅ Type checker knows: ThreeDEScene
        show = item.show
        # ... process scene
```

**Benefits:**
- Type checker validates dict structure
- Runtime validation catches malformed data
- Type-safe field access
- No cast() needed
- Self-documenting validation

---

## Example 7: Strict Mode Configuration

### Current Config (pyproject.toml)

```toml
[tool.basedpyright]
typeCheckingMode = "basic"  # ⚠️ Minimal checking

# All key rules disabled
reportMissingImports = false
reportMissingTypeStubs = false
reportUnknownMemberType = false
reportUnknownParameterType = false
reportUnknownArgumentType = false
reportUnknownVariableType = false
reportUnannotatedClassAttribute = false
```

**What this misses:**
- Unknown type propagation through attribute access
- Missing parameter annotations
- Untyped function calls
- Inferred Unknown variables
- Unannotated class attributes

### Recommended Config (basedpyright recommended mode)

```toml
[tool.basedpyright]
typeCheckingMode = "recommended"  # ✅ Balanced strictness
pythonVersion = "3.12"

# Enable graduated diagnostics
reportUnknownMemberType = "warning"       # Catch Unknown propagation
reportUnknownParameterType = "warning"    # Require parameter types
reportUnknownArgumentType = "warning"     # Check function calls
reportUnknownVariableType = "information" # Track untyped variables
reportUnannotatedClassAttribute = "warning"

# Basedpyright-exclusive features
strictListInference = true    # list[int | str] not list[Any]
strictDictionaryInference = true  # dict[str, int] not dict[str, Any]
strictSetInference = true     # set[int | str] not set[Any]
strictGenericNarrowing = true # Better isinstance narrowing

# Enforce best practices
reportIgnoreCommentWithoutRule = "error"  # Require specific error codes
reportAny = "warning"         # Flag Any types
reportExplicitAny = "error"   # Ban direct Any usage

# Quality gates
reportUnnecessaryTypeIgnoreComment = "warning"
reportUnusedVariable = "warning"
reportUnusedImport = "warning"
```

**What this catches:**
- 50-200 new type issues (estimated)
- Unknown type propagation
- Missing annotations
- Unnecessary type ignores
- Unused code

---

## Summary of Improvements

| Example | Current Issues | Improvements | Type Errors Prevented |
|---------|---------------|--------------|----------------------|
| **TypeGuards** | Unsafe dict handling | Validated narrowing | 10-15/year |
| **Protocols** | object types, ignores | Type-safe interfaces | 5-10/year |
| **Capabilities** | Runtime checks, cast() | Compile-time validation | 3-5/year |
| **ReadOnly** | Accidental mutations | Immutable protection | 2-3/year |
| **Generic Protocols** | Fixed return types | Flexible, type-safe | 1-2/year |
| **TypeIs** | Broad dict types | Precise narrowing | 5-8/year |
| **Strict Config** | Hidden issues | Comprehensive checking | 20-30/year |

**Total Estimated Bugs Prevented:** 46-73 type-related bugs per year

**Implementation Effort:** 2-3 weeks for all examples

**Ongoing Benefit:** Better IDE support, clearer interfaces, fewer runtime errors
