# ShotBot Test Suite - Hanging Tests Report

## Summary
Multiple tests in the ShotBot test suite are hanging/timing out, causing the test suite to fail to complete.

## Identified Hanging Tests

### Unit Tests (tests/unit/)
1. **test_cache_manager.py** - HANGING (timeout during collection)
2. **test_example_best_practices.py** - HANGING  
3. **test_exr_edge_cases.py** - HANGING
4. **test_exr_parametrized.py** - HANGING
5. **test_exr_performance.py** - HANGING
6. **test_main_window.py** - HANGING (specifically test_refresh_shots_updates_display)
7. **test_previous_shots_cache_integration.py** - HANGING
8. **test_previous_shots_grid.py** - HANGING
9. **test_previous_shots_worker.py** - HANGING
10. **test_process_pool_manager_simple.py** - HANGING
11. **test_shot_cache.py** - HANGING
12. **test_shot_deduplication.py** - HANGING
13. **test_shot_info_panel.py** - HANGING
14. **test_shot_model.py** - HANGING (may have been transient)

### Threading Tests (tests/threading/)
1. **test_threading_fixes.py** - HANGING (timeout during collection)

## Working Tests (Complete Successfully)
- test_3de_global_limit_fix.py
- test_cache_validator.py
- test_command_launcher.py
- test_exr_fallback_simple.py
- test_exr_regression_simple.py
- test_failure_tracker.py
- test_launcher_manager.py (68 tests passed in 3.14s)
- test_memory_manager.py (35 tests passed in 2.59s)
- test_nuke_script_generator.py
- test_previous_shots_finder.py
- test_previous_shots_model.py (16 tests passed in 3.26s)
- test_raw_plate_finder.py
- test_scanner_coverage.py
- test_shot_item_model.py
- test_shotbot.py (8 passed, 5 failed in 4.98s)
- test_storage_backend.py
- test_utils.py
- test_utils_extended.py

## Integration Tests (tests/integration/)
- test_thumbnail_discovery_integration.py - WORKS (5 passed in 2.45s)

## Common Patterns

### Collection-Time Hangs
Some tests hang during the collection phase before any tests run:
- test_cache_manager.py
- test_threading_fixes.py

This suggests module-level code or import issues.

### Specific Test Method Hang
- test_main_window.py::TestShotRefresh::test_refresh_shots_updates_display

### Pattern: EXR/Image Processing
Multiple hanging tests are related to EXR image processing:
- test_exr_edge_cases.py
- test_exr_parametrized.py
- test_exr_performance.py

### Pattern: Cache/Worker Tests
Many hanging tests involve caching and worker threads:
- test_cache_manager.py
- test_previous_shots_cache_integration.py
- test_previous_shots_worker.py
- test_shot_cache.py
- test_process_pool_manager_simple.py

## Recommendations

1. **Immediate Actions:**
   - Disable hanging tests temporarily to allow CI/CD to proceed
   - Add explicit timeouts to test methods that may hang
   - Check for module-level code that could cause collection hangs

2. **Root Cause Analysis Needed:**
   - EXR processing tests may have infinite loops or blocking I/O
   - Cache/worker tests may have deadlocks or race conditions
   - Threading tests may have synchronization issues

3. **Quick Workaround:**
   Create a pytest.ini configuration to skip hanging tests:
   ```ini
   [pytest]
   addopts = --ignore=tests/unit/test_cache_manager.py
             --ignore=tests/unit/test_example_best_practices.py
             --ignore=tests/unit/test_exr_edge_cases.py
             --ignore=tests/unit/test_exr_parametrized.py
             --ignore=tests/unit/test_exr_performance.py
             --ignore=tests/unit/test_previous_shots_cache_integration.py
             --ignore=tests/unit/test_previous_shots_grid.py
             --ignore=tests/unit/test_previous_shots_worker.py
             --ignore=tests/unit/test_process_pool_manager_simple.py
             --ignore=tests/unit/test_shot_cache.py
             --ignore=tests/unit/test_shot_deduplication.py
             --ignore=tests/unit/test_shot_info_panel.py
             --ignore=tests/threading/test_threading_fixes.py
   ```

