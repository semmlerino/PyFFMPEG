# Test Suite Organization Fix Plan - DO NOT DELETE
*Comprehensive plan to fix test suite organization following UNIFIED_TESTING_GUIDE principles*

## Executive Summary

The current test suite has critical infrastructure issues and organizational problems that violate UNIFIED_TESTING_GUIDE best practices:

- **CRITICAL**: pytest.ini disables pytest-qt but tests use `qtbot` fixtures
- **HIGH**: Duplicate test files violate "real components" principle  
- **MEDIUM**: File clutter (.disabled, .backup) makes test discovery unpredictable

**Goal**: Transform chaotic test suite into clean, maintainable, UNIFIED_TESTING_GUIDE-compliant infrastructure.

## Phase 1: Critical Infrastructure Fixes

### 1.1 Fix pytest Configuration Conflict

**PROBLEM**: 
```ini
# pytest.ini line 12
-p no:pytestqt  # This DISABLES pytest-qt
```

But tests use:
```python
def test_widget(qtbot):  # Requires pytest-qt plugin
    qtbot.addWidget(widget)  # WILL FAIL
```

**SOLUTION**:
```bash
# Remove the line that disables pytest-qt
sed -i '/^[[:space:]]*-p no:pytestqt/d' pytest.ini
```

**VALIDATION**:
```bash
# Test that qtbot now works
python run_tests.py tests/unit/test_shot_info_panel.py::TestShotInfoPanel::test_shot_display -v
```

**COMMIT**:
```bash
git add pytest.ini
git commit -m "fix: Enable pytest-qt plugin for qtbot fixtures

- Remove -p no:pytestqt from pytest.ini
- Fixes Qt tests that use qtbot fixtures  
- Critical infrastructure fix for test suite stability"
```

## Phase 2: File Consolidation

### 2.1 Cache Manager Consolidation

**FILES TO CONSOLIDATE**:
- `tests/unit/test_cache_manager.py` ← **KEEP (base)**
- `tests/unit/test_cache_manager_enhanced.py` ← **MERGE & DELETE**
- `tests/unit/test_cache_manager_threading.py` ← **MERGE & DELETE**

**MERGE STRATEGY**:
```python
# In test_cache_manager.py, add:
class TestCacheManagerBasics:
    """Unit tests for core functionality (existing)."""
    
class TestCacheManagerAdvanced:
    """Advanced caching scenarios from test_cache_manager_enhanced.py."""
    # Copy advanced tests here
    
class TestCacheManagerThreading:
    """Threading safety tests from test_cache_manager_threading.py."""
    # Copy threading tests here
    # Preserve ThreadSafeTestImage usage
```

**COMMANDS**:
```bash
# Safety: Create consolidated version first
cp tests/unit/test_cache_manager.py tests/unit/test_cache_manager_consolidated.py

# MANUAL STEP: Edit test_cache_manager_consolidated.py to add sections above

# Test consolidated version
python run_tests.py tests/unit/test_cache_manager_consolidated.py -v

# If tests pass, replace and cleanup
mv tests/unit/test_cache_manager_consolidated.py tests/unit/test_cache_manager.py
rm tests/unit/test_cache_manager_enhanced.py tests/unit/test_cache_manager_threading.py

git add tests/unit/
git commit -m "consolidate: Merge cache manager test files into single comprehensive suite"
```

### 2.2 Launcher Manager Consolidation

**FILES TO CONSOLIDATE**:
- `tests/unit/test_launcher_manager.py` ← **KEEP (base)**
- `tests/unit/test_launcher_manager_threading.py` ← **MERGE & DELETE**
- `tests/unit/test_launcher_thread_safety.py` ← **MERGE & DELETE**  
- `tests/unit/test_launcher_thread_safety_fixed.py` ← **MERGE & DELETE (priority)**

**MERGE STRATEGY**:
```python
# In test_launcher_manager.py, add:
class TestLauncherManagerBasics:
    """Unit tests for core functionality (existing)."""
    
class TestLauncherManagerThreading:
    """Thread safety and concurrent execution tests."""
    # Prioritize latest fixes from test_launcher_thread_safety_fixed.py
    # Merge comprehensive threading tests
    # Remove conflicting/duplicate test names
```

**COMMANDS**:
```bash
cp tests/unit/test_launcher_manager.py tests/unit/test_launcher_manager_consolidated.py

# MANUAL STEP: Edit to merge from 4 files, prioritize _fixed.py version

python run_tests.py tests/unit/test_launcher_manager_consolidated.py -v

mv tests/unit/test_launcher_manager_consolidated.py tests/unit/test_launcher_manager.py
rm tests/unit/test_launcher_manager_threading.py tests/unit/test_launcher_thread_safety.py tests/unit/test_launcher_thread_safety_fixed.py

git add tests/unit/
git commit -m "consolidate: Merge launcher manager test files into single comprehensive suite"
```

### 2.3 Other Consolidations

**Process Pool Manager**:
```bash
# Investigate .disabled file first
cat tests/unit/test_process_pool_manager.py.disabled
# If obsolete, delete. If useful, merge into simple version.

# Rename for consistency
mv tests/unit/test_process_pool_manager_simple.py tests/unit/test_process_pool_manager.py
```

**Stop-After-First Tests**:
```bash
# Keep: test_threede_stop_after_first.py (follows UNIFIED_TESTING_GUIDE with real files)
# Delete duplicates:
rm tests/unit/test_stop_after_first_behavior.py tests/unit/test_stop_after_first_no_mocks.py
```

**Utility Tests**:
```bash
# Merge extended into main utilities test
# MANUAL: Copy tests from test_utils_extended.py into test_utils.py
rm tests/unit/test_utils_extended.py
```

## Phase 3: Cleanup and Standardization

### 3.1 Remove Clutter Files

**COMMANDS**:
```bash
# Remove all disabled/backup files
find tests/ -name "*.disabled" -delete
find tests/ -name "*.backup" -delete

# Remove duplicate EXR tests (after merging useful parts into test_exr_edge_cases.py)
rm tests/unit/test_exr_fallback_simple.py
rm tests/unit/test_exr_parametrized.py  
rm tests/unit/test_exr_performance.py
rm tests/unit/test_exr_regression_simple.py

git add tests/
git commit -m "cleanup: Remove duplicate, disabled, and backup test files

- Standardize naming conventions
- Remove experimental/obsolete test versions
- Maintain single source of truth per component"
```

### 3.2 Naming Convention Standard

**PATTERN**: `test_<component>.py` where component is the primary class/module

**EXAMPLES**:
- `test_cache_manager.py` (tests CacheManager class)
- `test_shot_model.py` (tests ShotModel class)
- `test_launcher_manager.py` (tests LauncherManager class)
- `test_threede_scene_finder.py` (tests ThreeDESceneFinder class)

### 3.3 Test Class Organization

**STANDARD STRUCTURE**:
```python
class Test<Component>Basics:
    """Unit tests for core functionality."""
    
class Test<Component>Integration:
    """Integration tests with real components."""
    
class Test<Component>Threading:
    """Threading safety tests (if applicable)."""
    
class Test<Component>Performance:
    """Performance tests (if applicable)."""
```

### 3.4 Marker Standardization

```python
@pytest.mark.unit
def test_basic_functionality():
    
@pytest.mark.integration  
def test_component_interaction():
    
@pytest.mark.slow
def test_performance_behavior():
```

## Phase 4: Validation

### 4.1 Pre-Consolidation Baseline

```bash
# Create backup
cp -r tests/ tests_backup_$(date +%Y%m%d_%H%M%S)/

# Establish baseline
python run_tests.py --collect-only > before_consolidation.txt
python run_tests.py > before_results.txt
```

### 4.2 Step-by-Step Validation

After each consolidation:
```bash
# Test specific component
python run_tests.py tests/unit/test_<component>.py -v

# Verify no test functionality lost
# Check test names and counts match expectations
```

### 4.3 Final Validation

```bash
# Generate final inventory
python run_tests.py --collect-only > test_inventory_final.txt

# Full test suite with coverage
python run_tests.py --cov -v > final_test_results.txt

# Verify success criteria:
# - No "qtbot fixture not available" errors
# - All component tests pass  
# - Coverage >= baseline
# - Clean directory structure
```

## File Action Matrix

| Current File | Action | Target File | Rationale |
|-------------|--------|-------------|-----------|
| `test_cache_manager.py` | **KEEP** | `test_cache_manager.py` | Base comprehensive file |
| `test_cache_manager_enhanced.py` | **MERGE → DELETE** | → `test_cache_manager.py` | Merge advanced tests |
| `test_cache_manager_threading.py` | **MERGE → DELETE** | → `test_cache_manager.py` | Merge threading tests |
| `test_launcher_manager.py` | **KEEP** | `test_launcher_manager.py` | Base comprehensive file |
| `test_launcher_manager_threading.py` | **MERGE → DELETE** | → `test_launcher_manager.py` | Merge threading tests |
| `test_launcher_thread_safety.py` | **MERGE → DELETE** | → `test_launcher_manager.py` | Merge safety tests |
| `test_launcher_thread_safety_fixed.py` | **MERGE → DELETE** | → `test_launcher_manager.py` | Latest fixes (priority) |
| `test_process_pool_manager.py.disabled` | **EVALUATE → DELETE** | Delete if obsolete | Investigate first |
| `test_process_pool_manager_simple.py` | **RENAME** | `test_process_pool_manager.py` | Standard naming |
| `test_utils.py` | **KEEP** | `test_utils.py` | Main utilities test |
| `test_utils_extended.py` | **MERGE → DELETE** | → `test_utils.py` | Merge extensions |
| `test_stop_after_first_behavior.py` | **DELETE** | N/A | Superseded |
| `test_stop_after_first_no_mocks.py` | **DELETE** | N/A | Redundant |
| `test_threede_stop_after_first.py` | **KEEP** | `test_threede_stop_after_first.py` | Follows UNIFIED_TESTING_GUIDE |
| All `.disabled` files | **DELETE** | N/A | Cleanup |
| All `.backup` files | **DELETE** | N/A | Cleanup |

## Risk Mitigation

### High Risk
- **Configuration breaks all tests**: Test immediately after pytest.ini fix
- **Test functionality lost**: Use consolidation approach (create new, test, replace)
- **Threading instability**: Preserve ThreadSafeTestImage usage exactly

### Medium Risk  
- **Test name conflicts**: Rename during merge
- **Import errors**: Update cross-references
- **Coverage drops**: Investigate lost tests

### Low Risk
- **Git history complexity**: Clear commit messages
- **Documentation outdated**: Update file references

## Success Criteria

### Before (Chaos)
```
tests/unit/
├── test_cache_manager.py  
├── test_cache_manager_enhanced.py      # DUPLICATE
├── test_cache_manager_threading.py     # DUPLICATE  
├── test_launcher_manager.py
├── test_launcher_manager_threading.py  # DUPLICATE
├── test_launcher_thread_safety.py      # DUPLICATE
├── test_launcher_thread_safety_fixed.py # DUPLICATE
├── test_process_pool_manager.py.disabled # BROKEN
└── ... (30+ other files with issues)
```

### After (UNIFIED_TESTING_GUIDE Compliant)
```
tests/unit/
├── test_cache_manager.py            # ONE comprehensive file
├── test_launcher_manager.py         # ONE comprehensive file  
├── test_process_pool_manager.py     # Clean naming
├── test_shot_model.py              # Already refactored
├── test_threede_scene_finder.py    # Clean, follows guide
├── test_threede_stop_after_first.py # Real files, best practice
└── ... (clean, organized files)
```

### Metrics
- ✅ pytest.ini enables pytest-qt (no qtbot failures)
- ✅ One comprehensive test file per component
- ✅ Zero duplicate test files  
- ✅ Zero .disabled/.backup files
- ✅ All original test functionality preserved
- ✅ Follows "Real components over mocks" → Real, authoritative test suites
- ✅ Clear maintenance: Update component → Update single test file

## Execution Timeline

- **Day 1**: Fix pytest.ini (critical)
- **Day 2**: Cache Manager consolidation  
- **Day 3**: Launcher Manager consolidation
- **Day 4**: Cleanup and standardization
- **Day 5**: Final validation and documentation

This plan transforms the chaotic test suite into clean, maintainable, UNIFIED_TESTING_GUIDE-compliant testing infrastructure.