# Integration Fix Plan - Model/View Migration Cleanup

## Executive Summary
During the Model/View architecture migration (commit 707ce6c4), three widget-based implementations were deleted but test files and one module still reference them, causing import errors. This plan details the fixes needed to restore full test suite functionality.

## Problem Analysis

### Deleted Files (commit 707ce6c4)
- `base_grid_widget.py` (504 lines) - Base class for grid widgets
- `shot_grid.py` (154 lines) - Shot grid widget implementation
- `previous_shots_grid.py` (289 lines) - Previous shots grid widget

### Replacement Architecture
| Old Widget-based | New Model/View Components |
|-----------------|---------------------------|
| `shot_grid.py` → `ShotGrid` | `shot_grid_view.py` → `ShotGridView` + `shot_item_model.py` → `ShotItemModel` |
| `previous_shots_grid.py` → `PreviousShotsGrid` | `previous_shots_view.py` → `PreviousShotsView` + `previous_shots_item_model.py` → `PreviousShotsItemModel` |
| `base_grid_widget.py` → `BaseGridWidget` | Functionality distributed to individual views |

### Affected Files Requiring Updates

#### 1. **threede_shot_grid.py** (Line 7)
- **Issue**: Imports from deleted `base_grid_widget`
- **Current**: `from base_grid_widget import BaseGridWidget`
- **Status**: Module obsolete (main_window.py uses ThreeDEGridView instead)
- **Action**: Either delete module or update to not depend on BaseGridWidget

#### 2. **tests/unit/test_shot_grid_widget.py** (Line 31)
- **Issue**: Imports from deleted `shot_grid`
- **Current**: `from shot_grid import ShotGrid`
- **Action**: Update to use `ShotGridView` from `shot_grid_view`

#### 3. **tests/unit/test_previous_shots_grid.py** (Line 22)
- **Issue**: Imports from deleted `previous_shots_grid`
- **Current**: `from previous_shots_grid import PreviousShotsGrid`
- **Action**: Update to use `PreviousShotsView` from `previous_shots_view`

#### 4. **tests/unit/test_threede_shot_grid.py** (Line 13)
- **Issue**: Imports from `threede_shot_grid` which depends on deleted `base_grid_widget`
- **Current**: `from threede_shot_grid import ThreeDEShotGrid`
- **Action**: Update to use `ThreeDEGridView` from `threede_grid_view`

## Implementation Plan

### Phase 1: Decide on threede_shot_grid.py fate
**Option A (Recommended)**: Delete threede_shot_grid.py
- It's obsolete (replaced by threede_grid_view.py)
- Only referenced by its test file
- Main window already uses ThreeDEGridView

**Option B**: Fix the import
- Remove BaseGridWidget dependency
- Update to work standalone
- Less recommended as it maintains obsolete code

### Phase 2: Update Test Files

#### Task 2.1: Update test_shot_grid_widget.py
```python
# Old import
from shot_grid import ShotGrid

# New import
from shot_grid_view import ShotGridView
from shot_item_model import ShotItemModel
```
- Update all `ShotGrid` references to `ShotGridView`
- Add model initialization where needed
- Adjust test methods for Model/View pattern

#### Task 2.2: Update test_previous_shots_grid.py
```python
# Old import
from previous_shots_grid import PreviousShotsGrid

# New import
from previous_shots_view import PreviousShotsView
from previous_shots_item_model import PreviousShotsItemModel
```
- Update all `PreviousShotsGrid` references to `PreviousShotsView`
- Add model initialization where needed
- Adjust test methods for Model/View pattern

#### Task 2.3: Update test_threede_shot_grid.py
```python
# Old import
from threede_shot_grid import ThreeDEShotGrid

# New import
from threede_grid_view import ThreeDEGridView
from threede_item_model import ThreeDEItemModel
```
- Update all `ThreeDEShotGrid` references to `ThreeDEGridView`
- Add model initialization where needed
- Adjust test methods for Model/View pattern

### Phase 3: Validation

#### Task 3.1: Run Fast Tests
```bash
source venv/bin/activate
./run_fast_tests.sh
```
Expected: All import errors resolved

#### Task 3.2: Run Specific Updated Tests
```bash
python -m pytest tests/unit/test_shot_grid_widget.py -v
python -m pytest tests/unit/test_previous_shots_grid.py -v
python -m pytest tests/unit/test_threede_shot_grid.py -v
```

#### Task 3.3: Run Full Integration Tests
```bash
python -m pytest tests/integration/test_main_window_complete.py -v
```

#### Task 3.4: Run Complete Test Suite
```bash
python -m pytest tests/ -v
```

### Phase 4: Cleanup

#### Task 4.1: Remove Obsolete Files
- Delete threede_shot_grid.py if Option A chosen
- Remove any .pyc files from deleted modules
- Clean __pycache__ directories

#### Task 4.2: Update Documentation
- Update CLAUDE.md if module list changed
- Document Model/View migration completion

## Expected Outcomes

### Success Criteria
1. ✅ No import errors in test collection
2. ✅ Fast test suite runs without errors
3. ✅ Integration tests pass
4. ✅ Full test suite achieves >99% pass rate

### Benefits
- Consistent Model/View architecture throughout
- Cleaner codebase without obsolete modules
- Maintainable test suite aligned with current architecture
- Foundation for future enhancements

## Risk Mitigation

### Backup Strategy
- All deleted files recoverable from git history (commit 707ce6c4^)
- Can restore if needed: `git checkout 707ce6c4^ -- <filename>`

### Rollback Plan
If issues arise:
1. `git stash` current changes
2. `git checkout 707ce6c4^ -- base_grid_widget.py shot_grid.py previous_shots_grid.py`
3. Tests will work with old modules restored
4. Investigate alternative migration approach

## Timeline
- **Phase 1**: 5 minutes (decision + optional deletion)
- **Phase 2**: 30-45 minutes (update 3-4 test files)
- **Phase 3**: 15-20 minutes (run validation tests)
- **Phase 4**: 5 minutes (cleanup)
- **Total**: ~1 hour

## Notes
- The unified cache strategy implementation is working correctly and not affected by these issues
- These are pre-existing issues from the Model/View migration, not new problems
- Fixing these will establish a clean baseline for future development