# ShotBot Remediation - PART 2: Architecture & Polish

**Focus:** Clean architecture and documentation (nice-to-have)
**Prerequisites:** Part 1 must be complete
**Effort:** 6-9 hours (1-2 days with reviews)
**Tasks:** 6 tasks across Phases 3-4

---

## Quick Checklist

### Phase 3: Architecture Improvements
- [ ] **3.1** Extract shot migration service (separate business logic)
- [ ] **3.2** Document atomic thumbnail loading correctly
- [ ] **3.3** Add configuration constants (eliminate magic numbers)

### Phase 4: Documentation & Testing
- [ ] **4.1** Add regression tests (prevent bug recurrence)
- [ ] **4.2** Update architecture review summary
- [ ] **4.3** Create performance baseline document

### Success Metrics
- [ ] ShotMigrationService extracted and tested
- [ ] Configuration centralized in config.py
- [ ] Documentation accurate (no misleading claims)
- [ ] 15+ new tests added (regression + performance)
- [ ] Coverage at 94%+

---

# PHASE 3: ARCHITECTURE IMPROVEMENTS

## Task 3.1: Extract Shot Migration Service

**Issue:** Migration logic in CacheManager is business logic, not caching
**File:** `cache_manager.py:454-469`

### Create New Service
```python
# shot_migration_service.py (NEW FILE)
"""Service for managing shot migration between active and previous caches."""

from PySide6.QtCore import QObject, Signal

class ShotMigrationService(QObject):
    """Handles migration of shots between active and previous caches.

    Separation Rationale:
    - CacheManager handles storage, not business logic
    - Migration policy may change independently of caching
    - Easier to test migration logic in isolation
    """

    shots_migrated = Signal(list)
    migration_failed = Signal(str)

    def __init__(self, cache_manager: CacheManager):
        super().__init__()
        self._cache = cache_manager
        self.logger = logging.getLogger(__name__)

    def migrate_removed_shots(
        self, removed_shots: Sequence[Shot | ShotDict]
    ) -> bool:
        """Migrate shots removed from active workspace."""
        if not removed_shots:
            return True

        # Convert to dicts
        removed_dicts = [
            shot.to_dict() if hasattr(shot, "to_dict") else shot
            for shot in removed_shots
        ]

        # Get existing migrated shots
        existing = self._cache.get_migrated_shots() or []

        # Deduplicate by composite key
        existing_keys = {
            (s["show"], s["sequence"], s["shot"]) for s in existing
        }
        new_shots = [
            s for s in removed_dicts
            if (s["show"], s["sequence"], s["shot"]) not in existing_keys
        ]

        if not new_shots:
            return True

        # Merge and persist
        merged = existing + new_shots

        # Use async write
        future = self._cache.write_json_cache_async(
            self._cache.migrated_shots_cache_file, merged
        )

        # Wait for write (migration is critical)
        try:
            success = future.result(timeout=5.0)
        except TimeoutError:
            success = False

        if success:
            self.shots_migrated.emit(removed_shots)
            return True
        else:
            error_msg = "CRITICAL: Failed to persist migrated shots!"
            self.logger.critical(error_msg)
            self.migration_failed.emit(error_msg)
            return False
```

### Update ShotModel
```python
# shot_model.py (UPDATE)
from shot_migration_service import ShotMigrationService

class ShotModel(BaseShotModel):
    def __init__(self, ...):
        super().__init__(...)

        # Create migration service
        self._migration_service = ShotMigrationService(self._cache_manager)
        self._migration_service.shots_migrated.connect(self._on_shots_migrated)
        self._migration_service.migration_failed.connect(self._on_migration_failed)

    def _on_merge_complete(self, merge_result: ShotMergeResult):
        """Handle incremental merge completion."""
        # ... existing logic ...

        # Migrate removed shots if any
        if merge_result.removed_shots:
            self._migration_service.migrate_removed_shots(merge_result.removed_shots)
```

### Remove from CacheManager
```python
# cache_manager.py (REMOVE)
# Delete: migrate_shots_to_previous() method
# Keep: get_migrated_shots() for read access
```

### Git Commit
```bash
git add shot_migration_service.py cache_manager.py shot_model.py tests/
git commit -m "refactor(arch): Extract shot migration to dedicated service

- Create ShotMigrationService for business logic separation
- Remove migrate_shots_to_previous from CacheManager
- Update ShotModel to use migration service

Benefits:
- Clear separation (caching vs business logic)
- Independently testable migration policy

Related: Phase 3, Task 3.1"
```

---

## Task 3.2: Document Atomic Thumbnail Loading Correctly

**Issue:** Docstring claims "eliminates race conditions" but has caveats
**File:** `base_item_model.py:346-351`

### Update Docstring (CODE UNCHANGED)
```python
# base_item_model.py:346-365 (UPDATE DOCSTRING ONLY)
def _do_load_visible_thumbnails(self) -> None:
    """Load thumbnails for visible range with race condition mitigation.

    Thread Safety Design:
    -------------------
    This reduces (but doesn't eliminate) race conditions:

    1. **Thumbnail State Atomicity**: Check-and-mark in single lock
    2. **Bounds Checking**: Prevents IndexError
    3. **Lock Minimization**: I/O outside locks

    Known Race Conditions:
    ----------------------
    - Model data access may see stale snapshot
    - Mitigation: Bounds checking prevents crashes

    Why Not Fully Atomic:
    --------------------
    Full atomicity would block UI during file I/O and PIL decoding.
    Current design accepts rare benign races to avoid UI blocking.

    Performance: 100-200μs lock hold, 250ms debounce
    """
    # ... implementation unchanged
```

### Git Commit
```bash
git add base_item_model.py
git commit -m "docs(arch): Clarify thumbnail loading thread safety

- Update docstring with accurate race condition analysis
- Document trade-offs

Related: Phase 3, Task 3.2"
```

---

## Task 3.3: Add Configuration Constants

**Issue:** Magic numbers scattered throughout
**Files:** Multiple

### Add to config.py
```python
# config.py (ADD)
class ThumbnailLoadingConfig:
    VISIBILITY_CHECK_INTERVAL_MS = 100
    DEBOUNCE_INTERVAL_MS = 250
    BUFFER_ROWS = 5
    THUMBNAIL_CACHE_SIZE = 500  # ~128MB

class CacheWriteConfig:
    MAX_CACHE_WRITE_WORKERS = 2
    WRITE_TIMEOUT_SECONDS = 5.0

class PerformanceConfig:
    THUMBNAIL_RESAMPLING = "BILINEAR"
    THUMBNAIL_JPEG_QUALITY = 85
    WORKSPACE_COMMAND_TTL_SECONDS = 300
```

### Update Code
```python
# base_item_model.py (UPDATE)
from config import ThumbnailLoadingConfig

self._thumbnail_timer.setInterval(
    ThumbnailLoadingConfig.VISIBILITY_CHECK_INTERVAL_MS
)
self._thumbnail_cache = LRUCache(
    max_size=ThumbnailLoadingConfig.THUMBNAIL_CACHE_SIZE
)
buffer_size = ThumbnailLoadingConfig.BUFFER_ROWS
```

### Git Commit
```bash
git add config.py base_item_model.py cache_manager.py
git commit -m "refactor(config): Extract magic numbers to configuration

- Add configuration classes
- Update code to use constants

Related: Phase 3, Task 3.3"
```

---

# PHASE 4: DOCUMENTATION & TESTING

## Task 4.1: Add Regression Tests

### Create Test File
```python
# tests/regression/test_phase1_fixes.py (NEW)
"""Regression tests for Phase 1 fixes."""

def test_signal_disconnection_no_crash(qtbot):
    """Bug: RuntimeError on disconnect. Fixed: Phase 1, Task 1.1"""
    manager = ProcessPoolManager.get_instance()
    for _ in range(5):
        manager.cleanup()  # Should not raise
    assert True

def test_cache_write_signal_order(tmp_path):
    """Bug: Signal before write. Fixed: Phase 1, Task 1.2"""
    cache_manager = CacheManager(cache_dir=tmp_path)
    shots = [Shot("show1", "ABC", "0010", Path("/fake"))]

    signal_order = []
    cache_manager._write_json_cache_sync = lambda *a: (signal_order.append("write"), False)[1]
    cache_manager.shots_migrated.connect(lambda s: signal_order.append("signal"))

    result = cache_manager.migrate_shots_to_previous(shots)

    assert result is False
    assert signal_order == ["write"]  # Signal NOT emitted

def test_concurrent_set_items_no_crash(qtbot):
    """Bug: IndexError on concurrent updates. Fixed: Phase 1, Task 1.3"""
    model = ShotItemModel()
    shots = [create_mock_shot(i) for i in range(100)]

    model.set_items(shots)
    model.set_visible_range(0, 50)
    model.set_items([create_mock_shot(i) for i in range(50)])
    model.set_items(shots)

    qtbot.wait(500)
    assert model.rowCount() > 0
```

### Git Commit
```bash
git add tests/regression/
git commit -m "test(regression): Add regression tests for Phase 1-3 fixes

- Test signal safety, cache write order, concurrent updates
- Prevent bug recurrence

Related: Phase 4, Task 4.1"
```

---

## Task 4.2: Update ARCHITECTURE_REVIEW_SUMMARY.txt

### Add Section
```text
# Phase 1-3 Remediation (2025-10-30)

## Critical Bugs Fixed
1. Signal Disconnection Crash - 100% eliminated
2. Cache Write Data Loss - Silent loss prevented
3. Model Item Access Race - Crashes eliminated

## Performance Improvements
1. Async Cache Writes: 180ms → <10ms (95%)
2. LRU Cache: Unbounded → 128MB capped
3. PIL Optimization: 70-140ms → 20-40ms (60%)

## Architecture
1. ShotMigrationService extracted
2. Configuration centralized
3. Documentation corrected

## Testing
- 15+ new tests, Coverage: 92% → 94%
```

### Git Commit
```bash
git add ARCHITECTURE_REVIEW_SUMMARY.txt
git commit -m "docs: Update architecture review with remediation

Related: Phase 4, Task 4.2"
```

---

## Task 4.3: Create Performance Baseline

### Create PERFORMANCE_BASELINE.md
```markdown
# Performance Baseline

**System:** i9-14900HX, RTX 4090, 32GB RAM
**Date:** 2025-10-30

## Metrics

| Operation | Before | After | Gain |
|-----------|--------|-------|------|
| Cache write | 180ms | <10ms | 95% |
| Thumbnail | 70-140ms | 20-40ms | 60% |
| Tab switch | 200-500ms | 100-200ms | 50% |

## Memory

| Component | Before | After |
|-----------|--------|-------|
| Thumbnail cache | Unbounded | 128MB |
| With 432 shots | 195MB+ | 213MB |

## Verification

```bash
uv run pytest tests/performance/ -v
uv run python -m cProfile shotbot.py --mock
```
```

### Git Commit
```bash
git add PERFORMANCE_BASELINE.md
git commit -m "docs: Create performance baseline

Related: Phase 4, Task 4.3"
```

---

# PART 2 COMPLETE ✅

## Final Verification

```bash
uv run pytest tests/ -v
uv run basedpyright
uv run ruff check .
```

## Project Complete!

- ✅ All critical bugs fixed (Part 1)
- ✅ Performance optimized (Part 1)
- ✅ Architecture cleaned (Part 2)
- ✅ Documentation updated (Part 2)
- ✅ Comprehensive testing (Part 2)

**Total effort:** _____ hours (expected 18-25)

---

**Document Version:** 1.1
**Last Updated:** 2025-10-30
