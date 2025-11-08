# Test Suite Filesystem Isolation Audit Results

## Summary
**Audit Date**: 2025-11-08
**Scope**: `/home/gabrielh/projects/shotbot/tests/`
**Total Violations Found**: 7 distinct violations across 6 files
**Severity**: MEDIUM - Mix of test utilities (non-critical) and legitimate fixture cleanup

---

## Violations by Category

### Category 1: Hardcoded /tmp/ Paths (4 violations)
These are **test utility/double classes** that use fallback defaults when `tmp_path` isn't provided.

**VIOLATION LOCATIONS:**

1. **tests/test_doubles_library.py:479**
   - File: `/home/gabrielh/projects/shotbot/tests/test_doubles_library.py`
   - Line: 479
   - Code: `self.cache_dir = cache_dir or Path("/tmp/test_cache")`
   - Context: `TestCacheManager.__init__()` fallback default
   - **Status**: ✅ ACCEPTABLE - Fallback with parameter option (accepts tmp_path when passed)
   - **Note**: Class accepts `cache_dir` parameter, so tests can pass `tmp_path`

2. **tests/test_doubles_extended.py:53**
   - File: `/home/gabrielh/projects/shotbot/tests/test_doubles_extended.py`
   - Line: 53
   - Code: `self.base_path = base_path or Path("/tmp/test_fs")`
   - Context: `TestFilesystem.__init__()` fallback default
   - **Status**: ✅ ACCEPTABLE - Fallback with parameter option
   - **Note**: Accepts `base_path` parameter for `tmp_path` injection

3. **tests/doubles.py:97**
   - File: `/home/gabrielh/projects/shotbot/tests/doubles.py`
   - Line: 97
   - Code: `self.cache_dir = cache_dir or Path("/tmp/test_cache")`
   - Context: `MockCacheManager.__init__()` fallback default
   - **Status**: ✅ ACCEPTABLE - Fallback with parameter option
   - **Note**: Mock utility class; accepts parameter

4. **tests/utilities/minimal_test.py:25**
   - File: `/home/gabrielh/projects/shotbot/tests/utilities/minimal_test.py`
   - Line: 25
   - Code: `test_path = Path("/tmp/test_path")`
   - Context: `test_path_validation()` function
   - **Status**: ⚠️ VIOLATION - Hardcoded path without parameter
   - **Note**: Creates real /tmp/ directory and calls `mkdir()`, `rmdir()` on it
   - **Recommended Fix**: Use `tmp_path` fixture parameter

5. **tests/utilities/minimal_test.py:42**
   - File: `/home/gabrielh/projects/shotbot/tests/utilities/minimal_test.py`
   - Line: 42
   - Code: `base = Path("/tmp/shotbot_test")`
   - Context: `test_find_thumbnail()` function
   - **Status**: ⚠️ VIOLATION - Hardcoded path
   - **Note**: Creates directory structure in /tmp/shotbot_test
   - **Recommended Fix**: Use `tmp_path` fixture parameter

---

### Category 2: Path.home() Usage Without Proper Isolation (3 violations)

#### 2A: Legitimate Fixture Cleanup (conftest.py) ✅
**tests/conftest.py:358**
- File: `/home/gabrielh/projects/shotbot/tests/conftest.py`
- Line: 358
- Code: `shared_cache_dir = Path.home() / ".shotbot" / "cache_test"`
- Context: In `cleanup_state()` fixture (runs BEFORE/AFTER each test)
- **Status**: ✅ ACCEPTABLE - This is fixture cleanup, not test logic
- **Justification**: 
  - Used to CLEAN UP state that accumulates from tests that don't use tmp_path
  - Creates directory with "cache_test" suffix to avoid overwriting production cache
  - Explicitly documented as cleanup for shared cache contamination
  - Part of test infrastructure, not test data

#### 2B: Legitimate Helper Function (threading_test_utils.py) ✅
**tests/utilities/threading_test_utils.py:1060**
- File: `/home/gabrielh/projects/shotbot/tests/utilities/threading_test_utils.py`
- Line: 1060
- Code: `temp_config_dir = Path.home() / ".shotbot_test" / str(uuid.uuid4())`
- Context: Helper generator function `isolated_launcher_manager_fixture()`
- **Status**: ✅ ACCEPTABLE - Test utility/helper, not main test logic
- **Justification**:
  - Creates unique directory per test with UUID
  - Uses "_test" suffix to avoid production conflicts
  - Provides isolation through uniqueness
  - Documented purpose is test isolation

#### 2C: Integration Test Cleanup (test_cross_component_integration.py) ✅
**tests/integration/test_cross_component_integration.py:561**
- File: `/home/gabrielh/projects/shotbot/tests/integration/test_cross_component_integration.py`
- Line: 561
- Code: `cache_dir = Path.home() / ".shotbot" / "cache_test"`
- Context: In `setup()` method of test class fixture
- **Status**: ✅ ACCEPTABLE - Cleanup before test setup
- **Justification**:
  - Purpose is to DELETE/CLEAR cache directory before tests
  - Part of setup/teardown fixture infrastructure
  - Uses "cache_test" to avoid production paths
  - Cleanup pattern (not test data creation)

---

### Category 3: String Literals (Test Data, Not Real Paths) ✅
**tests/test_concurrent_thumbnail_race_conditions.py:98-100**
- File: `/home/gabrielh/projects/shotbot/tests/test_concurrent_thumbnail_race_conditions.py`
- Lines: 98-100
- Code: 
  ```python
  base_paths = [
      "/shows/test/shots/editorial/cutref",       # String literal
      "/home/user/.shotbot/cache/production/thumbnails",  # String literal
      "/shows/test/shots/mm/default/scene",       # String literal
  ]
  ```
- **Status**: ✅ ACCEPTABLE - String test data, not actual filesystem operations
- **Justification**: 
  - These are string path patterns passed to `PathUtils.validate_path_exists()`
  - No actual filesystem operations on these paths
  - Testing path validation logic, not filesystem isolation
  - Paths don't exist and aren't created

---

## Summary Table

| File | Line | Violation | Type | Severity | Status |
|------|------|-----------|------|----------|--------|
| test_doubles_library.py | 479 | `Path("/tmp/test_cache")` fallback | Fallback default | MINOR | ✅ OK |
| test_doubles_extended.py | 53 | `Path("/tmp/test_fs")` fallback | Fallback default | MINOR | ✅ OK |
| doubles.py | 97 | `Path("/tmp/test_cache")` fallback | Fallback default | MINOR | ✅ OK |
| minimal_test.py | 25 | `Path("/tmp/test_path")` | Hardcoded | MEDIUM | ⚠️ FIX |
| minimal_test.py | 42 | `Path("/tmp/shotbot_test")` | Hardcoded | MEDIUM | ⚠️ FIX |
| conftest.py | 358 | `Path.home() / ".shotbot"` | Fixture cleanup | MINOR | ✅ OK |
| threading_test_utils.py | 1060 | `Path.home() / ".shotbot_test"` | Test helper | MINOR | ✅ OK |
| test_cross_component_integration.py | 561 | `Path.home() / ".shotbot"` | Fixture cleanup | MINOR | ✅ OK |

---

## Findings

### ✅ Acceptable Patterns (5 violations)
These violations do NOT violate the UNIFIED_TESTING_V2.MD rule:

1. **Fallback defaults with parameters** (3 cases)
   - Test double/utility classes that accept optional path parameters
   - Allow `tmp_path` injection when needed
   - Only use fallback /tmp/ when not provided
   - Pattern: `self.cache_dir = cache_dir or Path("/tmp/test_cache")`

2. **Fixture cleanup patterns** (2 cases)
   - Used in conftest.py for shared state cleanup
   - Part of test infrastructure, not test logic
   - Create isolated directories with "_test" suffixes
   - Only delete/clear, never create test data

### ⚠️ Real Violations (2 violations)
These DO violate the UNIFIED_TESTING_V2.MD "Always use tmp_path for filesystem tests" rule:

1. **tests/utilities/minimal_test.py:25** - `test_path_validation()`
   - Hardcoded `/tmp/test_path`
   - Should accept `tmp_path` fixture parameter

2. **tests/utilities/minimal_test.py:42** - `test_find_thumbnail()`
   - Hardcoded `/tmp/shotbot_test`
   - Should accept `tmp_path` fixture parameter

---

## Recommendations

### Immediate Actions (Priority: HIGH)
Fix the 2 violations in `minimal_test.py`:

```python
# BEFORE (minimal_test.py:17-32)
def test_path_validation() -> None:
    test_path = Path("/tmp/test_path")
    test_path.mkdir(exist_ok=True)
    # ...
    test_path.rmdir()

# AFTER
def test_path_validation(tmp_path) -> None:
    test_path = tmp_path / "test_path"
    test_path.mkdir(exist_ok=True)
    # ...
    # No cleanup needed - pytest handles it
```

### No Changes Needed
- Test double classes (fallback defaults are fine)
- Fixture cleanup code (not test logic)
- String test data (no filesystem operations)

---

## Files to Review
**Action Items**:
- [ ] `/home/gabrielh/projects/shotbot/tests/utilities/minimal_test.py` - Fix 2 violations
- [ ] Verify no new hardcoded paths introduced in active tests

**Files Already Compliant**:
- ✅ `/home/gabrielh/projects/shotbot/tests/conftest.py` - Fixture cleanup only
- ✅ `/home/gabrielh/projects/shotbot/tests/test_doubles_library.py` - Parameterized defaults
- ✅ `/home/gabrielh/projects/shotbot/tests/test_doubles_extended.py` - Parameterized defaults
- ✅ `/home/gabrielh/projects/shotbot/tests/doubles.py` - Parameterized defaults
- ✅ `/home/gabrielh/projects/shotbot/tests/integration/test_cross_component_integration.py` - Fixture cleanup only

