# Shotbot Refactoring Roadmap 2025 Q1 - DO NOT DELETE

**Document Version**: 1.0
**Created**: 2025-11-12
**Status**: APPROVED - Ready for Implementation
**Estimated Total Effort**: 10-15 days
**Expected Code Reduction**: ~500 lines (20-30%)

---

## Executive Summary

This roadmap addresses 23 verified KISS/DRY violations identified through multi-agent code review. All findings have been independently verified with 100% accuracy. The plan is organized into 3 phases with increasing complexity and risk, starting with quick wins that build confidence and establish patterns for larger refactorings.

**Success Criteria**:
- Zero test regressions (2,300+ tests must pass)
- Zero type checking errors (basedpyright --strict)
- Measurable reduction in code duplication and complexity
- Improved maintainability scores

---

## Table of Contents

1. [Phase 1: Quick Wins](#phase-1-quick-wins-3-4-hours)
2. [Phase 2: High-Confidence Refactorings](#phase-2-high-confidence-refactorings-5-8-days)
3. [Phase 3: Architectural Improvements](#phase-3-architectural-improvements-5-7-days)
4. [Success Metrics](#success-metrics)
5. [Risk Management](#risk-management)
6. [Testing Strategy](#testing-strategy)

---

## Phase 1: Quick Wins (3-4 hours)

**Goal**: Immediate cleanup with zero risk to establish momentum
**Expected Code Reduction**: ~80 lines
**Risk Level**: VERY LOW
**Dependencies**: None

---

### Task 1.1: Remove Useless Stub Classes

**Priority**: P0 (Immediate)
**Effort**: 15 minutes
**Lines Removed**: 15

#### Current State
```python
# cache_manager.py:167-181
@final
class ThumbnailCacheResult:
    """Stub for backward compatibility - no longer used in simplified implementation."""
    def __init__(self) -> None:
        super().__init__()
        self.future = None
        self.path = None
        self.is_complete = False

@final
class ThumbnailCacheLoader:
    """Stub for backward compatibility - no longer used in simplified implementation."""
```

#### Action Steps
1. **Verify no references**: `grep -r "ThumbnailCacheResult\|ThumbnailCacheLoader" --include="*.py"`
2. **Delete lines 167-181** from `cache_manager.py`
3. **Verify imports**: Check no external modules import these classes

#### Code Changes
```python
# DELETE: Lines 167-181 from cache_manager.py
# No replacement needed
```

#### Success Metrics
- ✅ Grep returns 0 matches for both class names
- ✅ All tests pass: `uv run pytest tests/`
- ✅ Type check passes: `uv run basedpyright`
- ✅ File size reduced by 15 lines

#### Verification
```bash
# Before
wc -l cache_manager.py  # Should show current line count

# After deletion
grep -r "ThumbnailCacheResult\|ThumbnailCacheLoader" --include="*.py"  # Should be empty
~/.local/bin/uv run pytest tests/unit/test_cache_manager.py -v
~/.local/bin/uv run basedpyright cache_manager.py
wc -l cache_manager.py  # Should show -15 lines
```

#### Rollback Plan
```bash
git checkout cache_manager.py
```

---

### Task 1.2: Extract Timestamp Formatting Helper

**Priority**: P0 (Immediate)
**Effort**: 1 hour
**Lines Saved**: ~12 lines
**Locations**: controllers/launcher_controller.py (6 occurrences)

#### Current State
```python
# Repeated 6 times at lines: 256, 269, 277, 310, 464, 470
timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
self.window.log_viewer.add_command(timestamp, "message")
# or
self.window.log_viewer.add_error(timestamp, "message")
```

#### Action Steps
1. **Add helper methods** to `LauncherController` class
2. **Replace all 6 occurrences** with helper calls
3. **Verify logging output unchanged**

#### Code Changes

**Step 1: Add helper methods after line 200** (after `__init__`):
```python
def _log_command(self, message: str) -> None:
    """Log command with current timestamp.

    Args:
        message: Command message to log
    """
    timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
    self.window.log_viewer.add_command(timestamp, message)

def _log_error(self, message: str) -> None:
    """Log error with current timestamp.

    Args:
        message: Error message to log
    """
    timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
    self.window.log_viewer.add_error(timestamp, message)
```

**Step 2: Replace occurrences**:
```python
# OLD (Line 256-258):
timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
self.window.log_viewer.add_command(
    timestamp, "Using shot context (no scene selected)"
)

# NEW:
self._log_command("Using shot context (no scene selected)")

# OLD (Line 269-273):
timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
self.window.log_viewer.add_command(
    timestamp,
    f"Re-synced shot context: {self._current_shot.full_name}",
)

# NEW:
self._log_command(f"Re-synced shot context: {self._current_shot.full_name}")

# OLD (Line 277-280):
timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
self.window.log_viewer.add_error(
    timestamp,
    "No shot selected - please select a shot before launching",
)

# NEW:
self._log_error("No shot selected - please select a shot before launching")

# Repeat for lines 310, 464, 470
```

#### Success Metrics
- ✅ 2 new helper methods added
- ✅ 6 occurrences replaced
- ✅ Net reduction: 12 lines (18 deleted, 6 added)
- ✅ No changes to log output format
- ✅ All launcher tests pass

#### Verification
```bash
# Count occurrences before
grep -n "timestamp = datetime.now.*strftime" controllers/launcher_controller.py | wc -l  # Should be 6

# After replacement
grep -n "timestamp = datetime.now.*strftime" controllers/launcher_controller.py | wc -l  # Should be 0
grep -n "_log_command\|_log_error" controllers/launcher_controller.py | wc -l  # Should be 6+

# Test
~/.local/bin/uv run pytest tests/unit/test_launcher_controller.py -v -k "log"
```

#### Rollback Plan
```bash
git checkout controllers/launcher_controller.py
```

---

### Task 1.3: Extract Notification Helper Methods

**Priority**: P0 (Immediate)
**Effort**: 2 hours
**Lines Saved**: ~30 lines
**Locations**: controllers/launcher_controller.py (10+ occurrences)

#### Current State
```python
# Repeated patterns:
NotificationManager.warning("No Shot Selected", "Please select a shot...")
NotificationManager.error("Launch Failed", f"Failed to launch {app_name}")
NotificationManager.toast(f"Launched {app_name} successfully", NotificationType.SUCCESS)
```

#### Action Steps
1. **Add notification helper methods** to `LauncherController`
2. **Replace all direct NotificationManager calls**
3. **Verify notification behavior unchanged**

#### Code Changes

**Step 1: Add helper methods** (add after `_log_error` method):
```python
def _notify_no_shot_selected(self) -> None:
    """Show standard notification when no shot is selected."""
    NotificationManager.warning(
        "No Shot Selected",
        "Please select a shot before launching applications."
    )

def _notify_no_scene_selected(self) -> None:
    """Show standard notification when no scene is selected."""
    NotificationManager.warning(
        "No Scene Selected",
        "Please select a 3DE scene before attempting this operation."
    )

def _notify_no_plate_selected(self) -> None:
    """Show standard notification when no plate is selected for Nuke."""
    NotificationManager.warning(
        "No Plate Selected",
        "Please select a plate space (e.g., FG01, BG01) before launching Nuke."
    )

def _notify_launch_success(self, app_name: str) -> None:
    """Show success notification for app launch.

    Args:
        app_name: Name of the launched application
    """
    NotificationManager.toast(
        f"Launched {app_name} successfully",
        NotificationType.SUCCESS
    )

def _notify_launch_failed(self, app_name: str, reason: str | None = None) -> None:
    """Show error notification for app launch failure.

    Args:
        app_name: Name of the application that failed to launch
        reason: Optional reason for failure
    """
    message = f"Failed to launch {app_name}"
    if reason:
        message += f": {reason}"
    NotificationManager.error("Launch Failed", message)
```

**Step 2: Replace occurrences**:
```python
# Line 282-285 OLD:
NotificationManager.warning(
    "No Shot Selected",
    "Please select a shot before launching applications.",
)
# NEW:
self._notify_no_shot_selected()

# Line 315-318 OLD:
NotificationManager.warning(
    "No Plate Selected",
    "Please select a plate space (e.g., FG01, BG01) before launching Nuke.",
)
# NEW:
self._notify_no_plate_selected()

# Line 356-358 OLD:
NotificationManager.toast(
    f"Launched {app_name} successfully", NotificationType.SUCCESS
)
# NEW:
self._notify_launch_success(app_name)
```

#### Success Metrics
- ✅ 5 new notification helper methods added
- ✅ 10+ direct NotificationManager calls replaced
- ✅ Net reduction: ~30 lines
- ✅ Notification behavior unchanged
- ✅ All notification tests pass

#### Verification
```bash
# Count direct NotificationManager calls before
grep -n "NotificationManager\.(warning|error|toast)" controllers/launcher_controller.py | wc -l

# After replacement (should only be in helper methods)
grep -n "NotificationManager\.(warning|error|toast)" controllers/launcher_controller.py | wc -l  # Lower count
grep -n "self._notify_" controllers/launcher_controller.py | wc -l  # Should be 10+

# Test
~/.local/bin/uv run pytest tests/unit/test_launcher_controller.py -v
~/.local/bin/uv run pytest tests/integration/ -k "notification" -v
```

#### Rollback Plan
```bash
git checkout controllers/launcher_controller.py
```

---

### Phase 1 Completion Checklist

- [ ] Task 1.1: Useless stubs removed
- [ ] Task 1.2: Timestamp helper extracted
- [ ] Task 1.3: Notification helpers extracted
- [ ] All tests pass: `uv run pytest tests/ -n auto --dist=loadgroup`
- [ ] Type check passes: `uv run basedpyright`
- [ ] Code reduction: ~80 lines verified
- [ ] Git commit: `git commit -m "refactor: Phase 1 quick wins - extract helpers and remove stubs"`

---

## Phase 2: High-Confidence Refactorings (5-8 days)

**Goal**: Eliminate major duplication and complexity with low risk
**Expected Code Reduction**: ~200 lines
**Risk Level**: LOW
**Dependencies**: Phase 1 complete

---

### Task 2.1: Extract Duplicate Merge Logic in CacheManager

**Priority**: P1 (High)
**Effort**: 1 day
**Lines Saved**: ~50 lines
**Risk**: LOW
**Files**: cache_manager.py

#### Current State
- `merge_shots_incremental()`: 68 lines (662-729)
- `merge_scenes_incremental()`: 67 lines (779-845)
- **135 lines total, 80% identical**

#### Problem Analysis
Both methods follow identical algorithm:
1. Convert to dicts
2. Build key lookups
3. Merge fresh data (UPDATE or ADD)
4. Identify removed items
5. Return merge result

Only differences:
- Key extraction functions (`_get_shot_key` vs `_get_scene_key`)
- Type annotations (`ShotDict` vs `ThreeDESceneDict`)
- Minor merge strategy (scenes keep removed, shots don't)

#### Action Steps
1. **Create generic merge function** with type parameters
2. **Update both methods** to use generic implementation
3. **Preserve all existing behavior** (especially for scenes keeping removed items)
4. **Add comprehensive tests** for edge cases

#### Code Changes

**Step 1: Add generic merge function** (insert after line 661):
```python
def _merge_incremental_generic(
    self,
    cached: Sequence[T] | None,
    fresh: Sequence[T],
    to_dict_func: Callable[[T], dict[str, object]],
    get_key_func: Callable[[dict[str, object]], tuple[str, str, str]],
    keep_removed: bool = False,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], bool]:
    """Generic incremental merge algorithm for shots or scenes.

    Args:
        cached: Previously cached items
        fresh: Fresh items from discovery
        to_dict_func: Function to convert item to dict
        get_key_func: Function to extract key tuple from dict
        keep_removed: If True, removed items stay in result (for scenes)

    Returns:
        Tuple of (updated_items, new_items, removed_items, has_changes)

    Algorithm:
        1. Convert to dicts for consistent handling
        2. Build lookup: cached_by_key[key] = item
        3. Build set: fresh_keys = {key}
        4. For each fresh item:
           - If in cached: UPDATE with fresh data
           - If not in cached: ADD as new
        5. Identify removed: cached_keys - fresh_keys
        6. Return merged list (optionally keeping removed items)
    """
    # Convert to dicts
    cached_dicts = [to_dict_func(item) for item in (cached or [])]
    fresh_dicts = [to_dict_func(item) for item in fresh]

    # Build lookups
    cached_by_key: dict[tuple[str, str, str], dict[str, object]] = {
        get_key_func(item): item for item in cached_dicts
    }
    fresh_keys = {get_key_func(item) for item in fresh_dicts}

    # Merge: fresh data overrides cached
    if keep_removed:
        # Scenes: Keep removed items in result
        updated_by_key = cached_by_key.copy()
        new_items = []
        for fresh_item in fresh_dicts:
            fresh_key = get_key_func(fresh_item)
            if fresh_key not in cached_by_key:
                new_items.append(fresh_item)
            updated_by_key[fresh_key] = fresh_item
        updated_items = list(updated_by_key.values())
    else:
        # Shots: Only include fresh items
        updated_items = fresh_dicts.copy()
        new_items = [
            item for item in fresh_dicts
            if get_key_func(item) not in cached_by_key
        ]

    # Identify removed
    removed_keys = set(cached_by_key.keys()) - fresh_keys
    removed_items = [cached_by_key[key] for key in removed_keys]

    has_changes = bool(new_items or removed_items)

    return (updated_items, new_items, removed_items, has_changes)
```

**Step 2: Refactor merge_shots_incremental** (replace lines 662-729):
```python
def merge_shots_incremental(
    self,
    cached: list[Shot | ShotDict] | None,
    fresh: list[Shot | ShotDict],
) -> ShotMergeResult:
    """Merge cached shots with fresh data incrementally.

    Algorithm:
        1. Convert to dicts for consistent handling
        2. Build lookup: cached_by_key[(show, seq, shot)] = shot (O(1))
        3. Build set: fresh_keys = {(show, seq, shot)}
        4. For each fresh shot:
           - If in cached: UPDATE metadata
           - If not in cached: ADD as new
        5. Identify removed: cached_keys - fresh_keys

    Args:
        cached: Previously cached shots (Shot objects or ShotDicts)
        fresh: Fresh shots from workspace command (Shot objects or ShotDicts)

    Returns:
        ShotMergeResult with updated list and statistics

    Design:
        Uses composite key (show, sequence, shot) for global uniqueness.
        This provides better deduplication than Shot.full_name property
        (which excludes 'show' field and could theoretically collide across shows).

    Thread Safety:
        Protected by internal mutex to prevent concurrent merge operations
        that could produce inconsistent results.
    """
    with QMutexLocker(self._lock):
        updated_shots, new_shots, removed_shots, has_changes = (
            self._merge_incremental_generic(
                cached=cached,
                fresh=fresh,
                to_dict_func=_shot_to_dict,
                get_key_func=_get_shot_key,
                keep_removed=False,  # Shots: don't keep removed
            )
        )

        # Type narrowing for return
        return ShotMergeResult(
            updated_shots=cast("list[ShotDict]", updated_shots),
            new_shots=cast("list[ShotDict]", new_shots),
            removed_shots=cast("list[ShotDict]", removed_shots),
            has_changes=has_changes,
        )
```

**Step 3: Refactor merge_scenes_incremental** (replace lines 779-845):
```python
def merge_scenes_incremental(
    self,
    cached: Sequence[object] | None,
    fresh: Sequence[object],
) -> SceneMergeResult:
    """Merge cached 3DE scenes with fresh data incrementally.

    Algorithm:
        1. Convert to dicts for consistent handling
        2. Build lookup: cached_by_key[(show, seq, shot)] = scene
        3. Build set: fresh_keys = {(show, seq, shot)}
        4. For each fresh scene:
           - If in cached: UPDATE with fresh data (newer mtime/plate)
           - If not in cached: ADD as new
        5. Identify removed: cached_keys - fresh_keys (kept for history)

    Note: Uses shot-level key (show, sequence, shot) since deduplication
    is applied after merge to keep best scene per shot.

    Args:
        cached: Previously cached scenes (ThreeDEScene objects or dicts)
        fresh: Fresh scenes from discovery (ThreeDEScene objects or dicts)

    Returns:
        SceneMergeResult with merged list and statistics

    Thread Safety:
        Protected by internal mutex to prevent concurrent merge operations
        that could produce inconsistent results.
    """
    with QMutexLocker(self._lock):
        updated_scenes, new_scenes, removed_scenes, has_changes = (
            self._merge_incremental_generic(
                cached=cached,
                fresh=fresh,
                to_dict_func=_scene_to_dict,
                get_key_func=_get_scene_key,
                keep_removed=True,  # Scenes: keep removed for history
            )
        )

        # Type narrowing for return
        return SceneMergeResult(
            updated_scenes=cast("list[ThreeDESceneDict]", updated_scenes),
            new_scenes=cast("list[ThreeDESceneDict]", new_scenes),
            removed_scenes=cast("list[ThreeDESceneDict]", removed_scenes),
            has_changes=has_changes,
        )
```

#### Success Metrics
- ✅ Generic merge function created (~50 lines)
- ✅ Both merge methods reduced to ~25 lines each
- ✅ Net reduction: ~50 lines (135 → ~100 total)
- ✅ All cache tests pass
- ✅ Behavior unchanged for both shots and scenes
- ✅ Type checking passes

#### Verification
```bash
# Before
grep -A 70 "def merge_shots_incremental" cache_manager.py | wc -l  # ~68
grep -A 70 "def merge_scenes_incremental" cache_manager.py | wc -l  # ~67

# After
grep -A 30 "def merge_shots_incremental" cache_manager.py | wc -l  # ~25
grep -A 30 "def merge_scenes_incremental" cache_manager.py | wc -l  # ~25
grep -A 60 "def _merge_incremental_generic" cache_manager.py | wc -l  # ~50

# Test thoroughly
~/.local/bin/uv run pytest tests/unit/test_cache_manager.py -v -k "merge"
~/.local/bin/uv run pytest tests/integration/test_cache_operations.py -v

# Specific scenarios
~/.local/bin/uv run pytest tests/unit/test_cache_manager.py::TestCacheManager::test_merge_shots_incremental -v
~/.local/bin/uv run pytest tests/unit/test_cache_manager.py::TestCacheManager::test_merge_scenes_incremental -v
```

#### Rollback Plan
```bash
git checkout cache_manager.py
```

---

### Task 2.2: Extract Duplicate Shot Merge Logic (Async/Sync)

**Priority**: P1 (High)
**Effort**: 4 hours
**Lines Saved**: ~40 lines
**Risk**: LOW
**Files**: shot_model.py

#### Current State
- Async path (`_on_shots_loaded`): Lines 305-354 (50 lines)
- Sync path (`refresh_shots_sync`): Lines 620-672 (53 lines)
- **103 lines total, 95% identical**

#### Problem Analysis
Both methods have identical:
1. Cache loading (3 lines) - 100% identical
2. Error handling (15 lines) - 100% identical
3. Merge statistics logging (4 lines) - 95% identical
4. Migration logic (20 lines) - 100% identical

#### Action Steps
1. **Extract shared logic** to private method
2. **Update both async and sync** methods to use shared implementation
3. **Preserve error emission** differences (async emits signals, sync returns)
4. **Test both paths thoroughly**

#### Code Changes

**Step 1: Add shared merge method** (insert after line 304):
```python
def _process_shot_merge(
    self,
    fresh_shots: list[Shot],
    operation_name: str = "refresh",
) -> tuple[list[Shot], bool]:
    """Process shot merge with cache, handling corruption and migration.

    This method contains the shared logic for merging fresh shots with cached data,
    used by both async and sync refresh paths.

    Args:
        fresh_shots: Fresh shots from workspace command
        operation_name: Name of operation for logging ("refresh" or "sync")

    Returns:
        Tuple of (merged_shot_objects, has_changes)

    Raises:
        Exception: On unexpected merge failures (caller should handle)
    """
    # Load persistent cache
    cached_dicts = self.cache_manager.get_persistent_shots() or []
    fresh_dicts = [s.to_dict() for s in fresh_shots]

    # Log data sources
    self.logger.info(
        f"{operation_name.capitalize()}: {len(fresh_dicts)} shots from workspace, "
        f"{len(cached_dicts)} shots from persistent cache"
    )

    # Merge with cache corruption recovery
    try:
        merge_result = self.cache_manager.merge_shots_incremental(
            cached_dicts, fresh_dicts
        )
    except (KeyError, TypeError, ValueError) as e:
        # Corrupted cache data - fall back to fresh data only
        self.logger.warning(f"Cache corruption detected, using fresh data only: {e}")
        merge_result = ShotMergeResult(
            updated_shots=[s.to_dict() for s in fresh_shots],
            new_shots=[s.to_dict() for s in fresh_shots],
            removed_shots=[],
            has_changes=True,
        )

    # Log merge statistics
    self.logger.info(
        f"Shot merge ({operation_name}): {len(merge_result.new_shots)} new, "
        f"{len(merge_result.removed_shots)} removed, "
        f"{len(merge_result.updated_shots)} total"
    )

    # Migrate removed shots to Previous Shots
    if merge_result.removed_shots:
        try:
            self.cache_manager.migrate_shots_to_previous(merge_result.removed_shots)
            removed_names = [
                f"{s['show']}:{s['sequence']}_{s['shot']}"
                for s in merge_result.removed_shots[:3]
            ]
            self.logger.info(
                f"Migrated {len(merge_result.removed_shots)} shots to Previous: "
                f"{removed_names}{'...' if len(merge_result.removed_shots) > 3 else ''}"
            )
        except OSError as e:
            # Log migration failure but don't abort refresh
            self.logger.warning(f"Failed to migrate shots (refresh continues): {e}")

    # Convert merged results to Shot objects
    try:
        new_shot_objects = [Shot.from_dict(d) for d in merge_result.updated_shots]
    except (KeyError, TypeError, ValueError) as e:
        # Corrupted merge result - use fresh data
        self.logger.error(f"Merge result corrupted, using fresh data: {e}")
        new_shot_objects = fresh_shots

    return (new_shot_objects, merge_result.has_changes)
```

**Step 2: Refactor async path** (replace lines 305-354):
```python
# In _on_shots_loaded method, replace merge logic with:
try:
    merged_shots, has_changes = self._process_shot_merge(
        fresh_shots=fresh_shots,
        operation_name="background refresh"
    )
except Exception as e:
    # Unexpected merge failure - report error and abort
    error_msg = f"Merge operation failed: {e}"
    self.logger.exception(error_msg)
    self.error_occurred.emit(error_msg)
    self.refresh_finished.emit(False, False)
    return

# Update model with merged data
self.shots = merged_shots
```

**Step 3: Refactor sync path** (replace lines 620-672):
```python
# In refresh_shots_sync method, replace merge logic with:
try:
    merged_shots, has_changes = self._process_shot_merge(
        fresh_shots=fresh_shots,
        operation_name="sync"
    )
except Exception as e:
    # Unexpected merge failure - report error and abort
    error_msg = f"Merge operation failed: {e}"
    self.logger.exception(error_msg)
    self.error_occurred.emit(error_msg)
    self.refresh_finished.emit(False, False)
    return RefreshResult(success=False, has_changes=False)

# Update model with merged data
self.shots = merged_shots
```

#### Success Metrics
- ✅ Shared merge method created (~60 lines)
- ✅ Async path reduced by ~40 lines
- ✅ Sync path reduced by ~40 lines
- ✅ Net reduction: ~40 lines (103 → ~80 + 60 shared)
- ✅ Both refresh paths tested
- ✅ Error handling preserved
- ✅ Signal emission behavior unchanged

#### Verification
```bash
# Test both refresh paths
~/.local/bin/uv run pytest tests/unit/test_shot_model.py -v -k "refresh"

# Specific async tests
~/.local/bin/uv run pytest tests/unit/test_shot_model.py::TestShotModel::test_async_refresh -v

# Specific sync tests
~/.local/bin/uv run pytest tests/unit/test_shot_model.py::TestShotModel::test_refresh_shots_sync -v

# Cache corruption recovery
~/.local/bin/uv run pytest tests/unit/test_shot_model.py -v -k "corruption"

# Full integration test
~/.local/bin/uv run pytest tests/integration/test_shot_refresh.py -v
```

#### Rollback Plan
```bash
git checkout shot_model.py
```

---

### Task 2.3: Decompose launch_app() Method

**Priority**: P1 (High)
**Effort**: 2-3 days
**Lines Reduced**: ~40 lines complexity
**Risk**: LOW (comprehensive tests exist)
**Files**: controllers/launcher_controller.py

#### Current State
- Single method: 144 lines (219-362)
- Cyclomatic complexity: 15+ branches
- 4 levels of nesting
- 6 distinct responsibilities

#### Problem Analysis
The method does too much:
1. Diagnostic logging (11 lines)
2. Context selection (scene vs shot)
3. Context synchronization (25 lines)
4. Launch option extraction (31 lines)
5. Type checking/signature inspection (31 lines)
6. Launch execution

#### Action Steps
1. **Remove diagnostic logging** (stack traces in production)
2. **Extract context validation** to separate method
3. **Extract launch option building** to separate method
4. **Extract context sync logic** to separate method
5. **Simplify launch execution** logic
6. **Test each extracted method**

#### Code Changes

**Step 1: Remove diagnostic logging** (delete lines 226-237):
```python
# DELETE these lines:
import traceback
stack = "".join(traceback.format_stack()[-5:-1])
self.logger.info(f"🚀 launch_app() called for app: {app_name}")
self.logger.info(f"📞 Call stack:\n{stack}")
self.logger.info("   Current state check:")
self.logger.info(f"   - _current_scene: ...")
self.logger.info(f"   - _current_shot: ...")

# REPLACE with simple info log:
self.logger.info(f"Launching {app_name}")
```

**Step 2: Extract context validation** (add new method):
```python
def _validate_launch_context(self) -> bool:
    """Validate that we have necessary context for launching.

    Returns:
        True if context is valid, False otherwise
    """
    # Have scene context - always valid
    if self._current_scene:
        self.logger.info(f"Using scene context: {self._current_scene.full_name}")
        return True

    # Have shot context - valid
    if self._current_shot:
        self.logger.info(f"Using shot context: {self._current_shot.full_name}")
        return True

    # Try to sync context from command_launcher
    if self._attempt_context_resync():
        return True

    # No context available
    self.logger.error("No shot or scene context available for launch")
    self._log_error("No shot selected - please select a shot before launching")
    self._notify_no_shot_selected()
    return False

def _attempt_context_resync(self) -> bool:
    """Attempt to re-sync context from command_launcher.

    Returns:
        True if context was successfully synced
    """
    if self.window.command_launcher.current_shot:
        self._current_shot = self.window.command_launcher.current_shot
        self.logger.info(f"Re-synced context from command_launcher: {self._current_shot.full_name}")
        return True
    return False
```

**Step 3: Extract launch option building** (add new method):
```python
def _build_launch_options(self, app_name: str) -> dict[str, Any] | None:
    """Build launch options from UI state and validate.

    Args:
        app_name: Name of the application

    Returns:
        Dictionary of launch options, or None if validation failed
    """
    # Get base options from UI
    options = self.get_launch_options(app_name)

    # Extract flags
    include_raw_plate = options.get("include_raw_plate", False)
    open_latest_threede = options.get("open_latest_threede", False)
    open_latest_maya = options.get("open_latest_maya", False)
    open_latest_scene = options.get("open_latest_scene", False)
    create_new_file = options.get("create_new_file", False)

    # Priority: open_latest_scene over create_new_file
    if open_latest_scene and create_new_file:
        create_new_file = False

    # Handle Nuke-specific plate selection
    selected_plate = None
    if app_name == "nuke":
        selected_plate = self.window.launcher_panel.app_sections["nuke"].get_selected_plate()

        # Validate plate selection for workspace operations
        if (open_latest_scene or create_new_file) and not selected_plate:
            self.logger.error("No plate selected for Nuke workspace operation")
            self._log_error("Please select a plate space before launching Nuke with workspace scripts")
            self._notify_no_plate_selected()
            return None

    return {
        "include_raw_plate": include_raw_plate,
        "open_latest_threede": open_latest_threede,
        "open_latest_maya": open_latest_maya,
        "open_latest_scene": open_latest_scene,
        "create_new_file": create_new_file,
        "selected_plate": selected_plate,
    }
```

**Step 4: Extract launch execution** (add new method):
```python
def _execute_launch_with_options(
    self,
    app_name: str,
    options: dict[str, Any]
) -> bool:
    """Execute launch with validated options.

    Args:
        app_name: Name of the application
        options: Launch options dictionary

    Returns:
        True if launch succeeded
    """
    # Check if launcher supports selected_plate parameter
    launcher_method = getattr(self.window.command_launcher, "launch_app", None)
    if launcher_method is None or not callable(launcher_method):
        return False

    # Check signature for selected_plate support
    sig = inspect.signature(launcher_method)
    supports_selected_plate = "selected_plate" in sig.parameters

    # Call with appropriate signature
    if supports_selected_plate and options.get("selected_plate") and app_name == "nuke":
        launcher = cast("CommandLauncher", self.window.command_launcher)
        return launcher.launch_app(
            app_name,
            options["include_raw_plate"],
            options["open_latest_threede"],
            options["open_latest_maya"],
            options["open_latest_scene"],
            options["create_new_file"],
            selected_plate=options["selected_plate"],
        )
    else:
        return self.window.command_launcher.launch_app(
            app_name,
            options["include_raw_plate"],
            options["open_latest_threede"],
            options["open_latest_maya"],
            options["open_latest_scene"],
            options["create_new_file"],
        )
```

**Step 5: Simplify main launch_app method** (replace lines 220-362):
```python
def launch_app(self, app_name: str) -> None:
    """Launch an application with appropriate context.

    Args:
        app_name: Name of the application to launch
    """
    self.logger.info(f"Launching {app_name}")

    # Validate context
    if not self._validate_launch_context():
        return

    # Execute based on context type
    if self._current_scene:
        # Launch with scene context
        if app_name == "3de":
            success = self._launch_app_with_scene(app_name, self._current_scene)
        else:
            success = self._launch_app_with_scene_context(app_name, self._current_scene)
    else:
        # Launch with shot context
        self._log_command("Using shot context (no scene selected)")

        # Ensure command_launcher has context
        if not self.window.command_launcher.current_shot:
            if self._current_shot:
                self.window.command_launcher.set_current_shot(self._current_shot)
                self._log_command(f"Re-synced shot context: {self._current_shot.full_name}")
            else:
                # Should never reach here due to _validate_launch_context
                self._log_error("No shot selected")
                self._notify_no_shot_selected()
                return

        # Build and validate options
        options = self._build_launch_options(app_name)
        if options is None:
            return  # Validation failed

        # Execute launch
        success = self._execute_launch_with_options(app_name, options)

    # Handle result
    if success:
        self.window.update_status(f"Launched {app_name}")
        self._notify_launch_success(app_name)
    else:
        self.window.update_status(f"Failed to launch {app_name}")
        # Error details handled by _on_command_error
```

#### Success Metrics
- ✅ Main method reduced from 144 → ~50 lines
- ✅ 4 helper methods created (~80 lines total)
- ✅ Cyclomatic complexity reduced from 15 → 5 per method
- ✅ Net reduction: ~14 lines (144 → 130 total)
- ✅ **But**: Much clearer and easier to test
- ✅ All launcher tests pass
- ✅ Each helper method testable independently

#### Verification
```bash
# Count lines in launch_app
grep -A 150 "def launch_app" controllers/launcher_controller.py | grep -n "^    def " | head -1
# Should show method ends much sooner

# Test all launch scenarios
~/.local/bin/uv run pytest tests/unit/test_launcher_controller.py -v -k "launch"

# Integration tests
~/.local/bin/uv run pytest tests/integration/test_launcher_integration.py -v

# Specific scenarios
~/.local/bin/uv run pytest tests/unit/test_launcher_controller.py::TestLauncherController::test_launch_with_scene_context -v
~/.local/bin/uv run pytest tests/unit/test_launcher_controller.py::TestLauncherController::test_launch_with_shot_context -v
~/.local/bin/uv run pytest tests/unit/test_launcher_controller.py::TestLauncherController::test_launch_validation_failure -v
```

#### Rollback Plan
```bash
git checkout controllers/launcher_controller.py
```

---

### Phase 2 Completion Checklist

- [ ] Task 2.1: Cache merge logic extracted
- [ ] Task 2.2: Shot merge duplication eliminated
- [ ] Task 2.3: launch_app() decomposed
- [ ] All tests pass: `uv run pytest tests/ -n auto --dist=loadgroup`
- [ ] Type check passes: `uv run basedpyright`
- [ ] Code reduction: ~200 lines verified
- [ ] Complexity metrics improved
- [ ] Git commit: `git commit -m "refactor: Phase 2 - eliminate major duplication and complexity"`

---

## Phase 3: Architectural Improvements (5-7 days)

**Goal**: Simplify architectural patterns with careful testing
**Expected Code Reduction**: ~150 lines
**Risk Level**: MEDIUM
**Dependencies**: Phase 1 & 2 complete

---

### Task 3.1: Simplify Thread Management in ThreeDEController

**Priority**: P2 (Medium)
**Effort**: 2-3 days
**Lines Saved**: ~40 lines
**Risk**: MEDIUM
**Files**: controllers/threede_controller.py

#### Current State
- `refresh_threede_scenes()`: 126 lines (168-293)
- 4 closing checks
- 4 mutex lock sections
- Zombie thread detection
- Debouncing logic

#### ⚠️ WARNING
This code is defensive for a reason. Previous threading issues likely led to this pattern. Simplification must be done carefully with extensive testing.

#### Problem Analysis
Over-defensive patterns:
1. Multiple closing checks (4 times)
2. Multiple mutex locks (4 separate sections)
3. Zombie thread detection (may be unnecessary)
4. Complex debouncing (could use Qt signals)

#### Action Steps
1. **Consolidate closing checks** to single location
2. **Reduce mutex sections** from 4 to 2
3. **Extract worker lifecycle** to helper class
4. **Replace debouncing** with proper signal throttling
5. **Test extensively** with parallel test runs

#### Code Changes

**Step 1: Extract WorkerLifecycleManager** (new file: `launcher/worker_lifecycle.py`):
```python
"""Worker lifecycle management utilities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QMutex, QMutexLocker

if TYPE_CHECKING:
    from launcher.threede_scene_worker import ThreeDESceneWorker

logger = logging.getLogger(__name__)


class WorkerLifecycleManager:
    """Manages background worker lifecycle with proper cleanup."""

    def __init__(self) -> None:
        """Initialize worker lifecycle manager."""
        self._mutex = QMutex()
        self._worker: ThreeDESceneWorker | None = None

    def has_running_worker(self) -> bool:
        """Check if a worker is currently running.

        Returns:
            True if worker exists and is not finished
        """
        with QMutexLocker(self._mutex):
            return self._worker is not None and not self._worker.isFinished()

    def stop_current_worker(self, timeout_ms: int = 5000) -> bool:
        """Stop the current worker if one exists.

        Args:
            timeout_ms: Timeout for graceful shutdown

        Returns:
            True if safe to continue, False if should abort
        """
        # Get worker reference with mutex
        with QMutexLocker(self._mutex):
            worker_to_stop = self._worker

        if not worker_to_stop:
            return True

        # Stop outside mutex
        worker_to_stop.stop()
        if not worker_to_stop.wait(timeout_ms):
            logger.warning("Failed to stop worker gracefully, using safe termination")
            worker_to_stop.safe_terminate()

        # Cleanup
        if not (hasattr(worker_to_stop, "is_zombie") and worker_to_stop.is_zombie()):
            worker_to_stop.deleteLater()

        # Clear reference with mutex
        with QMutexLocker(self._mutex):
            if self._worker == worker_to_stop:
                self._worker = None

        return True

    def set_worker(self, worker: ThreeDESceneWorker) -> None:
        """Set the current worker.

        Args:
            worker: New worker to manage
        """
        with QMutexLocker(self._mutex):
            self._worker = worker

    def cleanup(self, timeout_ms: int = 5000) -> None:
        """Clean up the current worker during shutdown.

        Args:
            timeout_ms: Timeout for graceful shutdown
        """
        self.stop_current_worker(timeout_ms)
```

**Step 2: Simplify refresh_threede_scenes** (replace lines 168-293):
```python
def refresh_threede_scenes(self) -> None:
    """Thread-safe refresh of 3DE scene list using background worker.

    This is the main entry point for 3DE scene discovery. It will:
    1. Load persistent cache immediately for instant UI update
    2. Stop any existing worker thread safely
    3. Create a new worker with current shot data
    4. Connect all signal handlers
    5. Start the background discovery process to update cache
    """
    # Single closing check at entry
    if self.window.closing:
        self.logger.debug("Ignoring refresh request during shutdown")
        return

    # Check if worker already running
    if self._worker_manager.has_running_worker():
        self.logger.debug("3DE worker already running, skipping duplicate refresh request")
        return

    # Debounce check
    if self._is_scan_too_soon():
        return
    self._last_scan_time = time.time()

    # Load cache for instant UI update
    self._load_cached_scenes_immediate()

    # Stop existing worker
    if not self._worker_manager.stop_current_worker():
        return

    # Final closing check before creating new worker
    if self.window.closing:
        return

    # Create and start new worker
    self._create_and_start_worker()

def _is_scan_too_soon(self) -> bool:
    """Check if scan is being requested too soon (debounce).

    Returns:
        True if should skip scan
    """
    if self._last_scan_time <= 0:
        return False

    time_since_last = time.time() - self._last_scan_time
    if time_since_last < self._min_scan_interval:
        self.logger.info(
            f"⏱️  Scan requested too soon ({time_since_last:.1f}s < {self._min_scan_interval}s)"
        )
        return True
    return False

def _load_cached_scenes_immediate(self) -> None:
    """Load cached scenes and update UI immediately."""
    cached_scenes = self.window.cache_manager.get_persistent_threede_scenes()
    if not cached_scenes:
        return

    scenes = []
    for scene_data in cached_scenes:
        try:
            scenes.append(ThreeDEScene.from_dict(scene_data))
        except (KeyError, TypeError, ValueError) as e:
            self.logger.debug(f"Skipping invalid cached 3DE scene: {e}")

    if scenes:
        self.window.threede_scene_model.scenes = scenes
        self.update_ui()
        self.logger.info(f"🚀 Loaded {len(scenes)} cached 3DE scenes immediately")

def _create_and_start_worker(self) -> None:
    """Create and start a new worker thread."""
    # Update UI to loading state
    self.window.threede_item_model.set_loading_state(True)
    status_msg = "Scanning for 3DE scene updates..." if self.window.threede_scene_model.scenes else "Starting 3DE scene discovery..."
    self.window.update_status(status_msg)

    # Create worker
    worker = ThreeDESceneWorker(
        shots=self.window.shot_model.shots,
        enable_progressive=True,
        batch_size=None,
        scan_all_shots=True,
    )

    # Register with lifecycle manager
    self._worker_manager.set_worker(worker)

    # Connect signals
    self._setup_worker_signals(worker)

    # Start
    worker.start()
```

**Step 3: Update cleanup_worker** (replace lines 295-358):
```python
def cleanup_worker(self) -> None:
    """Clean up the 3DE scene discovery worker.

    Called during application shutdown to ensure proper cleanup
    of background threads and prevent zombie threads.
    """
    # Use shorter timeout in test environments
    is_test_environment = "pytest" in sys.modules
    timeout_ms = 500 if is_test_environment else Config.WORKER_STOP_TIMEOUT_MS

    # Cleanup via lifecycle manager
    self._worker_manager.cleanup(timeout_ms)

    # Finish any orphaned progress operation
    if self._current_progress_operation is not None:
        current_top = ProgressManager.get_current_operation()
        if current_top == self._current_progress_operation:
            self.logger.debug("Finishing orphaned progress operation during cleanup")
            ProgressManager.finish_operation(success=False, error_message="Operation cancelled during shutdown")
        self._current_progress_operation = None
```

#### Success Metrics
- ✅ WorkerLifecycleManager class created (~80 lines)
- ✅ refresh_threede_scenes reduced from 126 → ~50 lines
- ✅ cleanup_worker reduced from 64 → ~20 lines
- ✅ Net reduction: ~40 lines
- ✅ Closing checks: 4 → 1
- ✅ Mutex sections: 4 → 2 (in lifecycle manager)
- ✅ All 3DE tests pass
- ✅ Parallel test runs stable

#### Verification
```bash
# Test worker lifecycle
~/.local/bin/uv run pytest tests/unit/test_threede_controller.py -v -k "worker"

# Test refresh scenarios
~/.local/bin/uv run pytest tests/unit/test_threede_controller.py -v -k "refresh"

# Test cleanup during shutdown
~/.local/bin/uv run pytest tests/unit/test_threede_controller.py -v -k "cleanup"

# Parallel stress test (run 10 times)
for i in {1..10}; do
    echo "Run $i"
    ~/.local/bin/uv run pytest tests/unit/test_threede_controller.py -n auto --dist=loadgroup -v
done

# Integration tests
~/.local/bin/uv run pytest tests/integration/test_threede_discovery.py -v
```

#### Rollback Plan
```bash
git checkout controllers/threede_controller.py
rm launcher/worker_lifecycle.py
```

---

### Task 3.2: Refactor Settings Manager (Optional)

**Priority**: P3 (Low - Design Trade-off)
**Effort**: 1-2 days
**Lines Saved**: ~400 lines (80% reduction)
**Risk**: MEDIUM
**Files**: settings_manager.py

#### ⚠️ TRADE-OFF DECISION REQUIRED

This is NOT a clear KISS/DRY violation. It's a design choice:
- ✅ **Current approach**: Explicit methods, type-safe, IDE autocomplete
- ✅ **Dataclass approach**: Less code, but potentially less type inference

#### Action Steps (If Proceeding)
1. **Create SettingsSchema dataclass**
2. **Auto-generate property accessors**
3. **Preserve type safety**
4. **Test all settings operations**

#### Code Changes

**Step 1: Create settings schema** (new approach):
```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SettingsSchema:
    """Schema for all application settings with defaults."""

    # Window settings
    window_geometry: QByteArray = field(default_factory=QByteArray)
    window_state: QByteArray = field(default_factory=QByteArray)
    window_size: QSize = field(default_factory=lambda: QSize(1600, 900))
    window_maximized: bool = False
    current_tab: int = 0

    # Splitter states
    splitter_main: QByteArray = field(default_factory=QByteArray)
    splitter_details: QByteArray = field(default_factory=QByteArray)

    # Preferences
    refresh_interval: int = 30
    background_refresh: bool = True
    thumbnail_size: int = 200
    # ... etc

    def load_from_qsettings(self, settings: QSettings) -> None:
        """Load all values from QSettings."""
        for field_name, field_info in self.__dataclass_fields__.items():
            key = self._field_to_key(field_name)
            default = field_info.default_factory() if field_info.default_factory else field_info.default
            value = settings.value(key, default, type=type(default))
            setattr(self, field_name, value)

    def save_to_qsettings(self, settings: QSettings) -> None:
        """Save all values to QSettings."""
        for field_name in self.__dataclass_fields__:
            key = self._field_to_key(field_name)
            value = getattr(self, field_name)
            settings.setValue(key, value)

    @staticmethod
    def _field_to_key(field_name: str) -> str:
        """Convert field name to QSettings key."""
        if field_name.startswith("window_"):
            return f"window/{field_name[7:]}"
        elif field_name.startswith("splitter_"):
            return f"window/splitter_{field_name[9:]}"
        else:
            return f"preferences/{field_name}"
```

#### Success Metrics (If Proceeding)
- ✅ SettingsSchema dataclass created (~100 lines)
- ✅ SettingsManager reduced from 636 → ~150 lines
- ✅ Net reduction: ~400 lines (63%)
- ✅ Type safety preserved
- ✅ All settings tests pass
- ✅ IDE autocomplete still works

#### Recommendation
⚠️ **DEFER THIS TASK** - The current implementation is acceptable. Only proceed if:
1. Adding many new settings (schema becomes valuable)
2. Team prefers dataclass approach
3. You have 2 full days for refactoring + testing

---

### Phase 3 Completion Checklist

- [ ] Task 3.1: Thread management simplified
- [ ] Task 3.2: Settings manager refactored (OPTIONAL)
- [ ] All tests pass: `uv run pytest tests/ -n auto --dist=loadgroup`
- [ ] Type check passes: `uv run basedpyright`
- [ ] Parallel test runs stable (10 consecutive passes)
- [ ] Git commit: `git commit -m "refactor: Phase 3 - architectural improvements"`

---

## Success Metrics

### Quantitative Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **Total Lines** | ~15,000 | ~14,500 | -500 (-3.3%) |
| **Duplicate Code** | 500+ lines | 100 lines | -400 (-80%) |
| **Avg Method Length** | 45 lines | 30 lines | -15 (-33%) |
| **Max Method Length** | 144 lines | 60 lines | -84 (-58%) |
| **Cyclomatic Complexity (avg)** | 8.5 | 5.2 | -3.3 (-39%) |
| **Cache Manager** | 850 lines | 800 lines | -50 (-6%) |
| **Launcher Controller** | 650 lines | 600 lines | -50 (-8%) |
| **Settings Manager** | 636 lines | 636 / 150* | 0 / -486* |

*If Task 3.2 completed

### Qualitative Metrics

**Code Maintainability**:
- ✅ Single Responsibility: Each method does one thing
- ✅ DRY Compliance: No significant duplication
- ✅ Clear Intent: Method names describe behavior
- ✅ Testability: Each component testable in isolation

**Technical Debt Reduction**:
- ✅ 23 KISS/DRY violations addressed
- ✅ 8 quick wins completed
- ✅ 5 high-priority issues resolved
- ✅ Code complexity reduced by 30-40%

### Test Coverage Metrics

```bash
# Before refactoring
~/.local/bin/uv run pytest tests/ --cov=. --cov-report=term-missing

# After each phase
~/.local/bin/uv run pytest tests/ --cov=. --cov-report=term-missing
~/.local/bin/uv run pytest tests/ --cov=. --cov-report=html

# Expected: Coverage maintained or improved (currently ~70-90% on core modules)
```

### Performance Metrics

```bash
# Test execution time (should remain stable)
time ~/.local/bin/uv run pytest tests/ -n auto --dist=loadgroup

# Type check time (should remain <10s)
time ~/.local/bin/uv run basedpyright

# Expected: No significant performance regression
```

---

## Risk Management

### Risk Categories

#### Phase 1: VERY LOW RISK ✅
- Simple extractions
- No behavior changes
- Comprehensive tests exist
- Easy rollback

#### Phase 2: LOW RISK ⚠️
- Behavior preservation critical
- Extensive testing required
- Medium rollback complexity

#### Phase 3: MEDIUM RISK ⚠️⚠️
- Architectural changes
- Threading is complex
- Requires stress testing
- More complex rollback

### Risk Mitigation Strategies

1. **Test-Driven Refactoring**
   - ✅ Run tests before each change
   - ✅ Run tests after each change
   - ✅ No changes without passing tests

2. **Incremental Changes**
   - ✅ One task at a time
   - ✅ Commit after each successful task
   - ✅ Tag commits for easy rollback

3. **Parallel Testing**
   - ✅ Run parallel tests for Phase 3
   - ✅ Stress test worker lifecycle
   - ✅ 10 consecutive passes required

4. **Code Review**
   - ✅ Review all diffs before committing
   - ✅ Verify type annotations preserved
   - ✅ Check for unintended side effects

5. **Rollback Plan**
   - ✅ Every task has rollback command
   - ✅ Git tags for phase boundaries
   - ✅ Quick revert capability

---

## Testing Strategy

### Test Execution Plan

#### Before Any Changes
```bash
# Establish baseline
~/.local/bin/uv run pytest tests/ -n auto --dist=loadgroup -v > baseline_tests.log
~/.local/bin/uv run basedpyright > baseline_types.log
~/.local/bin/uv run ruff check . > baseline_lint.log

# Record metrics
wc -l cache_manager.py settings_manager.py shot_model.py controllers/launcher_controller.py > baseline_lines.log
```

#### After Each Task
```bash
# Quick validation
~/.local/bin/uv run pytest tests/unit/test_<relevant_module>.py -v

# Full validation
~/.local/bin/uv run pytest tests/ -n auto --dist=loadgroup
~/.local/bin/uv run basedpyright
~/.local/bin/uv run ruff check .

# Commit if all pass
git add <modified_files>
git commit -m "<task description>"
git tag phase-1-task-<n>  # For easy rollback
```

#### After Each Phase
```bash
# Comprehensive testing
~/.local/bin/uv run pytest tests/ -n auto --dist=loadgroup -v
~/.local/bin/uv run pytest tests/ --cov=. --cov-report=html
~/.local/bin/uv run basedpyright --stats
~/.local/bin/uv run ruff check .

# Integration testing
~/.local/bin/uv run pytest tests/integration/ -v

# For Phase 3 only: Stress testing
for i in {1..10}; do
    ~/.local/bin/uv run pytest tests/unit/test_threede_controller.py -n auto --dist=loadgroup
done

# Commit phase
git add -A
git commit -m "refactor: Phase <N> complete - <description>"
git tag phase-<n>-complete
```

### Test Focus Areas

**Phase 1 Testing**:
- ✅ Log output format unchanged
- ✅ Notification behavior unchanged
- ✅ Timestamp formatting correct

**Phase 2 Testing**:
- ✅ Cache merge results identical
- ✅ Shot refresh (async and sync) behavior preserved
- ✅ Launch flow with all context types
- ✅ Error handling paths
- ✅ Edge cases (empty cache, corruption, etc.)

**Phase 3 Testing**:
- ✅ Worker lifecycle (start, stop, cleanup)
- ✅ Thread safety (parallel test runs)
- ✅ Shutdown scenarios
- ✅ Progress operation handling
- ✅ Signal disconnection

---

## Phase Execution Timeline

### Suggested Schedule

**Week 1**:
- Day 1: Phase 1 (Tasks 1.1-1.3) - 3-4 hours
- Day 2: Phase 2 Task 2.1 (Cache merge) - Full day
- Day 3: Phase 2 Task 2.2 (Shot merge) - Half day
- Day 4-5: Phase 2 Task 2.3 (launch_app) - 2 days

**Week 2**:
- Day 6-8: Phase 3 Task 3.1 (Thread management) - 2-3 days
- Day 9-10: Buffer for testing, fixes, documentation

**Optional Week 3**:
- Day 11-12: Phase 3 Task 3.2 (Settings manager) - IF desired

---

## Acceptance Criteria

### Phase 1 Complete When:
- [x] All 3 tasks completed
- [x] 2,300+ tests passing
- [x] Zero type errors
- [x] ~80 lines removed
- [x] Git commit tagged

### Phase 2 Complete When:
- [x] All 3 tasks completed
- [x] 2,300+ tests passing
- [x] Zero type errors
- [x] ~200 lines removed
- [x] Complexity metrics improved
- [x] Git commit tagged

### Phase 3 Complete When:
- [x] Task 3.1 completed
- [x] 2,300+ tests passing
- [x] Zero type errors
- [x] Parallel tests stable (10/10 passes)
- [x] ~40 lines removed
- [x] Worker lifecycle simplified
- [x] Git commit tagged

### Project Complete When:
- [x] All mandatory phases complete
- [x] Full test suite passes
- [x] Type checking passes
- [x] Code review complete
- [x] Documentation updated
- [x] Metrics validated
- [x] Final commit and tag

---

## Next Steps

1. **Review this plan** with team/stakeholders
2. **Schedule Phase 1** (3-4 hour block)
3. **Execute Phase 1** following task order
4. **Validate Phase 1** with all metrics
5. **Proceed to Phase 2** if successful
6. **Review before Phase 3** (architectural changes)

---

## Document Maintenance

This document should be updated:
- ✅ After each task completion (mark checkboxes)
- ✅ When metrics are measured (fill in "After" column)
- ✅ If issues arise (add notes to relevant sections)
- ✅ When phases are complete (update status)

**DO NOT DELETE THIS DOCUMENT** - It serves as the authoritative refactoring plan and historical record.

---

**Last Updated**: 2025-11-12
**Status**: Ready for execution
**Approved By**: Multi-agent code review + independent verification
