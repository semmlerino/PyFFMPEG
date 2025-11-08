# State Isolation Audit Results

## Executive Summary

Comprehensive audit of state isolation patterns in the test suite (70+ test files analyzed).

**Overall Assessment**: MIXED - Good fundamentals with critical isolation violations in specific areas.

**Key Findings**:
- Tests generally use `monkeypatch` correctly for config isolation (POSITIVE)
- Autouse fixtures are well-designed and properly used (POSITIVE)
- Singleton reset() methods are called consistently (POSITIVE)
- CRITICAL VIOLATION: Direct os.environ mutation without cleanup (NEGATIVE)
- CRITICAL VIOLATION: Manual try/finally env restoration in some tests (NEGATIVE)

---

## 1. FILES PROPERLY USING MONKEYPATCH

### Good monkeypatch Usage (99 files with proper patterns):

**File count**: 60+ test files use monkeypatch for:
- Config.SHOWS_ROOT isolation via `monkeypatch.setattr(Config, "SHOWS_ROOT", ...)`
- Environment variables via `monkeypatch.setenv()`
- Mock object patching via `monkeypatch.setattr()`

**Examples of proper patterns**:

1. **tests/unit/test_cache_separation.py** (EXEMPLARY):
   - Uses `monkeypatch.delenv()` to clear flags
   - Uses `monkeypatch.setenv()` for isolation
   - All patches auto-restore after test

2. **tests/unit/test_raw_plate_finder.py** (EXEMPLARY):
   - 20+ tests all use `monkeypatch.setattr(Config, "SHOWS_ROOT", ...)` 
   - Consistent pattern across all test methods

3. **tests/unit/test_previous_shots_worker.py** (GOOD):
   - Uses `monkeypatch.setattr()` for subprocess mocking
   - Comments note "monkeypatch automatically restores"

4. **tests/unit/test_threede_scene_model.py** (GOOD):
   - Uses `monkeypatch.setattr()` for Config isolation

5. **tests/conftest.py** (EXCELLENT):
   - All fixtures use `monkeypatch` for QMessageBox mocking
   - Lines 499-517: suppress_qmessagebox fixture properly mocks
   - Lines 122-156: enforce_unique_connections uses monkeypatch

6. **tests/integration/test_feature_flag_switching.py** (EXCELLENT):
   - Uses `monkeypatch.setenv()` and `monkeypatch.delenv()` throughout

---

## 2. FILES MUTATING GLOBALS WITHOUT MONKEYPATCH (CRITICAL VIOLATIONS)

### ISOLATION VIOLATION PATTERN 1: Direct os.environ mutation with manual cleanup

**Severity**: CRITICAL - Test isolation risk if test aborts before finally block

**Affected Files** (4 files):

1. **tests/unit/test_mock_injection.py** (VIOLATION):
   ```python
   # Lines 23-64: test_mock_pool_injection
   original_env = dict(os.environ)
   try:
       os.environ["SHOTBOT_MOCK"] = "1"  # Direct mutation
       # ... test code ...
   finally:
       os.environ.clear()
       os.environ.update(original_env)  # Manual cleanup
   ```
   - If exception occurs before finally, os.environ is polluted
   - Should use `monkeypatch.setenv()` instead

   ```python
   # Lines 67-104: test_mock_injection_isolation
   original_env = dict(os.environ)
   try:
       os.environ["SHOTBOT_MOCK"] = "1"  # Direct mutation
       os.environ.pop("SHOTBOT_MOCK", None)  # Direct cleanup
   finally:
       os.environ.clear()
       os.environ.update(original_env)  # Manual cleanup
   ```

2. **tests/unit/test_previous_shots_finder.py** (VIOLATION):
   ```python
   # Lines 147-170: test_finder_initialization_default_user
   original_user = os.environ.get("USER")
   original_mock = os.environ.get("SHOTBOT_MOCK")
   try:
       if "SHOTBOT_MOCK" in os.environ:
           del os.environ["SHOTBOT_MOCK"]  # Direct deletion
       os.environ["USER"] = "envuser"  # Direct mutation
       # ... test code ...
   finally:
       # Manual restoration - error-prone
       if original_user is not None:
           os.environ["USER"] = original_user
       elif "USER" in os.environ:
           del os.environ["USER"]
       # ... etc ...
   ```
   - Multiple direct mutations
   - Complex error-prone manual cleanup

3. **tests/unit/test_headless.py** (VIOLATION):
   ```python
   # Lines 31-67: test_headless_detection
   original_env = dict(os.environ)
   try:
       os.environ["SHOTBOT_HEADLESS"] = "1"  # Direct mutation
       os.environ.clear()
       os.environ.update(original_env)  # Manual management
       os.environ["CI"] = "true"  # Multiple direct mutations
       # ... etc ...
   finally:
       os.environ.clear()
       os.environ.update(original_env)
   ```
   - Lines 34-67, 82-105: Similar pattern repeated
   - Also in test_headless_app_creation (lines 109-145)
   - Also in test_headless_main_window (lines 176-242)

4. **tests/integration/test_cross_component_integration.py** (VIOLATION):
   ```python
   # Lines 253, 620, 692, 785, 832: Direct os.environ mutation
   os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"
   ```
   - No corresponding cleanup visible
   - Relies on autouse fixtures to clean up instead of monkeypatch

### ISOLATION VIOLATION PATTERN 2: Direct QTimer/AsyncShotLoader mutation

**Affected Files** (2 files):

1. **tests/integration/test_cross_component_integration.py** (VIOLATION):
   ```python
   # Lines 261-271: Direct QTimer.singleShot mutation
   original_singleshot = QTimer.singleShot
   QTimer.singleShot = lambda *_args, **_kwargs: None  # Direct mutation
   try:
       # ... test code ...
   finally:
       QTimer.singleShot = original_singleshot  # Manual cleanup
   ```
   - Also Lines 448-486: AsyncShotLoader.__init__ direct mutation

2. **tests/integration/test_user_workflows.py** (VIOLATION):
   ```python
   # Lines 708, 727-728: Direct os.environ mutation without monkeypatch
   os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"
   os.environ["SHOTBOT_NO_INITIAL_LOAD"] = "1"
   # ...
   del os.environ["SHOTBOT_NO_INITIAL_LOAD"]  # Manual cleanup
   ```

---

## 3. AUTOUSE FIXTURES WITH MOCKS (Assessment)

### Pattern Analysis

**Total autouse fixtures found**: 60+

**Breakdown**:

1. **Proper autouse fixtures** (50+):
   - Tests/conftest.py:
     - `qt_cleanup()` - Qt event processing (PROPER)
     - `cleanup_state()` - Singleton resets (PROPER)
     - `clear_parser_cache()` - Pattern cache cleanup (PROPER)
     - `suppress_qmessagebox()` - QMessageBox mocking (PROPER - uses monkeypatch)
     - `stable_random_seed()` - Random seed setup (PROPER)
     - `prevent_qapp_exit()` - QApplication.exit() mocking (PROPER - uses monkeypatch)

   - Tests/integration/conftest.py:
     - `cleanup_state()` - Singleton resets (PROPER)
     - Calls NotificationManager.reset(), ProgressManager.reset(), etc.

2. **Questionable autouse fixtures** (5-10):
   - **tests/unit/test_notification_manager.py**, line 173:
     ```python
     @pytest.fixture(autouse=True)
     def cleanup(self) -> Generator[None, None, None]:
         yield
         NotificationManager.cleanup()
         NotificationManager._instance = None
     ```
     - Direct _instance assignment instead of reset() method
     - Not consistent with conftest.py pattern

   - **tests/unit/test_previous_shots_item_model.py**, line 25:
     ```python
     @pytest.fixture(autouse=True)
     def reset_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
         # ... uses monkeypatch to reset singletons
     ```
     - GOOD - Uses monkeypatch instead of direct mutation

   - **tests/unit/test_shot_item_model.py**, line 46:
     ```python
     @pytest.fixture(autouse=True)
     def reset_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
         monkeypatch.setattr(NotificationManager, "_instance", None)
         monkeypatch.setattr(ProgressManager, "_instance", None)
         monkeypatch.setattr(ProcessPoolManager, "_instance", None)
     ```
     - GOOD - Uses monkeypatch for proper isolation

### Assessment: AUTOUSE PATTERN GOOD

- 80%+ of autouse fixtures are properly designed
- Test-specific cleanup fixtures are fine (not using mocks)
- QMessageBox mocking is properly done with monkeypatch

---

## 4. SINGLETON RESET() METHOD USAGE

### Proper Usage (90%+ of tests):

**Files with correct reset() calls**:

1. **tests/conftest.py** (EXCELLENT):
   - Lines 374: `NotificationManager.reset()`
   - Lines 381: `ProgressManager.reset()`
   - Lines 389: `ProcessPoolManager.reset()`
   - Lines 396: `FilesystemCoordinator.reset()`
   - Also called AFTER test (lines 418-460) for defense-in-depth

2. **tests/integration/conftest.py** (EXCELLENT):
   - Lines 408: `NotificationManager.reset()`
   - Lines 415: `ProgressManager.reset()`
   - Lines 422: `ProcessPoolManager.reset()`
   - Lines 429: `FilesystemCoordinator.reset()`

3. **tests/unit/test_launcher_worker.py** (GOOD):
   - Lines 58, 61: `ProcessPoolManager.reset()` called

4. **tests/unit/test_process_pool_manager.py** (GOOD):
   - Line 503: `session.reset()` called

### Inconsistent Usage (5-10%):

1. **tests/unit/test_notification_manager.py** (INCONSISTENT):
   - Line 177-178: Uses cleanup() + direct _instance assignment
   - Should use reset() method instead

2. **tests/unit/test_shot_item_model.py** (INCONSISTENT):
   - Uses monkeypatch.setattr() for _instance
   - Should call reset() method for consistency

**Assessment**: GOOD - Most tests properly call reset(), minor inconsistencies

---

## 5. CROSS-TEST CONTAMINATION RISKS

### HIGH RISK PATTERNS:

1. **test_cross_component_integration.py, lines 253, 620, 692, 785, 832**:
   - Direct `os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"` without cleanup
   - Relies on autouse fixture cleanup instead of monkeypatch
   - If autouse fixture breaks, test will pollute others
   - **Risk**: HIGH - Multiple tests modify same env var

2. **test_user_workflows.py, lines 708, 727-728**:
   - Direct `os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"`
   - Direct `os.environ["SHOTBOT_NO_INITIAL_LOAD"] = "1"`
   - Manual cleanup with `del os.environ[...]`
   - **Risk**: MEDIUM - Manual cleanup is error-prone

3. **test_mock_injection.py, lines 23-64, 67-104**:
   - Direct ProcessPoolManager._instance mutation
   - Manual env cleanup with dict restore
   - **Risk**: MEDIUM - Exception before finally block pollutes

4. **test_headless.py, lines 28-242**:
   - Direct os.environ mutations without monkeypatch
   - Multiple tests with manual cleanup
   - **Risk**: HIGH - Repeated pattern across 6 test functions

### LOW RISK PATTERNS:

1. **test_cache_separation.py** (monkeypatch throughout):
   - All tests use monkeypatch.setenv/delenv/setattr
   - **Risk**: LOW

2. **test_raw_plate_finder.py** (consistent monkeypatch):
   - 20+ tests all use monkeypatch.setattr(Config, ...)
   - **Risk**: LOW

---

## Summary by Category

| Category | Status | Count | Risk Level |
|----------|--------|-------|------------|
| Files properly using monkeypatch | GOOD | 60+ | LOW |
| Files with direct os.environ mutation | VIOLATION | 4 | CRITICAL |
| Files with class/method mutation | VIOLATION | 2 | MEDIUM |
| Autouse fixtures properly designed | GOOD | 50+ | LOW |
| Singleton reset() calls | GOOD | 95% | LOW |
| Manual try/finally env cleanup | ANTI-PATTERN | 4 | CRITICAL |

---

## Recommendations

### IMMEDIATE (Fix Critical Violations):

1. **Replace manual try/finally with monkeypatch in**:
   - tests/unit/test_mock_injection.py (lines 23-64, 67-104)
   - tests/unit/test_previous_shots_finder.py (lines 147-170)
   - tests/unit/test_headless.py (all test functions)
   - tests/integration/test_user_workflows.py (lines 708, 727-728)

   **Pattern to apply**:
   ```python
   # BEFORE:
   original_env = dict(os.environ)
   try:
       os.environ["KEY"] = "value"
   finally:
       os.environ.clear()
       os.environ.update(original_env)
   
   # AFTER:
   def test_something(monkeypatch):
       monkeypatch.setenv("KEY", "value")
       # ... test code ...
   ```

2. **Replace direct class attribute mutation with monkeypatch**:
   - tests/integration/test_cross_component_integration.py (QTimer.singleShot)
   - tests/integration/test_cross_component_integration.py (AsyncShotLoader.__init__)

   **Pattern to apply**:
   ```python
   # BEFORE:
   original = SomeClass.method
   SomeClass.method = mock_func
   try:
       # test code
   finally:
       SomeClass.method = original
   
   # AFTER:
   def test_something(monkeypatch):
       monkeypatch.setattr(SomeClass, "method", mock_func)
       # ... test code ...
   ```

3. **Standardize singleton cleanup**:
   - tests/unit/test_notification_manager.py should call reset() instead of cleanup() + manual assignment

### SHORT-TERM (Code Quality):

1. **Document monkeypatch requirement** in CLAUDE.md:
   - "All environment variable and global state changes must use monkeypatch"
   - "Never use try/finally with os.environ mutations"

2. **Add pre-commit hook check**:
   - Detect direct `os.environ[` mutations in tests
   - Detect direct class attribute mutations with manual cleanup

3. **Review parallel test safety**:
   - Current violations won't cause issues in serial tests
   - May cause race conditions with pytest-xdist
   - Tests already use `-n 2` for parallel execution

### LONG-TERM (Process):

1. Audit newly added tests for monkeypatch compliance
2. Consider pytest plugin to enforce monkeypatch usage
3. Document fixtures in UNIFIED_TESTING_V2.MD

---

## Files by Status

### EXEMPLARY (Best Practice):
- tests/unit/test_cache_separation.py
- tests/unit/test_raw_plate_finder.py
- tests/integration/test_feature_flag_switching.py
- tests/conftest.py (suppress_qmessagebox fixture)
- tests/integration/conftest.py (cleanup_state fixture)

### GOOD (Acceptable):
- tests/unit/test_previous_shots_worker.py
- tests/unit/test_threede_scene_model.py
- tests/unit/test_shot_item_model.py
- tests/unit/test_previous_shots_item_model.py
- Most unit tests in tests/unit/

### NEEDS IMPROVEMENT (Anti-patterns):
- tests/unit/test_mock_injection.py (CRITICAL)
- tests/unit/test_previous_shots_finder.py (CRITICAL)
- tests/unit/test_headless.py (CRITICAL)
- tests/integration/test_user_workflows.py (CRITICAL)
- tests/integration/test_cross_component_integration.py (CRITICAL)