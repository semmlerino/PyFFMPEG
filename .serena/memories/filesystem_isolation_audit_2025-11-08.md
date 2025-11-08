# Filesystem Isolation Audit Report
**Date**: 2025-11-08  
**Scope**: tests/ directory (192 test files)  
**Total Violations**: 41 instances  
**Overall Compliance**: 93.9% (632/673 patterns compliant)

## Executive Summary

The test suite has high compliance with UNIFIED_TESTING_V2.MD filesystem isolation rules, but critical violations exist that require immediate attention:

- **CRITICAL**: 4 violations affecting fixture definitions and home directory access
- **HIGH**: 37 violations using tempfile.TemporaryDirectory() instead of tmp_path
- **Most problematic area**: Global fixture in conftest.py affects entire test suite

## Critical Violations (Must Fix Immediately)

### 1. tests/conftest.py:358 (P0 - GLOBAL FIXTURE)
```python
shared_cache_dir = Path.home() / ".shotbot" / "cache_test"
```
- **Impact**: Affects ENTIRE test suite
- **Issue**: Creates permanent directory in user home directory
- **Used by**: cleanup_cache_test global fixture

### 2. tests/unit/test_previous_shots_model.py:95
```python
return TestCacheManager()  # Missing cache_dir parameter
```
- **Impact**: All tests using test_cache_manager fixture
- **Severity**: CRITICAL

### 3. tests/utilities/threading_test_utils.py:1060
```python
temp_config_dir = Path.home() / ".shotbot_test" / str(uuid.uuid4())
```
- **Impact**: Integration tests using threading utilities

### 4. tests/integration/test_cross_component_integration.py:561
```python
cache_dir = Path.home() / ".shotbot" / "cache_test"
```

## Violation Breakdown

### By Type:
1. **tempfile.TemporaryDirectory()**: 37 instances (HIGH severity)
   - Manual cleanup required
   - Not integrated with pytest
   - Files: 21 test files

2. **Path.home() hardcoding**: 3 instances (CRITICAL severity)
   - Creates permanent files
   - User home directory pollution

3. **CacheManager without cache_dir**: 1 instance (CRITICAL severity)
   - test_previous_shots_model.py fixture

### By Category:
- CacheManager compliance: 99.6% (249/250+ correct)
- Filesystem isolation: 83.8% (191/228 correct)
- Home directory usage: 0% (0/3 correct)

## Most Problematic Files

1. **tests/utilities/performance_baseline.py**: 5 tempfile violations
2. **tests/conftest.py**: 1 critical + 2 tempfile violations
3. **tests/unit/test_thread_safety_regression.py**: 4 tempfile violations
4. **tests/unit/test_optimized_threading.py**: 4 tempfile violations

## Correct Usage Examples

### Pattern 1 - Single Cache Manager:
```python
cache_dir = tmp_path / "cache"
manager = CacheManager(cache_dir=cache_dir)
```

### Pattern 2 - Multiple Cache Managers:
```python
model1 = ShotModel(cache_manager=TestCacheManager(cache_dir=tmp_path / "cache1"))
model2 = PreviousShotsModel(cache_manager=TestCacheManager(cache_dir=tmp_path / "cache2"))
```

### Pattern 3 - Test Files:
```python
test_file = tmp_path / "data.json"
test_file.write_text(json_data)
```

## Compliant Files (Using tmp_path correctly)
- tests/unit/test_cache_manager.py (38+ uses)
- tests/unit/test_main_window.py (25+ uses)
- tests/unit/test_text_filter.py (20+ uses)
- tests/unit/test_show_filter.py (15+ uses)
- tests/integration/test_user_workflows.py (15+ uses)
- (13+ other files with perfect compliance)

## Priority Roadmap

**Week 1 (P0)**:
- Fix tests/conftest.py:358 (global fixture - affects all tests)

**Week 2 (P1)**:
- Fix tests/unit/test_previous_shots_model.py:95
- Fix tests/utilities/threading_test_utils.py:1060
- Fix tests/integration/test_cross_component_integration.py:561

**Weeks 3-4 (P2)**:
- Replace 37 tempfile.TemporaryDirectory() violations with tmp_path
- Start with files having 5+ violations
- Add linting rules to prevent new violations

**Month 2 (P3)**:
- CI/CD enforcement
- Documentation updates
- Project-wide testing review

## Rule Reference
**UNIFIED_TESTING_V2.MD Rule #4, Section 6a (Line 254)**:
> "Always use tmp_path - All filesystem tests must use tmp_path fixture. CacheManager must use cache_dir parameter: `CacheManager(cache_dir=tmp_path / "cache")`"

## Key Metrics
- **Files scanned**: 192
- **Patterns checked**: 673
- **Violations found**: 41
- **Compliance rate**: 93.9%
