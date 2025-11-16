# Launcher Code Review - Quick Fixes

**Priority:** High (Immediate Actions)
**Estimated Time:** 15 minutes
**Impact:** Code quality improvements

---

## FIX #1: Remove Duplicate Time Import

**File:** `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`
**Line:** 146
**Severity:** Low (PEP 8 violation)
**Time:** 2 minutes

### Current Code:
```python
def _run_send_command(self) -> None:
    # ...line 145
    import time  # ❌ DUPLICATE - already imported at top
    enqueue_time = time.time()
```

### Fixed Code:
```python
def _run_send_command(self) -> None:
    # ...line 145
    enqueue_time = time.time()  # ✅ Use top-level import
```

### Why:
- PEP 8: Imports belong at module top
- Already imported at line 21
- Inline import adds micro performance overhead

---

## FIX #2: Add Logger Type Annotation

**File:** `/home/gabrielh/projects/shotbot/launch/process_executor.py`
**Line:** 26
**Severity:** Low (Type safety)
**Time:** 2 minutes

### Current Code:
```python
import logging

logger = logging.getLogger(__name__)  # Implicit type
```

### Fixed Code:
```python
import logging
from typing import Final

logger: Final[logging.Logger] = logging.getLogger(__name__)  # ✅ Explicit
```

### Why:
- Explicit type annotation improves clarity
- `Final` prevents reassignment
- Consistent with modern Python practices
- Helps type checker

---

## FIX #3: Document Subprocess Lifecycle

**File:** `/home/gabrielh/projects/shotbot/command_launcher.py`
**Line:** 543
**Severity:** Medium (Resource cleanup)
**Time:** 5 minutes

### Current Code:
```python
process = subprocess.Popen(term_cmd)

# Async verification after 100ms
QTimer.singleShot(100, partial(self.process_executor.verify_spawn, process, app_name))
```

### Recommendation:
Add documentation comment:

```python
# Launch terminal process
# Note: Process is intentionally not reaped here - it's a GUI app (long-running)
# After verify_spawn checks it's alive, the process reference is released
# allowing it to run independently
process = subprocess.Popen(term_cmd)

# Async verification after 100ms
QTimer.singleShot(100, partial(self.process_executor.verify_spawn, process, app_name))
```

### Why:
- Clarifies design intent
- Prevents future "fixes" that add unwanted reaping
- Documents that zombie processes are acceptable for GUI apps
- Improves maintainability

---

## OPTIONAL: Extract Scene Finding Logic

**File:** `/home/gabrielh/projects/shotbot/command_launcher.py`
**Lines:** 706-732 (similar patterns at 735-761)
**Severity:** Low (Code organization)
**Time:** 15-20 minutes (if done)

### Current Code (duplication):
```python
if app_name == "3de" and context.open_latest_threede:
    latest_scene = self._threede_latest_finder.find_latest_threede_scene(...)
    if latest_scene:
        try:
            safe_scene_path = CommandBuilder.validate_path(str(latest_scene))
            command = f"{command} -open {safe_scene_path}"
            # ...
        except ValueError as e:
            # ...

if app_name == "maya" and context.open_latest_maya:
    latest_scene = self._maya_latest_finder.find_latest_maya_scene(...)
    if latest_scene:
        try:
            safe_scene_path = CommandBuilder.validate_path(str(latest_scene))
            command = f"{command} -file {safe_scene_path}"
            # ...
```

### Suggestion:
Extract to helper method:
```python
def _append_scene_file_to_command(
    self,
    app_name: str,
    command: str,
    context: LaunchContext,
) -> str:
    """Append latest scene file to command if available."""
    # DRY implementation for 3DE, Maya, etc.
```

### Why:
- Reduces method length (currently ~185 lines)
- Eliminates duplication
- Easier to test individual app handling
- Improves readability

---

## SUMMARY

| Fix | File | Time | Impact |
|-----|------|------|--------|
| Remove duplicate import | persistent_terminal_manager.py | 2m | High (correctness) |
| Add logger annotation | process_executor.py | 2m | Low (clarity) |
| Document subprocess lifecycle | command_launcher.py | 5m | High (maintainability) |
| Extract scene logic | command_launcher.py | 15-20m | Medium (code quality) |

**Total Time Estimate:** 9-29 minutes (10m mandatory + 20m optional)

---

## TESTING

After making changes, run:
```bash
# Type checking
~/.local/bin/uv run basedpyright

# Linting
~/.local/bin/uv run ruff check .

# Tests
~/.local/bin/uv run pytest tests/unit/test_launcher*.py -v
```

---

## NOTES

- No functional bugs found
- All changes are code quality improvements
- No changes needed for thread safety
- No changes needed for resource management
- Suggested extractions are for maintainability, not critical

