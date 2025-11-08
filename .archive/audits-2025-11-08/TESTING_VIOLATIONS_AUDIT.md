# Testing Violations Audit - UNIFIED_TESTING_V2.MD Compliance

## Executive Summary

This audit identified **255+ violations** across test files that violate guidelines in **UNIFIED_TESTING_V2.MD**. Violations fall into two major categories:

| Violation Type | Count | Severity | Status |
|---|---|---|---|
| `CacheManager()` without `cache_dir` parameter | 7 | CRITICAL | Fix Pending |
| `Config.SHOWS_ROOT` accessed without monkeypatch | 248+ | HIGH | Fix Pending |
| Module-level Qt app creation | 0 | HIGH | PASS |

---

## Violation #1: CacheManager() Without cache_dir Parameter

**Severity:** CRITICAL  
**Section:** UNIFIED_TESTING_V2.MD § 6a - "Shared Cache Directories" (lines 214-254)  
**Affected File:** `/home/gabrielh/projects/shotbot/tests/unit/test_cache_separation.py`

### The Problem

When `CacheManager()` is instantiated without a `cache_dir` parameter, it defaults to a shared directory: `~/.shotbot/cache_test`. This directory **persists between tests** and **accumulates data across parallel test runs**, causing:

- Tests pass in isolation but fail in full suite
- Data from one test contaminates another
- Failures only appear with `-n 2` or higher parallelism
- Hard to diagnose (tests work individually)

### Guideline Reference

From UNIFIED_TESTING_V2.MD (lines 244-253):

```python
# ❌ WRONG - shares ~/.shotbot/cache_test across all tests
def test_cache_behavior():
    cache_manager = CacheManager()  # Uses default shared directory

# ✅ RIGHT - isolated cache per test
def test_cache_behavior(tmp_path):
    cache_manager = CacheManager(cache_dir=tmp_path / "cache")
```

### Specific Violations

**File:** `/home/gabrielh/projects/shotbot/tests/unit/test_cache_separation.py`

| Line | Test Function | Violation | Fix |
|------|---|---|---|
| 89 | `test_cache_manager_separation()` | `test_manager = CacheManager()` | Add `cache_dir=tmp_path / "cache"` |
| 95 | `test_cache_manager_separation()` | `mock_manager = CacheManager()` | Add `cache_dir=tmp_path / "cache"` |
| 101 | `test_cache_manager_separation()` | `test_manager2 = CacheManager()` | Add `cache_dir=tmp_path / "cache"` |
| 139 | `test_cache_isolation()` | `test_manager = CacheManager()` | Add `cache_dir=tmp_path / "cache"` |
| 146 | `test_cache_isolation()` | `mock_manager = CacheManager()` | Add `cache_dir=tmp_path / "cache"` |
| 153 | `test_cache_isolation()` | `test_manager2 = CacheManager()` | Add `cache_dir=tmp_path / "cache"` |
| 164 | `test_cache_isolation()` | `test_manager3 = CacheManager()` | Add `cache_dir=tmp_path / "cache"` |

### Context Snippet

```python
def test_cache_manager_separation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that CacheManager uses separate directories."""
    # ...setup code...
    
    # Test mode is automatically detected when running under pytest
    test_manager = CacheManager()  # ❌ VIOLATION - no cache_dir
    assert test_manager.cache_dir == CacheConfig.TEST_CACHE_DIR
```

### Recommended Fix

Add `tmp_path` fixture and pass `cache_dir` parameter:

```python
def test_cache_manager_separation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that CacheManager uses separate directories."""
    # ...setup code...
    
    # Create isolated cache directory
    test_cache = tmp_path / "test_cache"
    test_cache.mkdir(parents=True, exist_ok=True)
    
    # Test mode is automatically detected when running under pytest
    test_manager = CacheManager(cache_dir=test_cache)  # ✅ FIXED
    assert test_manager.cache_dir == CacheConfig.TEST_CACHE_DIR
```

### Impact

- Affects conftest.py cleanup (line 356-364): "Tests using CacheManager() without cache_dir parameter use ~/.shotbot/cache_test"
- Cleanup is in place but isolation is better handled at test creation time
- **All 7 violations in this one file can be fixed with one systematic pass**

---

## Violation #2: Config.SHOWS_ROOT Without Monkeypatch

**Severity:** HIGH  
**Section:** UNIFIED_TESTING_V2.MD § 2 & 5 (lines 72-79, 123-131)  
**Affected Files:** 6+ files with 248+ instances

### The Problem

When tests access `Config.SHOWS_ROOT` without monkeypatching it first, they:

- Use the **real production value** from the environment
- Create Shot objects with absolute paths from real VFX directories
- May interact with actual filesystem in parallel execution
- Have different values on different workers (inconsistent state)

In parallel execution (`-n 2` or higher), this causes:
- Different workers see different SHOWS_ROOT values
- Test isolation breaks when tests depend on specific paths
- Regex caches accumulate (OptimizedShotParser uses SHOWS_ROOT as cache key)

### Guideline Reference

From UNIFIED_TESTING_V2.MD (lines 72-79):

```python
# ✅ RIGHT - use monkeypatch for state isolation
def test_config_path(tmp_path, monkeypatch):
    monkeypatch.setattr("config.Config.SHOWS_ROOT", str(tmp_path))
    # Now your test uses tmp_path instead of real filesystem
```

From UNIFIED_TESTING_V2.MD (lines 123-131):

```python
# ❌ WRONG - shared globally
path = f"{Config.SHOWS_ROOT}/gator/shots"

# ✅ RIGHT - isolated with monkeypatch
monkeypatch.setattr("config.Config.SHOWS_ROOT", str(tmp_path))
```

### Pattern 1: Fixture Using Config.SHOWS_ROOT

**File:** `/home/gabrielh/projects/shotbot/tests/unit/test_shot_item_model.py`

**Lines:** 64-72 (test_shots fixture)

```python
@pytest.fixture
def test_shots() -> list[Shot]:
    """Create test Shot objects for testing."""
    return [
        Shot("show1", "seq01", "0010", f"{Config.SHOWS_ROOT}/show1/shots/seq01/seq01_0010"),  # ❌ VIOLATION
        Shot("show1", "seq01", "0020", f"{Config.SHOWS_ROOT}/show1/shots/seq01/seq01_0020"),  # ❌ VIOLATION
        Shot("show2", "seq02", "0030", f"{Config.SHOWS_ROOT}/show2/shots/seq02/seq02_0030"),  # ❌ VIOLATION
        Shot("show2", "seq02", "0040", f"{Config.SHOWS_ROOT}/show2/shots/seq02/seq02_0040"),  # ❌ VIOLATION
    ]
```

**Issue:**
- Fixture creates Shot objects with absolute paths from real Config.SHOWS_ROOT
- No isolation between tests
- Every test using this fixture uses production paths
- In parallel execution, different workers may have different SHOWS_ROOT

**Recommended Fix (Option A - Monkeypatch in fixture):**

```python
@pytest.fixture
def test_shots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[Shot]:
    """Create test Shot objects for testing."""
    monkeypatch.setattr("config.Config.SHOWS_ROOT", str(tmp_path))
    return [
        Shot("show1", "seq01", "0010", f"{Config.SHOWS_ROOT}/show1/shots/seq01/seq01_0010"),  # ✅ FIXED
        Shot("show1", "seq01", "0020", f"{Config.SHOWS_ROOT}/show1/shots/seq01/seq01_0020"),  # ✅ FIXED
        Shot("show2", "seq02", "0030", f"{Config.SHOWS_ROOT}/show2/shots/seq02/seq02_0030"),  # ✅ FIXED
        Shot("show2", "seq02", "0040", f"{Config.SHOWS_ROOT}/show2/shots/seq02/seq02_0040"),  # ✅ FIXED
    ]
```

**Recommended Fix (Option B - Use tmp_path directly):**

```python
@pytest.fixture
def test_shots(tmp_path: Path) -> list[Shot]:
    """Create test Shot objects for testing."""
    shows_root = str(tmp_path)
    return [
        Shot("show1", "seq01", "0010", f"{shows_root}/show1/shots/seq01/seq01_0010"),  # ✅ FIXED
        Shot("show1", "seq01", "0020", f"{shows_root}/show1/shots/seq01/seq01_0020"),  # ✅ FIXED
        Shot("show2", "seq02", "0030", f"{shows_root}/show2/shots/seq02/seq02_0030"),  # ✅ FIXED
        Shot("show2", "seq02", "0040", f"{shows_root}/show2/shots/seq02/seq02_0040"),  # ✅ FIXED
    ]
```

---

### Pattern 2: Test Methods Accessing Config.SHOWS_ROOT

**File:** `/home/gabrielh/projects/shotbot/tests/unit/test_main_window.py`

**Lines:** Multiple instances

| Line | Test Method | Code | Issue |
|------|---|---|---|
| 277 | `test_shot_selection_enables_app_buttons()` | `shows_root = Config.SHOWS_ROOT` | No monkeypatch isolation |
| 300 | `test_shot_deselection_disables_app_buttons()` | `shows_root = Config.SHOWS_ROOT` | No monkeypatch isolation |
| 338 | `test_selection_updates_shot_info_panel()` | `shows_root = Config.SHOWS_ROOT` | No monkeypatch isolation |
| 413 | `test_refresh_after_shot_selected()` | `shows_root = Config.SHOWS_ROOT` | No monkeypatch isolation |
| 471 | `test_manual_refresh_updates_UI()` | `shows_root = Config.SHOWS_ROOT` | No monkeypatch isolation |
| 549 | `test_cache_cleared_on_refresh()` | `shows_root = Config.SHOWS_ROOT` | No monkeypatch isolation |
| 613 | `test_app_selection_switches_to_previous()` | `shows_root = Config.SHOWS_ROOT` | No monkeypatch isolation |
| 658 | `test_app_launch_with_valid_shot()` | `shows_root = Config.SHOWS_ROOT` | No monkeypatch isolation |
| 735 | `test_launcher_error_shows_notification()` | `shows_root = Config.SHOWS_ROOT` | No monkeypatch isolation |
| 763 | `test_invalid_shot_path_shows_error()` | `shows_root = Config.SHOWS_ROOT` | No monkeypatch isolation |

**Context Snippet (Line 277-278):**

```python
def test_shot_selection_enables_app_buttons(self, qtbot: QtBot, tmp_path: Path) -> None:
    """Test that selecting a shot enables application launcher buttons."""
    cache_manager = CacheManager(cache_dir=tmp_path / "cache")
    main_window = MainWindow(cache_manager=cache_manager)
    qtbot.addWidget(main_window)

    # Create a test shot
    shows_root = Config.SHOWS_ROOT  # ❌ VIOLATION - no monkeypatch
    shot = Shot("test_show", "seq01", "0010", f"{shows_root}/test/seq01/0010")
```

**Recommended Fix:**

```python
def test_shot_selection_enables_app_buttons(
    self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that selecting a shot enables application launcher buttons."""
    # Isolate Config.SHOWS_ROOT to tmp_path
    monkeypatch.setattr("config.Config.SHOWS_ROOT", str(tmp_path))  # ✅ FIXED
    
    cache_manager = CacheManager(cache_dir=tmp_path / "cache")
    main_window = MainWindow(cache_manager=cache_manager)
    qtbot.addWidget(main_window)

    # Create a test shot
    shows_root = Config.SHOWS_ROOT  # Now uses tmp_path
    shot = Shot("test_show", "seq01", "0010", f"{shows_root}/test/seq01/0010")
```

---

### Pattern 3: Systematic Use in Model Tests

**File:** `/home/gabrielh/projects/shotbot/tests/unit/test_base_item_model.py`

**Lines:** 107, 108, 117, 131, 142, 153, 166, 177, 188, 199 (and many more ~30+ instances)

```python
class TestInitialization:
    def test_initialization_with_shots(self) -> None:
        """Test ItemModel initialization with list of shots."""
        shots = [
            Shot("TEST", "seq01", "0010", f"{Config.SHOWS_ROOT}/TEST/shots/seq01/seq01_0010"),  # ❌ VIOLATION
            Shot("TEST", "seq01", "0020", f"{Config.SHOWS_ROOT}/TEST/shots/seq01/seq01_0020"),  # ❌ VIOLATION
        ]
```

**Recommended Fix:** Add monkeypatch to test class setup fixture or parametrize tests.

---

### Files with Config.SHOWS_ROOT Violations (248+ instances)

| File | Est. Count | Key Issues |
|------|---|---|
| `test_base_item_model.py` | 30+ | Systematic use in all test methods |
| `test_base_shot_model.py` | 40+ | Systematic use in all test methods |
| `test_main_window.py` | 10 | Test methods without isolation |
| `test_shot_item_model.py` | 1 | Fixture affects all tests |
| `test_previous_shots_finder.py` | 10+ | Test setup without isolation |
| `test_previous_shots_grid.py` | 5+ | Fixture without isolation |
| `test_regex_optimization.py` | 7 | Test setup without isolation |
| `test_error_recovery_optimized.py` | 5+ | Test setup without isolation |
| Other files | 125+ | Various patterns |

---

### Cache Pollution Risk

**From UNIFIED_TESTING_V2.MD line 478-481:**

> The cache is keyed by Config.SHOWS_ROOT. When tests monkeypatch this value, the cache accumulates entries that can cause parser regex mismatches.

**Autouse fixture in conftest.py (line 482-495) handles this:**

```python
@pytest.fixture(autouse=True)
def clear_parser_cache() -> Iterator[None]:
    """Clear OptimizedShotParser pattern cache to prevent pollution."""
    yield
    # Clear AFTER test to remove entries from this test
    try:
        from optimized_shot_parser import _PATTERN_CACHE
        _PATTERN_CACHE.clear()
    except (ImportError, AttributeError):
        pass
```

**However**, this only clears **after** the test. Without monkeypatching Config.SHOWS_ROOT **before** tests, the cache accumulates multiple SHOWS_ROOT values, defeating the purpose of isolation.

---

## Violation #3: Module-Level Qt App Creation

**Severity:** HIGH  
**Section:** UNIFIED_TESTING_V2.MD § 7 (lines 303-322)  
**Status:** ✅ PASS - No violations found

### Guideline

```python
# ❌ WRONG - at module level
app = QCoreApplication.instance() or QCoreApplication([])

# ✅ RIGHT - use pytest-qt's qapp fixture
def test_something(qapp):
    # qapp provides the QApplication instance
    assert qapp is not None
```

### Audit Results

All test files properly use pytest-qt's `qapp` fixture:

| File | Pattern | Status |
|------|---|---|
| `test_cache_separation.py` | No Qt imports | ✅ PASS |
| `test_shot_item_model.py` | Lazy imports via fixture | ✅ PASS |
| `test_main_window.py` | Module-level fixture with autouse | ✅ PASS |
| `conftest.py` | Session-scoped qapp fixture (line 53-98) | ✅ PASS |

**No violations found.**

---

## Remediation Plan

### Phase 1: CRITICAL (test_cache_separation.py)

**Time Estimate:** 15 minutes  
**Difficulty:** Easy

Systematic replacement in `test_cache_separation.py`:

```bash
# Replace all instances of:
CacheManager()

# With:
CacheManager(cache_dir=tmp_path / "cache")
```

**Changes Required:**
1. Add `tmp_path: Path` parameter to affected test functions
2. Add `from pathlib import Path` import if missing
3. Replace 7 instances of `CacheManager()` with `CacheManager(cache_dir=tmp_path / "cache")`
4. Ensure tmp_path is cleaned up (pytest handles automatically)

---

### Phase 2: HIGH (Config.SHOWS_ROOT Violations)

**Time Estimate:** 2-3 hours  
**Difficulty:** Medium

**Option A (Recommended): Fixture-level isolation**

1. Identify all fixtures that use Config.SHOWS_ROOT
   - `test_shots()` in test_shot_item_model.py
   - Similar patterns in other files

2. Add `tmp_path` and `monkeypatch` parameters to fixtures
3. Apply monkeypatch before using Config.SHOWS_ROOT

**Option B: Test-level isolation**

1. Add `monkeypatch` parameter to test methods
2. Apply monkeypatch at start of test

**Option C: Batch replacement**

1. In test methods: Replace `Config.SHOWS_ROOT` with `str(tmp_path)`
2. In fixtures: Apply monkeypatch before using Config.SHOWS_ROOT

---

### Phase 3: VALIDATION

**After fixing violations:**

```bash
# Run full test suite with parallelism
uv run pytest tests/ -n 2 --tb=short

# Check for isolation-related failures
# If tests pass individually but fail in parallel, isolation issue remains
for test_file in tests/unit/test_*.py; do
    echo "Testing: $test_file"
    uv run pytest "$test_file" -v || echo "FAILED: $test_file"
done
```

---

## Recommendation Summary

| Priority | Action | Files | Est. Time |
|----------|--------|-------|-----------|
| **P0 CRITICAL** | Fix CacheManager() in test_cache_separation.py | 1 | 15 min |
| **P1 HIGH** | Fix Config.SHOWS_ROOT in test_shot_item_model.py fixture | 1 | 30 min |
| **P2 HIGH** | Fix Config.SHOWS_ROOT in test_main_window.py (10 tests) | 1 | 45 min |
| **P3 MEDIUM** | Fix Config.SHOWS_ROOT in other test files | 5+ | 1-2 hrs |
| **P4 VALIDATION** | Run full test suite with `-n 2` to verify | - | 30 min |

**Total Estimated Time:** 3-4 hours

---

## References

- **UNIFIED_TESTING_V2.MD** - Comprehensive testing guide (lines 0-1170)
  - Section 2: "Basic Qt Testing Hygiene" (lines 22-79)
  - Section 6a: "Shared Cache Directories" (lines 214-254)
  - Section 7: "Module-Level Qt App Creation" (lines 303-322)

- **Project Instructions** - CLAUDE.md
  - "Singleton Pattern & Test Isolation" section
  - "Qt Widget Guidelines" section

---

## Appendix: Example Fixes

### Example 1: Fixing test_cache_separation.py

**Before:**
```python
def test_cache_manager_separation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that CacheManager uses separate directories."""
    test_manager = CacheManager()  # ❌ WRONG
    assert test_manager.cache_dir == CacheConfig.TEST_CACHE_DIR
```

**After:**
```python
def test_cache_manager_separation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that CacheManager uses separate directories."""
    test_manager = CacheManager(cache_dir=tmp_path / "test")  # ✅ RIGHT
    assert test_manager.cache_dir == (tmp_path / "test")
```

### Example 2: Fixing test_shots Fixture

**Before:**
```python
@pytest.fixture
def test_shots() -> list[Shot]:
    """Create test Shot objects for testing."""
    return [
        Shot("show1", "seq01", "0010", f"{Config.SHOWS_ROOT}/show1/shots/seq01/seq01_0010"),
    ]
```

**After (Option A - Monkeypatch):**
```python
@pytest.fixture
def test_shots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[Shot]:
    """Create test Shot objects for testing."""
    monkeypatch.setattr("config.Config.SHOWS_ROOT", str(tmp_path))
    return [
        Shot("show1", "seq01", "0010", f"{Config.SHOWS_ROOT}/show1/shots/seq01/seq01_0010"),
    ]
```

**After (Option B - Direct tmp_path):**
```python
@pytest.fixture
def test_shots(tmp_path: Path) -> list[Shot]:
    """Create test Shot objects for testing."""
    shows_root = str(tmp_path)
    return [
        Shot("show1", "seq01", "0010", f"{shows_root}/show1/shots/seq01/seq01_0010"),
    ]
```

### Example 3: Fixing test_main_window.py

**Before:**
```python
def test_shot_selection_enables_app_buttons(self, qtbot: QtBot, tmp_path: Path) -> None:
    """Test that selecting a shot enables application launcher buttons."""
    cache_manager = CacheManager(cache_dir=tmp_path / "cache")
    main_window = MainWindow(cache_manager=cache_manager)
    qtbot.addWidget(main_window)

    shows_root = Config.SHOWS_ROOT  # ❌ WRONG
    shot = Shot("test_show", "seq01", "0010", f"{shows_root}/test/seq01/0010")
    main_window._on_shot_selected(shot)
```

**After:**
```python
def test_shot_selection_enables_app_buttons(
    self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that selecting a shot enables application launcher buttons."""
    # Isolate Config.SHOWS_ROOT for test independence
    monkeypatch.setattr("config.Config.SHOWS_ROOT", str(tmp_path))  # ✅ RIGHT
    
    cache_manager = CacheManager(cache_dir=tmp_path / "cache")
    main_window = MainWindow(cache_manager=cache_manager)
    qtbot.addWidget(main_window)

    shows_root = Config.SHOWS_ROOT  # Now isolated to tmp_path
    shot = Shot("test_show", "seq01", "0010", f"{shows_root}/test/seq01/0010")
    main_window._on_shot_selected(shot)
```

---

**Report Generated:** 2025-11-07  
**Audit Scope:** tests/ directory  
**Total Issues:** 255+ violations across 6+ files
