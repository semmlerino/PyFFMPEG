# Phase 2: Duplicate Model Updates Fix - Issues 2, 3, 5

**Status:** ✅ COMPLETED
**Date:** 2025-11-01

## Summary

Fixed duplicate model updates and thumbnail scheduling caused by duplicate signal emissions during initial shot loading. The root cause was emitting both `shots_changed` and `shots_loaded` signals for the same event, causing the UI to update twice with identical data.

## Problem

### Issue 2: Duplicate Model Updates (CRITICAL)

**Original confusing log sequence:**
```
10:05:50 - shot_item_model.ShotItemModel - INFO - Model updated: 30 items, thumbnails: 0 preserved, 0 evicted
10:05:50 - shot_item_model.ShotItemModel - INFO - Model updated: 30 items, thumbnails: 0 preserved, 0 evicted
```

**Problem:** ShotItemModel.set_items() called twice in rapid succession with identical data, causing:
- Duplicate "Model updated" logs
- Duplicate thumbnail load scheduling (Issue 3)
- Duplicate thumbnail load checks (Issue 5)
- Wasted CPU cycles
- Potential UI flicker

### Issue 3: Duplicate Thumbnail Scheduling (HIGH)

**Symptoms:**
```
10:05:50 - shot_item_model.ShotItemModel - DEBUG - Scheduling thumbnail load timer for 30 items
10:05:50 - shot_item_model.ShotItemModel - DEBUG - Timer scheduled successfully
[repeated]
```

**Problem:** Direct consequence of Issue 2 - each model update schedules thumbnail loading.

### Issue 5: Redundant Thumbnail Load Checks (LOW)

**Symptoms:**
```
10:05:51 - shot_item_model.ShotItemModel - DEBUG - _do_load_visible_thumbnails: checking 30 items
[appears twice]
```

**Problem:** Symptom of duplicate thumbnail scheduling from Issue 3.

---

## Root Cause Analysis

### Signal Flow Investigation

**Step 1: Traced the duplicate model update calls**

Found two callers of `shot_item_model.set_shots()`:
1. `main_window.py:403` - Initial setup during MainWindow construction
2. `refresh_orchestrator.py:212` - Called by `_refresh_shot_display()`

**Step 2: Found duplicate signal handlers**

The `_refresh_shot_display()` method is called from TWO signal handlers:
```python
# refresh_orchestrator.py
def handle_shots_loaded(self, shots: list[Shot]) -> None:
    self.logger.info(f"Shots loaded signal received: {len(shots)} shots")
    self._refresh_shot_display()  # ← Calls set_shots()
    self._update_status(f"Loaded {len(shots)} shots")
    NotificationManager.info(f"{len(shots)} shots loaded")

def handle_shots_changed(self, shots: list[Shot]) -> None:
    self.logger.info(f"Shots changed signal received: {len(shots)} shots")
    self._refresh_shot_display()  # ← Calls set_shots()
    self._update_status(f"Shot list updated: {len(shots)} shots")
    NotificationManager.success(f"Refreshed {len(shots)} shots")
```

**Step 3: Found signal connections in MainWindow**

```python
# main_window.py
_ = self.shot_model.shots_loaded.connect(self._on_shots_loaded)
_ = self.shot_model.shots_changed.connect(self._on_shots_changed)

def _on_shots_loaded(self, shots: list[Shot]) -> None:
    # ... code ...
    self.refresh_orchestrator.handle_shots_loaded(shots)

def _on_shots_changed(self, shots: list[Shot]) -> None:
    # ... code ...
    self.refresh_orchestrator.handle_shots_changed(shots)
```

**Step 4: Discovered duplicate signal emission in ShotModel**

Found the smoking gun in `shot_model.py` at `_on_shots_loaded()` method:

```python
# BEFORE (WRONG):
# Emit structural change signal ONLY if shots added/removed
if merge_result.has_changes:
    self.shots_changed.emit(self.shots)  # ← Emits first signal

# Special case for first load
if old_count == 0 and len(self.shots) > 0:
    self.shots_loaded.emit(self.shots)   # ← Emits second signal
```

**During initial load with expired cache:**
- `old_count == 0` (started with no shots)
- Fresh data loads 30 shots
- `merge_result.has_changes == True` (0 → 30 is a structural change)
- **Both conditions are TRUE!**
- Result: BOTH signals emitted for the same event

**Signal propagation path:**
```
shot_model._on_shots_loaded()
  ├─→ shots_changed.emit()
  │     └─→ main_window._on_shots_changed()
  │           └─→ refresh_orchestrator.handle_shots_changed()
  │                 └─→ _refresh_shot_display()
  │                       └─→ shot_item_model.set_shots()
  │                             └─→ base_item_model.set_items()
  │                                   ├─→ "Model updated: 30 items..." (LOG #1)
  │                                   └─→ "Scheduling thumbnail load..." (LOG #1)
  │
  └─→ shots_loaded.emit()
        └─→ main_window._on_shots_loaded()
              └─→ refresh_orchestrator.handle_shots_loaded()
                    └─→ _refresh_shot_display()
                          └─→ shot_item_model.set_shots()
                                └─→ base_item_model.set_items()
                                      ├─→ "Model updated: 30 items..." (LOG #2)
                                      └─→ "Scheduling thumbnail load..." (LOG #2)
```

---

## Changes Made

### Fix: Make Signal Emissions Mutually Exclusive

**File:** `shot_model.py` - `_on_shots_loaded()` method (lines 386-394)

**Before:**
```python
# Emit structural change signal ONLY if shots added/removed
if merge_result.has_changes:
    self.shots_changed.emit(self.shots)

# Special case for first load
if old_count == 0 and len(self.shots) > 0:
    self.shots_loaded.emit(self.shots)
```

**After:**
```python
# Choose the appropriate signal based on context:
# - First load (0 → N): Use shots_loaded
# - Subsequent updates with changes: Use shots_changed
if old_count == 0 and len(self.shots) > 0:
    # Special case for first load - emit shots_loaded
    self.shots_loaded.emit(self.shots)
elif merge_result.has_changes:
    # Structural change after initial load - emit shots_changed
    self.shots_changed.emit(self.shots)
```

**Key Change:** Changed from two `if` statements to `if`/`elif`, making the signals mutually exclusive:
- **First load** (0 shots → N shots): Emit `shots_loaded` ONLY
- **Subsequent updates** with changes: Emit `shots_changed` ONLY
- **Never emit both** for the same event

---

## Expected Log Output After Changes

### Scenario 1: Cache Expired - Initial Load (Most Common)

**Before Fix (WRONG - duplicate updates):**
```
10:05:50 - shot_model.ShotModel - INFO - Background refresh: 30 shots from workspace, 30 shots from persistent cache
10:05:50 - shot_model.ShotModel - INFO - Shot merge: 30 new, 0 removed, 30 total
10:05:50 - shot_model.ShotModel - INFO - Background load complete: 0 → 30 shots (+30 new, -0 removed)
10:05:50 - refresh_orchestrator.RefreshOrchestrator - INFO - Shots changed signal received: 30 shots
10:05:50 - shot_item_model.ShotItemModel - INFO - Model updated: 30 items, thumbnails: 0 preserved, 0 evicted
10:05:50 - shot_item_model.ShotItemModel - DEBUG - Scheduling thumbnail load timer for 30 items
10:05:50 - refresh_orchestrator.RefreshOrchestrator - INFO - Shots loaded signal received: 30 shots
10:05:50 - shot_item_model.ShotItemModel - INFO - Model updated: 30 items, thumbnails: 0 preserved, 0 evicted
10:05:50 - shot_item_model.ShotItemModel - DEBUG - Scheduling thumbnail load timer for 30 items
```

**After Fix (CORRECT - single update):**
```
10:05:50 - shot_model.ShotModel - INFO - Background refresh: 30 shots from workspace, 30 shots from persistent cache
10:05:50 - shot_model.ShotModel - INFO - Shot merge: 30 new, 0 removed, 30 total
10:05:50 - shot_model.ShotModel - INFO - Background load complete: 0 → 30 shots (+30 new, -0 removed)
10:05:50 - refresh_orchestrator.RefreshOrchestrator - INFO - Shots loaded signal received: 30 shots
10:05:50 - shot_item_model.ShotItemModel - INFO - Model updated: 30 items, thumbnails: 0 preserved, 0 evicted
10:05:50 - shot_item_model.ShotItemModel - DEBUG - Scheduling thumbnail load timer for 30 items
```

### Scenario 2: Subsequent Refresh with Changes

**After Fix (CORRECT):**
```
10:06:30 - shot_model.ShotModel - INFO - Background refresh: 32 shots from workspace, 30 shots from persistent cache
10:06:30 - shot_model.ShotModel - INFO - Shot merge: 2 new, 0 removed, 32 total
10:06:30 - shot_model.ShotModel - INFO - Background load complete: 30 → 32 shots (+2 new, -0 removed)
10:06:30 - refresh_orchestrator.RefreshOrchestrator - INFO - Shots changed signal received: 32 shots
10:06:30 - shot_item_model.ShotItemModel - INFO - Model updated: 32 items, thumbnails: 30 preserved, 0 evicted
10:06:30 - shot_item_model.ShotItemModel - DEBUG - Scheduling thumbnail load timer for 32 items
```

Note: Only `shots_changed` signal emitted (not first load anymore), and only ONE model update.

### Scenario 3: Refresh with No Changes

**After Fix (CORRECT):**
```
10:07:00 - shot_model.ShotModel - INFO - Background refresh: 32 shots from workspace, 32 shots from persistent cache
10:07:00 - shot_model.ShotModel - INFO - Shot merge: 0 new, 0 removed, 32 total
10:07:00 - shot_model.ShotModel - INFO - Async refresh: no changes detected
```

Note: No signals emitted when there are no changes, so no model updates at all (optimal!).

---

## Benefits

1. **Eliminated Duplicate Operations** - Model update happens exactly once per data change
2. **Reduced CPU Usage** - No redundant model resets, thumbnail scheduling, or UI updates
3. **Cleaner Signal Semantics:**
   - `shots_loaded`: Initial load only (0 → N shots)
   - `shots_changed`: Subsequent structural changes (add/remove shots)
4. **Fixed Thumbnail Scheduling** - Thumbnails scheduled once per model update (Issues 3 & 5 solved)
5. **Better Performance** - Eliminated unnecessary work during startup
6. **Clearer Logs** - No confusing duplicate "Model updated" messages

---

## Technical Analysis

### Why the Original Logic Was Wrong

The original code had TWO independent `if` statements:
```python
if merge_result.has_changes:      # Condition A
    self.shots_changed.emit()

if old_count == 0 and len() > 0:  # Condition B
    self.shots_loaded.emit()
```

During initial load: **Both conditions can be true simultaneously!**
- Condition A: True (0 → 30 is a change)
- Condition B: True (started with 0, now have 30)
- Result: **Both signals fire**

### Why the Fix Is Correct

The fixed code uses `if`/`elif`:
```python
if old_count == 0 and len() > 0:  # First load
    self.shots_loaded.emit()
elif merge_result.has_changes:     # Subsequent changes
    self.shots_changed.emit()
```

**Mutual exclusivity guarantees:**
- If it's the first load → Emit `shots_loaded`, skip the `elif`
- If NOT first load AND has changes → Emit `shots_changed`
- **Never emit both**

### Signal Semantics

**`shots_loaded` signal:**
- Meaning: "Shots have been initially loaded into the model"
- When: First load only (empty → populated)
- Listeners: UI components that need initial setup

**`shots_changed` signal:**
- Meaning: "The shot list structure has changed (additions/removals)"
- When: After initial load, when shots are added/removed
- Listeners: UI components that need to react to structural changes

The fix ensures these signals maintain their distinct semantic meanings without overlap.

---

## Files Modified

- `shot_model.py` - 1 location (lines 386-394)

---

## Related Issues Resolved

- ✅ **Issue 2**: Duplicate model updates (CRITICAL) - **FIXED**
- ✅ **Issue 3**: Duplicate thumbnail scheduling (HIGH) - **FIXED** (consequence of Issue 2)
- ✅ **Issue 5**: Redundant thumbnail load checks (LOW) - **FIXED** (consequence of Issue 2)

---

## Verification Steps

To verify this fix:

1. **Run the application** with expired cache (wait 1440 minutes or delete cache file)
2. **Check startup logs** for:
   - Single "Model updated" log (not duplicate)
   - Single "Scheduling thumbnail load timer" log (not duplicate)
   - Only ONE of: "Shots loaded signal" OR "Shots changed signal" (not both)
3. **Perform a manual refresh** (F5 key) and verify:
   - If no changes: No model update
   - If changes: Single "Shots changed signal", single model update
4. **Check performance**:
   - Startup time not degraded
   - No UI flicker during initial load
   - Thumbnails load smoothly

---

## Next Steps

Phase 2 complete. Ready to proceed with Phase 3:
- Investigate multiple Finder object instantiations (Issue 4)
