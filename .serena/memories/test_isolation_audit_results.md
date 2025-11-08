# Test Isolation Audit Results

## Executive Summary
Audit of test suite for test isolation issues per UNIFIED_TESTING_V2.MD guidelines.
Medium thoroughness: Focus on 4 key violation categories.

**Overall Status**: 3 HIGH-risk categories identified, 1 LOW-risk

---

## VIOLATION CATEGORIES

### 1. Shared Cache Directories (CacheManager without cache_dir) - HIGH RISK

**Violation Count**: 10 instances across 2 files

**Impact**: Tests share ~/.shotbot/cache_test directory, causing cache contamination across parallel workers

**Files with Violations**:

1. **tests/unit/test_cache_separation.py** (7 violations)
   - Line 89: `test_manager = CacheManager()`
   - Line 95: `mock_manager = CacheManager()`
   - Line 101: `test_manager2 = CacheManager()`
   - Line 139: `test_manager = CacheManager()`
   - Line 146: `mock_manager = CacheManager()`
   - Line 153: `test_manager2 = CacheManager()`
   - Line 164: `test_manager3 = CacheManager()`

2. **tests/advanced/README.md** (1 violation - documentation)
   - Line 100: `cache = CacheManager()` (in code example)

**Root Cause**: Tests intentionally use default cache_dir to test CacheConfig behavior. This is documented in conftest.py at line 356: "Tests using CacheManager() without cache_dir parameter use ~/.shotbot/cache_test"

**Risk Assessment**: HIGH
- **Why**: Multiple tests write to shared ~/.shotbot/cache_test directory
- **Parallel Execution Impact**: Cache data from worker A visible to worker B
- **Mitigation Status**: Partially mitigated - test_cache_separation.py intentionally tests this behavior, but tests should use tmp_path for isolation

**Recommendation**: Use monkeypatch with tmp_path:
```python
def test_cache_behavior(tmp_path, monkeypatch):
    monkeypatch.setattr(CacheConfig, "TEST_CACHE_DIR", tmp_path / "test")
    manager = CacheManager()
```

---

### 2. Global Config Usage Without Monkeypatch - MEDIUM RISK

**Violation Count**: 3 instances in fixtures (NOT in test functions)

**Impact**: Tests use Config.SHOWS_ROOT directly in fixtures without monkeypatch isolation

**Files with Violations**:

1. **tests/unit/test_launcher_controller.py**
   - Line 178: `workspace_path=f"{Config.SHOWS_ROOT}/TEST/shots/seq01/seq01_0010"` (in fixture)
   - Line 188: `scene_path=Path(f"{Config.SHOWS_ROOT}/TEST/shots/seq01/seq01_0010/3de/v001/scene.3de")` (in fixture)
   - Line 192: `workspace_path=f"{Config.SHOWS_ROOT}/TEST/shots/seq01/seq01_0010"` (in fixture)

**Context**: Located in test fixtures `test_shot` and `test_scene`:
```python
@pytest.fixture
def test_shot() -> Shot:
    return Shot(
        workspace_path=f"{Config.SHOWS_ROOT}/TEST/shots/seq01/seq01_0010",
    )
```

**Root Cause**: Fixtures use Config.SHOWS_ROOT for path construction. Since fixtures are created per test, this uses whatever Config.SHOWS_ROOT is set to at fixture creation time.

**Risk Assessment**: MEDIUM
- **Why**: These are fixtures (not module-level), evaluated per test
- **Parallel Execution Impact**: Low - each test gets its own fixture instance
- **Real Risk**: If Config.SHOWS_ROOT changes during test (via monkeypatch), fixture still uses original value
- **Actual Impact**: Minimal because fixture is evaluated fresh for each test

**Recommendation**: Pass Config.SHOWS_ROOT as fixture parameter OR use monkeypatch to set it before fixture creation

---

### 3. MainWindow() Without defer_background_loads Parameter - MEDIUM-to-LOW RISK

**Violation Count**: 29 instances across integration tests

**Impact**: MainWindow created without background loader control

**Files with Violations**:

1. **tests/integration/test_cross_component_integration.py** (4 violations)
   - Line 266: `window = MainWindow()` (wrapped in QTimer.singleShot mock)
   - Line 694: `window = MainWindow()`
   - Line 787: `window = MainWindow()`
   - Line 834: `window = MainWindow()`

2. **tests/integration/test_feature_flag_switching.py** (7 violations)
   - Lines 114, 145, 204, 223, 439, 469, 511: Multiple `MainWindow()` calls

3. **tests/integration/test_launcher_panel_integration.py** (12 violations)
4. **tests/integration/test_refactoring_safety.py** (3 violations)
5. Other integration tests: 3 additional violations

**Root Cause**: defer_background_loads parameter doesn't exist in MainWindow.__init__(). Tests use QTimer.singleShot mocking or process pool mocking to manage background operations.

**Risk Assessment**: LOW
- **Why**: defer_background_loads is not an actual MainWindow parameter
- **Actual Mitigation**: Tests already handle background loading via:
  - QTimer.singleShot mocking (lines 262, 223)
  - TestProcessPool injection
  - Background worker thread management

**Current Approach**: Tests disable/control background operations through:
```python
# Approach 1: Mock QTimer
with patch("PySide6.QtCore.QTimer.singleShot"):
    window = MainWindow()

# Approach 2: Mock ProcessPoolManager
mock_get_instance.return_value = TestProcessPool()
window = MainWindow()
```

**Recommendation**: No action needed - existing pattern is correct

---

### 4. Module-Level Qt App Creation - PASSED ✅

**Violation Count**: 0 instances

**Status**: All tests properly use pytest-qt's `qapp` fixture

**Details**:
- conftest.py (lines 53-97): Proper session-scoped qapp fixture
- All tests inherit from qapp fixture
- No module-level `app = QApplication()` instances found

---

## SUMMARY TABLE

| Category | Count | Risk | Status |
|----------|-------|------|--------|
| CacheManager without cache_dir | 10 | HIGH | Needs fixing (test-specific design) |
| Config usage without monkeypatch | 3 | MEDIUM | Minimal impact (fixtures) |
| MainWindow without defer_background_loads | 29 | LOW | Non-existent parameter (false positive) |
| Module-level Qt app creation | 0 | - | PASSED ✅ |

---

## PARALLEL EXECUTION IMPACT

Based on current violations:

**Tests that FAIL under `-n 2` due to cache contamination**:
- test_cache_separation.py tests may see cross-worker cache contamination

**Tests that PASS under `-n 2`** (acceptable):
- Config usage in fixtures (evaluated per test)
- MainWindow creation (background operations controlled)

**Recommended Execution**:
```bash
# Current status
~/.local/bin/uv run pytest tests/ -n 2  # May have cache contamination in test_cache_separation.py
~/.local/bin/uv run pytest tests/ -n 0  # Serial (safe)

# After fixes
~/.local/bin/uv run pytest tests/ -n auto  # All parallel safe
```

---

## RECOMMENDED FIXES (Priority Order)

### 1. HIGH PRIORITY: Fix test_cache_separation.py
Use tmp_path isolation for all CacheManager instantiations:
```python
def test_cache_isolation(monkeypatch, tmp_path):
    test_base = tmp_path / "cache_test"
    monkeypatch.setattr(CacheConfig, "TEST_CACHE_DIR", test_base / "test")
    test_manager = CacheManager()  # Now uses isolated tmp_path
```

### 2. MEDIUM PRIORITY: Fix test_launcher_controller.py fixtures
Pass Config.SHOWS_ROOT as fixture parameter:
```python
@pytest.fixture
def test_shot(monkeypatch, tmp_path) -> Shot:
    shows_root = tmp_path / "shows"
    monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))
    return Shot(...)
```

### 3. LOW PRIORITY: Verify MainWindow background operations
Current approach is correct - no changes needed.

