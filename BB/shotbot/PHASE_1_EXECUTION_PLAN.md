# Phase 1: Dead Code Removal - Execution Plan
*Estimated Time: 1-2 hours*
*Risk Level: LOW*
*Impact: ~5,000 lines removed, zero functional changes*

## Pre-Execution Checklist

- [ ] Ensure working directory is clean: `git status`
- [ ] Create backup branch: `git checkout -b refactor-phase1-cleanup`
- [ ] Run tests to establish baseline: `python -m pytest tests/ -m fast`
- [ ] Note current line count: `find . -name "*.py" | xargs wc -l`

## Step-by-Step Execution

### Step 1: Delete Backup Files (8 files)
```bash
# List backup files to confirm
ls -la *.backup

# Delete backup files
rm -f accessibility_manager.py.backup
rm -f accessibility_manager_complete.py.backup
rm -f config.py.backup
rm -f main_window.py.backup
rm -f pyrightconfig.json.backup
rm -f shot_item_model.py.backup
rm -f shot_model_optimized.py.backup
rm -f threede_scene_finder_optimized_monolithic_backup.py

# Verify deletion
ls -la *.backup  # Should show no files
```

### Step 2: Move Test Files to tests/ Directory (26 files)
```bash
# Create subdirectory for moved tests
mkdir -p tests/moved_from_root

# Move all test files from root to tests/moved_from_root/
mv test_actual_parsing.py tests/moved_from_root/
mv test_cache_separation.py tests/moved_from_root/
mv test_critical_fixes_complete.py tests/moved_from_root/
mv test_critical_fixes_simple.py tests/moved_from_root/
mv test_dependency_injection.py tests/moved_from_root/
mv test_headless.py tests/moved_from_root/
mv test_json_error_handling.py tests/moved_from_root/
mv test_logging_mixin.py tests/moved_from_root/
mv test_mock_injection.py tests/moved_from_root/
mv test_mock_mode.py tests/moved_from_root/
mv test_parser_optimization.py tests/moved_from_root/
mv test_persistent_terminal.py tests/moved_from_root/
mv test_python311_real_compat.py tests/moved_from_root/
mv test_python311_syntax.py tests/moved_from_root/
mv test_qthread_cleanup.py tests/moved_from_root/
mv test_refactoring.py tests/moved_from_root/
mv test_run_linters.py tests/moved_from_root/
mv test_runner.py tests/moved_from_root/
mv test_shot_fetcher.py tests/moved_from_root/
mv test_shot_model.py tests/moved_from_root/
mv test_shot_parser_edge_cases.py tests/moved_from_root/
mv test_threede_latest_scene_finder.py tests/moved_from_root/
mv test_threede_scene_finder_edge_cases.py tests/moved_from_root/
mv test_threede_scene_validation.py tests/moved_from_root/
mv test_workspace_parser.py tests/moved_from_root/
mv test_workspace_parser_comprehensive.py tests/moved_from_root/

# Verify no test files remain in root
ls test_*.py  # Should show no files
```

### Step 3: Remove Obsolete Alternative Implementations (4 files)
```bash
# Verify these files are not imported anywhere
grep -r "import config_refactored" .
grep -r "from config_refactored" .
grep -r "import accessibility_manager_complete" .
grep -r "from accessibility_manager_complete" .
grep -r "import process_pool_factory_refactored" .
grep -r "from process_pool_factory_refactored" .
grep -r "import cache_config_unified" .
grep -r "from cache_config_unified" .

# If no imports found, delete the files
rm -f config_refactored.py
rm -f accessibility_manager_complete.py
rm -f process_pool_factory_refactored.py
rm -f cache_config_unified.py

# Verify deletion
ls config_refactored.py accessibility_manager_complete.py process_pool_factory_refactored.py cache_config_unified.py
```

### Step 4: Clean Deprecated Code from process_pool_manager.py

#### 4a: Remove deprecated method
Edit `process_pool_manager.py`:
- Delete method `_get_bash_session_deprecated()` (approximately lines 150-170)
- Delete the `self._sessions = {}` dictionary initialization
- Delete any comments mentioning "deprecated" sessions

#### 4b: Verify no usage
```bash
grep -r "_get_bash_session_deprecated" .
grep -r "self._sessions\[" .
```

### Step 5: Clean Unused Exception Classes (Optional - Verify First)

#### 5a: Verify exception usage
```bash
# Check if these exceptions are used anywhere
grep -r "NetworkError" . --include="*.py" | grep -v "exceptions.py"
grep -r "ValidationError" . --include="*.py" | grep -v "exceptions.py"
grep -r "ConfigurationError" . --include="*.py" | grep -v "exceptions.py"
grep -r "raise_if_invalid_path" . --include="*.py" | grep -v "exceptions.py"
grep -r "raise_if_command_not_allowed" . --include="*.py" | grep -v "exceptions.py"
```

#### 5b: If truly unused, remove from exceptions.py
- Delete `NetworkError` class
- Delete `ValidationError` class
- Delete `ConfigurationError` class
- Delete `raise_if_invalid_path()` function
- Delete `raise_if_command_not_allowed()` function

## Verification Steps

### 1. Run Quick Tests
```bash
# Quick validation
python tests/utilities/quick_test.py

# Fast test suite
./run_fast_tests.sh
```

### 2. Check Application Still Runs
```bash
# Mock mode test
python shotbot.py --mock --headless

# If successful, try with UI (if display available)
python shotbot.py --mock
```

### 3. Run Linters
```bash
# Check for any import errors
ruff check .

# Type checking
basedpyright
```

### 4. Compare Line Count
```bash
# Show reduction in lines
find . -name "*.py" | xargs wc -l

# Git statistics
git diff --stat
```

## Expected Results

- **Files Deleted**: ~38 files
- **Lines Removed**: ~5,000 lines
- **Test Status**: All passing
- **Application Status**: Runs normally
- **Type Check Status**: No new errors

## Rollback Plan

If any issues occur:
```bash
# Discard all changes and return to main
git checkout main
git branch -D refactor-phase1-cleanup
```

## Commit Strategy

After verification:
```bash
# Stage all deletions
git add -A

# Commit with detailed message
git commit -m "refactor: Phase 1 - Remove dead code and organize test files

- Deleted 8 backup files (.backup extensions)
- Moved 26 test files from root to tests/moved_from_root/
- Removed 4 unused alternative implementations
- Cleaned deprecated methods from process_pool_manager.py
- Removed unused exception classes and helper functions

Impact: ~5,000 lines removed, no functional changes
All tests passing, application runs normally"

# Push to remote
git push origin refactor-phase1-cleanup

# Create PR or merge to main after review
```

## Success Criteria

- [ ] All backup files deleted
- [ ] All test files moved to tests/
- [ ] Obsolete implementations removed
- [ ] Deprecated code cleaned
- [ ] All tests passing
- [ ] Application runs in mock mode
- [ ] No import errors from linters
- [ ] Git commit successful

## Notes

- If any file deletion causes import errors, investigate before proceeding
- Some "test" files in root might be utility scripts - verify before moving
- Keep this plan document for reference
- Document any deviations or issues encountered

## Next Steps

After successful completion:
1. Merge to main branch
2. Update team on cleanup completion
3. Proceed to Phase 2: Eliminate Duplication

---
*End of Phase 1 Execution Plan*