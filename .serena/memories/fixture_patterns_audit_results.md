# Fixture Pattern Audit Results - 2025-11-07

## Quick Summary
- **Overall Grade:** A- (Strong compliance with UNIFIED_TESTING_V2.MD)
- **Scope:** tests/unit, tests/integration, tests/conftest.py
- **Total violations found:** 2 categories

## Key Findings

### Compliant (✅)
1. **7 appropriate autouse fixtures** - Qt cleanup, cache clearing, QMessageBox suppression, random seed
2. **All subprocess mocks are explicit** - Never in autouse
3. **All Qt tests use qapp fixture** - 100% compliant
4. **Factory patterns** - Clear test data generation with tmp_path
5. **No module-level QApplication creation** - Best practice followed

### Violations

#### Violation 1: CacheManager() Without cache_dir (3 instances)
- **File:** tests/unit/test_cache_separation.py (lines 89, 95, 101)
- **Issue:** Shared cache directory pollution (~/.shotbot/cache_test)
- **Severity:** MEDIUM
- **Guideline:** Section 6a - "Always use tmp_path for cache directories in tests"
- **Fix:** Add `cache_dir=tmp_path / "cache_name"` parameter
- **Effort:** 15 minutes

#### Violation 2: Test-Specific Autouse Singletons (7 instances)
- **Files:** test_main_window.py, test_launcher_worker.py, test_cache_separation.py, test_previous_shots_item_model.py, test_launcher_workflow_integration.py, test_feature_flag_switching.py, integration/conftest.py
- **Issue:** Singleton resets run autouse, but guidelines limit autouse to: Qt cleanup, cache clearing, QMessageBox mocking, random seed
- **Severity:** LOW-MEDIUM
- **Guideline:** Section "Essential Autouse Fixtures" - singleton resets not in approved categories
- **Fix:** Convert to explicit fixtures, tests request when needed
- **Effort:** 3.5 hours total

## Remediation Roadmap

### Priority 1 (Immediate - 15 min)
Fix CacheManager() calls in test_cache_separation.py to use tmp_path

### Priority 2 (Short-term - 3.5 hours)
Convert 7 autouse singleton fixtures to explicit, reduce unnecessary overhead

### Priority 3 (Ongoing)
New tests should follow explicit fixture pattern for non-core autouse

## Patterns Done Well
1. Qt cleanup autouse - comprehensive thread/event handling
2. suppress_qmessagebox autouse - prevents modal dialogs
3. Explicit subprocess mocking - never pollutes all tests
4. Factory fixture pattern - clean test data generation

## Related Documentation
- UNIFIED_TESTING_V2.MD section "Essential Autouse Fixtures" (line 378-417)
- UNIFIED_TESTING_V2.MD section "6a. Shared Cache Directories" (line 214-254)
- UNIFIED_TESTING_V2.MD section "Autouse for Mocks" (line 358-376)
