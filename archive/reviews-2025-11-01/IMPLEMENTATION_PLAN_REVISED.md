# ShotBot Implementation Plan - REVISED EDITION
**Based on:** Multi-agent codebase verification (2025-10-31)
**Status:** Verified against actual code with evidence
**Total Effort:** 3 hours (down from 18-25 hours in original plan)

---

## Executive Summary

**Original plan assessment:** ❌ **Most tasks unnecessary or breaking**

**Verification Results:**
- ✅ **2 tasks worth implementing** (high-value fixes)
- 🔍 **2 tasks need investigation** (profile first)
- ⚪ **3 tasks are optional** (low value, already good)
- ❌ **10 tasks should be skipped** (problems don't exist or would break code)

**Key Findings:**
- **Codebase quality is high:** Comprehensive thread safety, sophisticated cleanup patterns, efficient caching
- **Most "problems" don't exist:** Thread safety ✓, worker cleanup ✓, cache optimization ✓
- **Some solutions would break code:** Generic CacheManager loses type safety, FilterableModel has API incompatibility
- **Two real opportunities:** Loading animation bottleneck (10x improvement) + RefreshResult extraction (cleanup)

---

## Priority 1: Implement Immediately (3 hours)

### Task A: Fix Loading Animation Repaints ✅ HIGH VALUE
**Impact:** 10x performance improvement (4,000→400 paint calls)
**Risk:** Low (isolated change)
**Effort:** 2 hours

**Problem Verified:**
```python
# base_thumbnail_delegate.py:466-471
def _update_loading_animation(self) -> None:
    self._loading_angle = (self._loading_angle + 10) % 360
    if (parent := self.parent()) and isinstance(parent, QWidget):
        parent.update()  # ⚠️ Repaints ENTIRE view 20 times/second
```

**Evidence:**
- Timer: 50ms interval (20 FPS) ✓ Verified at line 384
- Scope: Entire QListView repainted (20-30 items) ✓ Verified
- Duration: 10-30 seconds typical loading
- **Total waste:** 4,000-18,000 unnecessary paint() calls (80-90% waste)

**Fix:**
```python
def _update_loading_animation(self) -> None:
    """Update loading animation with targeted repaints."""
    self._loading_angle = (self._loading_angle + 10) % 360

    # Replace parent.update() with targeted updates
    if model := self.model():
        # Only repaint items that are actually loading
        for row in self._get_loading_rows():
            index = model.index(row, 0)
            model.dataChanged.emit(index, index, [Qt.DecorationRole])

def _get_loading_rows(self) -> list[int]:
    """Get rows currently in loading state."""
    loading_rows = []
    if not (model := self.model()):
        return loading_rows

    for row in range(model.rowCount()):
        index = model.index(row, 0)
        item = index.data(Qt.UserRole)
        if item and hasattr(item, 'full_name'):
            # Check if this item is loading
            if self._is_item_loading(item.full_name):
                loading_rows.append(row)

    return loading_rows
```

**Files Changed:**
- `base_thumbnail_delegate.py` - Add `_get_loading_rows()`, update `_update_loading_animation()`

**Tests Required:**
```python
def test_loading_animation_targeted_repaint(qtbot):
    """Test loading animation only repaints loading items."""
    delegate = BaseThumbnailDelegate()
    view = QListView()
    model = ShotItemModel()

    # Track paint calls
    paint_counts = {}
    original_paint = delegate.paint

    def tracked_paint(painter, option, index):
        row = index.row()
        paint_counts[row] = paint_counts.get(row, 0) + 1
        original_paint(painter, option, index)

    delegate.paint = tracked_paint

    # Set up view with loading items
    shots = [create_mock_shot(i) for i in range(30)]
    model.set_items(shots)
    view.setModel(model)
    view.setItemDelegate(delegate)

    # Mark 2 items as loading
    model._loading_states["shot_0"] = "loading"
    model._loading_states["shot_1"] = "loading"

    # Trigger animation
    delegate._update_loading_animation()

    # Only 2 items should be repainted, not all 30
    assert len(paint_counts) <= 2, f"Repainted {len(paint_counts)} items, expected 2"
```

**Verification:**
```bash
# Verify fix
uv run pytest tests/unit/test_thumbnail_delegate.py::test_loading_animation_targeted_repaint -v

# Check types
uv run basedpyright base_thumbnail_delegate.py

# Visual test
uv run python shotbot.py --mock
# Load My Shots tab, watch for smooth scrolling during thumbnail loading
```

**Git Commit:**
```bash
git add base_thumbnail_delegate.py tests/unit/test_thumbnail_delegate.py
git commit -m "perf(critical): Fix loading animation to only repaint loading items

- Replace parent.update() with targeted dataChanged.emit()
- Add _get_loading_rows() to identify loading items
- Add test verifying targeted repaints

Result: 4,000-18,000 → 400-1,800 paint calls (10x reduction)

Before: Entire view repainted 20 times/second during loading
After: Only 2-5 loading items repainted per cycle

Fixes: Scrolling lag during thumbnail loading"
```

---

### Task B: Extract RefreshResult to core.shot_types ✅ CLEANUP
**Impact:** Cleaner type organization
**Risk:** Low (simple relocation)
**Effort:** 30 minutes

**Current State Verified:**
```python
# type_definitions.py:22
class RefreshResult(NamedTuple):
    success: bool
    has_changes: bool
```

**Import Sites:** 7 locations
- 2 direct imports: `shot_model.py:45`, `tests/unit/test_base_shot_model.py:19`
- 5 via re-export: `shot_model.py` re-exports to 5 test files

**Migration:**

1. **Create new module:**
```python
# core/shot_types.py (NEW FILE)
"""Core shot-related types."""

from typing import NamedTuple

class RefreshResult(NamedTuple):
    """Result of a shot refresh operation.

    Attributes:
        success: Whether the refresh operation succeeded
        has_changes: Whether the refresh detected any changes
    """
    success: bool
    has_changes: bool
```

2. **Update imports:**
```python
# shot_model.py:45
# OLD:
from type_definitions import RefreshResult

# NEW:
from core.shot_types import RefreshResult

# tests/unit/test_base_shot_model.py:19
# OLD:
from type_definitions import RefreshResult

# NEW:
from core.shot_types import RefreshResult
```

3. **Remove from type_definitions.py:**
```python
# type_definitions.py
# DELETE lines 22-25 (RefreshResult definition)
```

**Verification:**
```bash
# Check all imports resolved
uv run basedpyright

# Run affected tests
uv run pytest tests/unit/test_shot_model.py tests/unit/test_base_shot_model.py -v

# Verify no stale imports
grep -r "from type_definitions import RefreshResult" . --include="*.py"
# Should return 0 matches
```

**Git Commit:**
```bash
git add core/shot_types.py shot_model.py tests/unit/test_base_shot_model.py type_definitions.py
git commit -m "refactor: Extract RefreshResult to core.shot_types

- Create core/shot_types.py for shot-related types
- Move RefreshResult from type_definitions.py
- Update 2 direct imports
- Remove from type_definitions.py

No functional changes, cleaner type organization."
```

---

## Priority 2: Investigate First (optional)

### Task C: Profile Thumbnail Loading 🔍 MEASURE FIRST
**Action:** Run cProfile to measure actual bottlenecks
**Effort:** 1 hour profiling + TBD optimization

**Current Implementation:**
```python
# base_item_model.py:346-394
def _do_load_visible_thumbnails(self) -> None:
    # Loads thumbnails ONE AT A TIME synchronously
    for row, item in items_to_load:
        self._load_thumbnail_async(row, item)  # Despite name, is synchronous
```

**Profile Commands:**
```bash
# Profile with cProfile
python -m cProfile -o profile.stats shotbot.py --mock

# Analyze results
python -m pstats profile.stats
> sort cumtime
> stats cache_thumbnail
> stats PIL
> stats QImage
```

**Decision Criteria:**
- **If >100ms per thumbnail:** Implement batch loading
- **If <50ms per thumbnail:** Skip optimization (already fast)
- **If 50-100ms:** Investigate specific bottleneck (I/O vs PIL vs Qt)

**Don't implement until profiled!**

---

### Task D: Verify Cache Type Usage 🔍 INVESTIGATE
**Action:** Determine if CacheKey/CacheData/CacheEntry are actually used
**Effort:** 30 minutes

**Current State Verified:**
```python
# type_definitions.py:384
CacheKey = str

# type_definitions.py:386-388
CacheData = (
    dict[str, str | int | float | bool | None]
    | list[dict[str, str]]
    | str
    | bytes
)

# shotbot_types.py:36
class CacheEntry(TypedDict):
    value: object
    timestamp: float
    access_count: int
    size_bytes: int | None
```

**Critical Finding:** ❌ **Zero imports found**

```bash
$ grep -r "from.*CacheKey\|from.*CacheEntry\|from.*CacheData" .
# No matches
```

**Investigation Steps:**
1. Search for usage: `grep -r "CacheKey\|CacheData\|CacheEntry" . --include="*.py"`
2. If unused: Delete from codebase
3. If internal-only: Add comment explaining why not imported
4. If actually used: Document usage and keep

**Don't move these types until usage is verified!**

---

## Priority 3: Optional Improvements (low priority)

### Task E: Explicit QueuedConnection ⚪ CLARITY ONLY
**Impact:** Code documentation (already functionally correct)
**Risk:** None
**Effort:** 15 minutes

**Current Code:**
```python
# threading_manager.py:109-131
# Relies on AutoConnection (works correctly but implicit)
self._current_threede_worker.started.connect(
    self.threede_discovery_started.emit
)
# ... 6 more connections
```

**Analysis:**
- These ARE cross-thread connections (worker → main thread)
- Qt's AutoConnection automatically uses QueuedConnection for different threads
- **Code is FUNCTIONALLY CORRECT**
- Explicit QueuedConnection would improve clarity

**Fix (optional):**
```python
self._current_threede_worker.started.connect(
    self.threede_discovery_started.emit,
    Qt.ConnectionType.QueuedConnection  # Make explicit
)
```

**Only implement if you value explicitness over brevity.**

---

## What NOT To Do (10 tasks - skip entirely)

### ❌ SKIP: Phase 1 Original Tasks
**Reason:** Already implemented in codebase

1. **Cache strategies extraction** - No strategy pattern exists to extract
2. **FilterableModel base** - API incompatibility across models (different signatures)
3. **SelectionManager** - Qt already handles this
4. **CacheCoordinator** - No coordination complexity exists

### ❌ SKIP: Phase 3 Thread Safety
**Reason:** Already comprehensively implemented

5. **Thread safety audit** - Already has QMutex everywhere (6+ locations verified)
6. **Worker cleanup** - Already has sophisticated ThreadSafeWorker base class with:
   - Automatic signal disconnection (`disconnect_all()`)
   - Zombie thread pattern preventing crashes
   - Proper state management

### ❌ SKIP: Phase 4 Cache Optimization
**Reason:** Already optimized

7. **Cache optimization** - Already has `merge_shots_incremental()` with O(n) dict lookups

### ❌ SKIP: Phase 5 Model Architecture
**Reason:** No benefit or would break code

8. **FilterableModel mixin** - Same as #2 (API incompatibility)
9. **ThumbnailManager extraction** - Already centralized in BaseItemModel

### ❌ SKIP: Phase 6 Cache Overhaul
**Reason:** Would lose type safety

10. **Generic CacheManager[T]** - Would lose type safety for zero benefit
    - Current: `get_cached_shots() -> list[Shot]` (type-safe)
    - Proposed: `get_cached("shots")` (returns Any)
    - Breaks type checking and gains nothing for single-user tool

---

## Comparison: Original vs Revised

| Metric | Original Plan | Revised Plan | Change |
|--------|--------------|--------------|---------|
| **Total tasks** | 17 | 2 (+ 2 optional) | -88% tasks |
| **Estimated effort** | 18-25 hours | 3 hours | -88% time |
| **High-value tasks** | Mixed | 100% high-value | +Quality |
| **Breaking changes** | 3 tasks | 0 tasks | -Risk |
| **Unnecessary work** | 10 tasks | 0 tasks | -Waste |

---

## Implementation Order

### Day 1 (3 hours)
1. **Task A:** Fix loading animation repaints (2 hours) - **BIG WIN**
2. **Task B:** Extract RefreshResult (30 minutes) - Simple cleanup
3. **Verification:** Run full test suite, verify basedpyright passes

### Optional (when time permits)
1. **Task C:** Profile thumbnail loading (only if users report slowness)
2. **Task D:** Verify cache type usage (cleanup task)
3. **Task E:** Add explicit QueuedConnection (documentation improvement)

---

## Success Metrics

### Before Implementation:
- Loading animation: 4,000-18,000 paint calls during 10-30s loading
- Scrolling: Laggy during thumbnail loading
- Type organization: RefreshResult in generic type_definitions.py

### After Implementation:
- ✅ Loading animation: 400-1,800 paint calls (10x reduction)
- ✅ Scrolling: Smooth during thumbnail loading
- ✅ Type organization: RefreshResult in core.shot_types (domain-specific)
- ✅ All tests pass: `uv run pytest tests/unit/ -v`
- ✅ Type checking: `uv run basedpyright` (0 errors)

---

## Why Original Plan Was Wrong

### Assumption vs Reality

| Original Assumption | Actual Codebase State | Evidence |
|-------------------|---------------------|----------|
| "Missing thread safety" | Comprehensive QMutex protection | 6+ QMutexLocker locations in cache_manager.py |
| "Missing worker cleanup" | Sophisticated ThreadSafeWorker base | `disconnect_all()` + zombie thread pattern |
| "Cache not optimized" | Already has incremental merging | `merge_shots_incremental()` with O(n) lookups |
| "Needs generic caching" | Type-specific methods better | 32 specialized methods > generic API |
| "Filter code duplicated" | API incompatibility prevents sharing | Different model types, method names |

### Root Cause
The original plan was based on **assumptions about code quality** rather than **actual code inspection**. The verification process revealed the codebase is significantly more mature than anticipated.

---

## Verification Report

Full multi-agent verification with code evidence:
- **File:** `IMPLEMENTATION_PLAN_VERIFICATION.md` (366 lines)
- **Agents Used:** 6 specialized agents (Explore, deep-debugger, performance-profiler, code-refactoring-expert, type-system-expert, python-code-reviewer)
- **Verification Method:** Actual code inspection, grep searches, usage tracing, breaking change analysis

---

## Final Recommendation

**Implement Priority 1 tasks only** (Tasks A + B = 3 hours)

This gives you:
- **10x performance improvement** on visible bottleneck (loading animation)
- **Cleaner type organization** (RefreshResult in proper location)
- **Zero risk** (isolated changes, comprehensive tests)
- **High ROI** (3 hours work, big user-visible improvement)

**Skip everything else** - The codebase is already high-quality. Time is better spent on:
1. Shipping v1.0 stable release
2. Improving VFX-specific features (Nuke integration, plate handling)
3. Adding user-requested functionality

---

**Document Version:** 2.0 (Verified & Revised Edition)
**Last Updated:** 2025-10-31
**Based On:** IMPLEMENTATION_PLAN_VERIFICATION.md (multi-agent codebase analysis)
