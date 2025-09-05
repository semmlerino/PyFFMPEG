# Quick Fix Guide - Model/View Test Infrastructure

## ⚡ Immediate Actions (Copy-Paste Ready)

### Step 1: Delete Orphaned Module (1 min)
```bash
rm threede_shot_grid.py
rm -rf __pycache__/threede_shot_grid*
git status
```

### Step 2: Fix test_shot_grid_widget.py (5 min)

**Line 31 - DELETE this line:**
```python
from shot_grid import ShotGrid  # Deprecated but still tested
```

**Find & Replace Throughout File:**
- `ShotGrid` → `ShotGridView`
- Add model initialization where needed

**Example Test Update:**
```python
# OLD (delete)
def test_shot_grid_init(qtbot):
    grid = ShotGrid()
    qtbot.addWidget(grid)
    
# NEW (replace with)
def test_shot_grid_view_init(qtbot):
    model = ShotItemModel()
    view = ShotGridView(model)
    qtbot.addWidget(view)
```

### Step 3: Fix test_previous_shots_grid.py (5 min)

**Line 22 - REPLACE:**
```python
# OLD
from previous_shots_grid import PreviousShotsGrid

# NEW
from previous_shots_view import PreviousShotsView
from previous_shots_item_model import PreviousShotsItemModel
```

**Find & Replace:**
- `PreviousShotsGrid` → `PreviousShotsView`
- Add `PreviousShotsItemModel` initialization

### Step 4: Fix test_threede_shot_grid.py (5 min)

**Line 13 - REPLACE:**
```python
# OLD
from threede_shot_grid import ThreeDEShotGrid

# NEW
from threede_grid_view import ThreeDEGridView
from threede_item_model import ThreeDEItemModel
```

**Find & Replace:**
- `ThreeDEShotGrid` → `ThreeDEGridView`
- Add `ThreeDEItemModel` initialization

### Step 5: Validate Each Fix (10 min)
```bash
# Test each file individually
pytest tests/unit/test_shot_grid_widget.py -xvs
pytest tests/unit/test_previous_shots_grid.py -xvs
pytest tests/unit/test_threede_shot_grid.py -xvs
```

### Step 6: Run Fast Tests (2 min)
```bash
./run_fast_tests.sh
# Should see: ✅ 600+ tests passed
```

### Step 7: Clean & Commit (2 min)
```bash
# Clean caches
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
rm -rf .pytest_cache

# Commit
git add -A
git commit -m "Fix test infrastructure after Model/View migration

- Remove orphaned threede_shot_grid.py
- Update tests to use Model/View components
- Fix import errors from deleted widget modules"
```

---

## 🔍 Common Patterns to Fix

### Pattern 1: Widget Creation
```python
# OLD PATTERN
widget = SomeGrid()
widget.do_something()

# NEW PATTERN
model = SomeItemModel()
view = SomeView(model)
view.do_something()
```

### Pattern 2: Signal Connections
```python
# OLD PATTERN
widget.signal.connect(handler)

# NEW PATTERN
model.signal.connect(handler)  # Most signals moved to model
# OR
view.signal.connect(handler)   # UI-specific signals stay on view
```

### Pattern 3: Data Access
```python
# OLD PATTERN
data = widget.get_data()

# NEW PATTERN
data = model.get_data()
```

---

## ✅ Success Checklist

- [ ] `threede_shot_grid.py` deleted
- [ ] No import errors when running: `pytest --collect-only`
- [ ] test_shot_grid_widget.py passes
- [ ] test_previous_shots_grid.py passes
- [ ] test_threede_shot_grid.py passes
- [ ] Fast test suite runs (./run_fast_tests.sh)
- [ ] Changes committed

---

## 🚨 If Something Goes Wrong

### Restore Deleted Files
```bash
git checkout 707ce6c4^ -- base_grid_widget.py
git checkout 707ce6c4^ -- shot_grid.py
git checkout 707ce6c4^ -- previous_shots_grid.py
```

### Revert Test Changes
```bash
git checkout HEAD -- tests/unit/test_shot_grid_widget.py
git checkout HEAD -- tests/unit/test_previous_shots_grid.py
git checkout HEAD -- tests/unit/test_threede_shot_grid.py
```

---

## 📊 Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Import Errors | 3 | 0 |
| Fast Tests | ❌ Fail | ✅ Pass |
| Test Count | ~1100 | ~1100 |
| Pass Rate | ~85% | >99% |
| Runtime | N/A | <120s |

---

**Time Estimate**: 30 minutes total
**Risk Level**: Low (only touching test files)
**Rollback Time**: 2 minutes