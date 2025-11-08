# Anti-Pattern Audit Results

## Executive Summary
Very thorough search of test suite found **2 files using @pytest.mark.flaky**, **0 files using xdist_group**, and **7 files with missing docstrings**. Good overall test hygiene but some issues to address.

---

## 1. Files Using @pytest.mark.flaky (REQUIRES ROOT CAUSE FIXES)

**Status**: FOUND - 2 files with 3 instances total

### Files with @pytest.mark.flaky:

1. **tests/unit/test_shot_parsing_vfx_paths.py**
   - Line 182: `@pytest.mark.flaky(reruns=2)` on `test_workspace_path_format()`
   - **Issue**: Test document acknowledges "Qt singleton state contamination" - should be fixed, not masked with reruns
   - **Root Cause**: Likely `make_test_shot` fixture contaminating Qt state across parallel workers
   - **Fix Needed**: Investigate fixture isolation, use monkeypatch for Qt state

2. **tests/unit/test_show_filter.py**
   - Line 316: `@pytest.mark.flaky(reruns=2)` on `test_populate_show_filter()`
   - Line 573: `@pytest.mark.flaky(reruns=2)` on `test_refresh_populates_show_filter()`
   - **Issue**: Both tests acknowledge "Qt singleton state contamination"
   - **Root Cause**: Tests touching Qt singleton (QApplication) without proper isolation
   - **Fix Needed**: Use fixture-based cleanup or defer_background_loads pattern

### Recommended Action:
- Replace @pytest.mark.flaky with proper test isolation fixes
- Document why these tests were flaky: likely Qt event loop state leaking between workers
- Run tests with `-n 2` to verify fix works in parallel

---

## 2. Files Using xdist_group (NONE FOUND)

**Status**: CLEAN - No files use xdist_group as band-aid

---

## 3. Excessive Mocking Analysis

**Status**: ACCEPTABLE - Mocking patterns are reasonable

### Mock-Heavy Files:

1. **tests/fixtures/mocks.py** (275 lines, 25 mock references)
   - Purpose: Centralized mock definitions (appropriate location)
   - Pattern: Legitimate fixture-based mocking

2. **tests/test_doubles_extended.py** (unknown size, 6 mock references)
   - Pattern: Test double library (acceptable)

3. **tests/unit/test_mock_injection.py** (104 lines, 3 mock references)
   - Purpose: Specific mock injection patterns (appropriate)

### Assessment:
- Mocking is concentrated in test fixture files (good practice)
- No evidence of excessive mocking in individual tests
- System boundaries (subprocess, network) are properly mocked

---

## 4. Tests Missing Docstrings

**Status**: IDENTIFIED - 7 files with ~19 total missing docstrings (very low percentage)

### Files with Missing Docstrings:

1. **tests/test_doubles_extended.py** (6 tests missing)
   - test_shot_creation
   - test_widget_behavior
   - test_cache_behavior
   - test_async_operation
   - test_command_execution
   - (1 more)
   - Type: Utility test file (lower priority)

2. **tests/test_type_safe_patterns.py** (1 test missing)
   - test_with_real_data

3. **tests/unit/test_main_window_fixed.py** (1 test missing)
   - test_run_command

4. **tests/unit/test_qt_signal_warnings.py** (1 test missing)
   - test_slot

5. **tests/unit/test_scene_finder_performance.py** (9 tests missing)
   - test_rglob, test_find_command, test_rglob_medium
   - test_find_command_medium, test_find_scenes, ...
   - Type: Performance/benchmark tests (lower priority)

6. **tests/unit/test_thread_safety_validation.py** (1 test missing)
   - test_task

### Assessment:
- Total: ~19 missing docstrings out of 2,296+ tests = 0.8% missing rate
- Most missing docstrings are in utility/performance test files
- Core test files (shot_model, cache_manager, etc.) have good docstring coverage

### Recommended Action:
- Add docstrings to tests in utility files (quick fix)
- Performance tests should document what metric is being measured

---

## 5. isinstance() Anti-Pattern Analysis

**Status**: ACCEPTABLE - isinstance() usage is appropriate in tests

### Pattern Distribution:
- **Path type checking**: `isinstance(path, str)` - APPROPRIATE (type validation)
- **Qt type assertions**: `assert isinstance(widget, QWidget)` - APPROPRIATE (capability validation)
- **Result type assertions**: `assert isinstance(result, dict)` - APPROPRIATE (contract validation)
- **Object type checks in collections**: `isinstance(item, MyClass)` - APPROPRIATE (collection validation)

### Assessment:
- isinstance() usage in tests is legitimate and follows best practices
- Tests are validating behavior contracts, not implementing duck typing
- No instances of inappropriate isinstance() used to replace protocol checking

### Verdict:
NO ANTI-PATTERN FOUND - isinstance() usage in tests is appropriate

---

## Summary of Findings

| Category | Status | Files | Action |
|----------|--------|-------|--------|
| xdist_group band-aid | CLEAN | 0 | None |
| @pytest.mark.flaky | FOUND | 2 | Fix root causes (Qt state isolation) |
| Excessive mocking | ACCEPTABLE | 0 concerning | None |
| Missing docstrings | MINOR | 7 files, 19 tests | Add docstrings to utility tests |
| isinstance() anti-pattern | CLEAN | N/A | None |

---

## Priority Fixes

### High Priority:
1. **Remove @pytest.mark.flaky from test_show_filter.py and test_shot_parsing_vfx_paths.py**
   - Fix Qt state isolation in fixtures
   - Test with `-n 2` to verify parallel execution
   - Document what isolation issue was causing the flakiness

### Medium Priority:
2. **Add docstrings to performance and utility tests**
   - Improves test maintainability
   - Documents measurement intent
   - Takes ~30 minutes

### Low Priority:
3. **Monitor for new flaky decorators**
   - Use git hooks to warn on @pytest.mark.flaky additions
   - Enforce docstring policy with pre-commit hooks

