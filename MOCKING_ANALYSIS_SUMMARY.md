# Mocking Strategy Analysis - Quick Reference

## Key Findings at a Glance

### The Big Picture
- **118 test files** with comprehensive mocking strategies
- **8 distinct mocking patterns** identified across the codebase
- **Transition in progress**: Moving from `unittest.mock` to custom test doubles
- **~25% of tests over-mocked**, especially in filesystem and widget operations
- **2-3 parallel test failures** correlate directly with over-mocking

---

## 8 Mocking Patterns Found

| # | Pattern | Extent | Assessment |
|---|---------|--------|-----------|
| 1 | Subprocess mocking (@patch, MagicMock) | 40+ files | ✅ Appropriate - system boundary |
| 2 | Qt Widget mocking (Mock()) | 25+ files | ⚠️ Partially over-mocked - 30-40% could improve |
| 3 | Qt Signals with QSignalSpy | 15+ files | ✅ Best practice - real components |
| 4 | Custom test doubles (18 classes) | Emerging | ✅ Good strategy - behavior-focused |
| 5 | Configuration mocking (monkeypatch) | 30+ files | ✅ Appropriate - test infrastructure |
| 6 | Real filesystem (tmp_path) | 20+ files | ✅ Best practice - no mocking needed |
| 7 | Path operation mocking (@patch Path.*) | 15+ files | ⚠️ Over-mocked - should use tmp_path |
| 8 | Protocol stubs (conftest.py) | Global | ✅ Appropriate - minimal protocol impl |

---

## Distribution: How Tests Are Mocked

```
Minimal Mocking (Real Components) ............ 40%  ✅ Good
- Real Shot objects, signals, models
- Examples: test_shot_model.py, test_base_item_model.py

Moderate Mocking (Appropriate) ............... 35%  ✅ Good
- System boundaries (subprocess)
- Configuration isolation (monkeypatch)
- Minimal widget stubs

Heavy Mocking (Over-Mocked) ................. 25%  ⚠️ Problem
- Path operations (@patch pathlib.Path)
- File I/O mocking
- Widget tree mocking
- Complex mock chains
```

---

## Problem Areas (Over-Mocking)

### 1. Path Operation Mocking (15+ files) - HIGH PRIORITY
**Current Bad Pattern**:
```python
@patch("pathlib.Path.exists")
@patch("pathlib.Path.iterdir")
def test_find_media(self, mock_iterdir, mock_exists):
    mock_exists.return_value = True
    # Tests mock behavior, not actual logic
```

**Better Pattern**:
```python
def test_find_media(self, tmp_path: Path):
    test_dir = tmp_path / "media"
    test_dir.mkdir()
    (test_dir / "test.nk").write_text("data")
    # Tests real behavior
```

**Files Affected**:
- `test_nuke_media_detector.py` - 8+ Path patches
- `test_nuke_undistortion_parser.py` - 6+ patches
- `test_persistent_terminal_manager.py` - 10+ patches

**ROI**: High - Medium effort for clear improvement

---

### 2. Qt Widget Over-Mocking (25-30% of tests)
**Current Bad Pattern**:
```python
# conftest.py lines 1748-1787
window = Mock()
window.launcher_panel = Mock()
window.log_viewer = Mock()
window.status_bar = Mock()
window.custom_launcher_menu = Mock()  # 10+ more
# No actual behavior - just stubs
```

**Files Affected**:
- `test_refresh_orchestrator.py` - 15+ Mock() attributes
- `test_cleanup_manager.py` - 10+ Mock() attributes
- `test_launcher_controller.py` - 8+ Mock() stubs
- `test_main_window.py` - Entire MainWindow as MagicMock

**Why It's a Problem**:
- Parallel tests fail (2-3 failures observed)
- Mock state doesn't synchronize across threads
- Tests don't catch real signal issues

**Solution**: Use minimal real widgets or proper test doubles

**ROI**: Medium effort for flakiness elimination

---

### 3. Subprocess Mocking Inconsistency (35% inconsistent)
**Problem**: Mix of approaches - some use TestSubprocess (good), some use MagicMock (lazy)

**Files to Standardize**:
- `test_launcher_process_manager.py` - Inconsistent MagicMock usage
- `test_launcher_worker.py` - Mix of approaches
- `test_command_launcher.py` - Multiple patterns

**ROI**: Low effort, high clarity improvement

---

## Good Examples (Best Practices)

### Pattern 1: Real Behavior Testing
```python
# test_shot_model.py
def test_refresh_shots(self):
    model = ShotModel()
    success, has_changes = model.refresh_shots()
    assert success == True  # Tests behavior, not mocks
```

### Pattern 2: System Boundary Mocking Only
```python
# test_launcher_workflow_integration.py
with patch("subprocess.Popen") as mock_popen:  # Only at boundary
    mock_popen.return_value = self.mock_process
    launcher_manager.execute(...)
    # Everything else is real behavior
```

### Pattern 3: Test Doubles Over Mock()
```python
# test_process_pool_manager.py
pool = TestProcessPool()  # Has real behavior
pool.set_outputs("result")
result = pool.execute_command("test")
assert "result" in result  # Real parsing
```

---

## Metrics Summary

| Metric | Current | Assessment |
|--------|---------|-----------|
| Files with @patch | 45-50 | High but expected (subprocess) |
| Files with Mock() | 25-30 | Moderate (some defensive) |
| Files with test doubles | 18 | Good baseline |
| Avg mock setup lines | 8-12 | Higher than ideal (<5) |
| Files with 10+ Mocks | 12 | Problem area |
| Estimated over-mocking % | ~25% | Significant improvement possible |

---

## Actionable Recommendations

### Immediate (Week 1) - High ROI
1. **Fix Path mocking** (15+ files affected)
   - Replace `@patch("pathlib.Path.*")` with `tmp_path`
   - 2-4 hour effort per file, significant clarity improvement
   - Files: `test_nuke_media_detector.py`, `test_persistent_terminal_manager.py`, etc.

2. **Standardize subprocess patterns** (90% done - finish it)
   - Consolidate on `TestSubprocess` class
   - 1-2 hour effort across 5-10 files
   - Better test readability

3. **Reduce conftest.py Mock() objects**
   - Change from 10+ Mocks to 2-3 minimal stubs
   - Might fix 2-3 parallel test failures
   - 3-4 hour effort, high reliability improvement

### Short-term (Weeks 2-3)
4. Create test doubles for common UI patterns
5. Add type hints to Mock() objects
6. Establish "mock complexity budget" (≤5 lines for setup)

### Long-term (Weeks 4-8)
7. Complete @patch audit - justify or remove each one
8. Add CI check for mocking anti-patterns
9. Make MOCKING_REFACTORING_GUIDE mandatory

---

## Key Insights

### Insight 1: Strategic Over-Mocking is Intentional
The team purposefully over-mocks:
- Qt components (avoid environment issues)
- Subprocess calls (avoid external dependencies)
- Configuration (test isolation)

This is **appropriate** for a VFX desktop app in a single-user environment.

### Insight 2: Test Double Strategy is Sound
The `test_doubles_library.py` with 18 test doubles shows a deliberate shift toward:
- Behavior-focused testing
- Realistic mock behavior (not just stubs)
- Type-safe testing patterns

This is **aligned with modern Python testing best practices**.

### Insight 3: Over-Mocking Causes Flakiness
The 2-3 parallel test failures correlate with excessive Mock() usage:
- Mock objects don't synchronize across threads
- Real components would force correct behavior
- This is a **fixable issue** with medium effort

### Insight 4: Mixed Strategy is Correct
The codebase properly distinguishes:
- **Real components**: Models, signals, business logic
- **Test doubles**: Subprocess, process pools, cache
- **Mock stubs**: UI protocol verification only
- **Mocking**: Only at system boundaries

This is the **recommended modern approach**.

---

## Parallel Test Failures Root Cause

**Observation**: 2-3 tests fail in parallel execution

**Root Cause**: Excessive `Mock()` objects without proper synchronization

**Tests Affected**:
- `test_launcher_controller.py` - Mock() widgets
- `test_main_window.py` - MagicMock MainWindow
- `test_refresh_orchestrator.py` - Mock state coordination

**Why It Happens**:
```
Parallel Execution
    ↓
Multiple Mock() instances created in same worker
    ↓
Mock state not synchronized (e.g., signals don't fire)
    ↓
Tests pass individually, fail in parallel
    ↓
Real components or proper test doubles would sync automatically
```

**Fix**: Replace Mock() with minimal real widgets or proper test doubles

---

## Files Needing Refactoring (Priority Order)

### High Priority (Major Impact)
1. `test_nuke_media_detector.py` - Replace Path mocking (8+ patches)
2. `test_persistent_terminal_manager.py` - Replace os.path mocking (10+ patches)
3. `conftest.py` - Reduce Widget Mock() objects (10+ per fixture)

### Medium Priority (Consistency)
4. `test_nuke_undistortion_parser.py` - Consolidate file mocking
5. `test_launcher_process_manager.py` - Standardize subprocess mocking
6. `test_refresh_orchestrator.py` - Real components or better stubs

### Low Priority (Nice to Have)
7. Extract common Mock patterns into reusable test doubles
8. Add type hints to prevent silent Mock failures
9. Document why each @patch is necessary

---

## Overall Assessment

**The strategy is fundamentally sound** with clear best practices documented (UNIFIED_TESTING_GUIDE) and intentional patterns. Room for optimization is mainly about:

1. **Consistency** - Complete the shift to test doubles
2. **Coverage** - Reduce over-mocking in low-value areas
3. **Clarity** - Simplify complex mock chains
4. **Reliability** - Fix parallel test failures by using real components

**Estimated effort to optimize**: 2-3 weeks for significant improvement

**Expected gains**:
- 30-40% reduction in mock setup complexity
- Fix 2-3 parallel test failures
- Improved test clarity and maintainability
- Better behavior-focused testing

---

## Next Steps

1. **Review** this analysis with team
2. **Prioritize** refactoring targets
3. **Implement** high-priority fixes (Path mocking → tmp_path)
4. **Monitor** parallel test improvement
5. **Enforce** best practices in new tests

See **MOCKING_STRATEGY_ANALYSIS.md** for detailed analysis with code examples.
