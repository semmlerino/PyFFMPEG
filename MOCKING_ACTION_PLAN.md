# Mocking Optimization Action Plan
**Based on pytest best practices verification via context7**

## TL;DR

✅ **Your mocking strategy is 70% optimal** - You're already doing test doubles, system boundary mocking, and real Qt widgets correctly.

⚠️ **20% needs optimization** - Path operations should use `tmp_path` instead of mocks.

🎯 **Quick wins**: 2-3 hours to fix Path mocking in 2 files eliminates 17 anti-patterns.

---

## What's Already Excellent (Keep These)

### 1. Test Doubles Library ✅
**Location**: `tests/test_doubles_library.py`
**Quality**: Exemplary

Your test doubles are **better than standard Mock() usage**:
- `TestSubprocess` - Real behavior, not just return values
- `TestCompletedProcess` - Proper subprocess simulation
- `ThreadSafeTestImage` - Thread-safe Qt image handling
- `SignalDouble` - Real signal emission for Qt tests

**No changes needed** - This is best-in-class.

### 2. Qt Headless Testing ✅
**Location**: `tests/conftest.py`
**Quality**: Appropriate

Your Qt widget visibility patching matches pytest-qt best practices:
```python
QWidget.show = _mock_widget_show  # Prevents actual display
_virtually_visible_widgets.add(id(self))  # Tracks state
```

**No changes needed** - This is correct for headless CI/CD.

### 3. Real Widget Testing ✅
**Pattern**: Using `qtbot` with real widgets
**Quality**: Correct per pytest-qt docs

```python
def test_launcher_panel(qtbot):
    panel = LauncherPanel()  # Real widget
    qtbot.addWidget(panel)    # Lifecycle management
    panel.launch_button.click()  # Real interaction
```

**No changes needed** - This matches pytest-qt recommendations.

---

## What Needs Optimization

### Priority 1: Path Operation Mocking ⚠️
**Impact**: High | **Effort**: Low (2-3 hours) | **ROI**: Excellent

#### Problem
17 tests mock `pathlib.Path.exists` and `pathlib.Path.iterdir` when they should use real filesystem.

#### Files Affected
1. **tests/unit/test_nuke_media_detector.py** (10 tests)
   - `test_detect_frame_range_with_hash_pattern`
   - `test_detect_frame_range_with_printf_pattern`
   - `test_detect_frame_range_no_matching_files`
   - `test_detect_frame_range_exception_handling`
   - `test_detect_media_properties_with_frame_detection`
   - (+ 5 more)

2. **tests/unit/test_nuke_undistortion_parser.py** (7 tests)
   - `test_parse_undistortion_file_nonexistent`
   - `test_parse_copy_paste_format_detection`
   - `test_parse_copy_paste_format_basic`
   - (+ 4 more)

#### Solution Template
```python
# BEFORE
@patch("pathlib.Path.exists")
@patch("pathlib.Path.iterdir")
def test_something(mock_iterdir, mock_exists):
    mock_exists.return_value = True
    mock_iterdir.return_value = [MagicMock(name="file.txt")]

# AFTER
def test_something(tmp_path: Path):
    (tmp_path / "file.txt").touch()
```

#### Why This Matters
- ✅ Real filesystem tests catch more bugs
- ✅ Simpler code (no mock setup)
- ✅ Faster execution (tmp_path is optimized)
- ✅ Tests edge cases (permissions, encoding)

#### Estimated Time
- ~10 minutes per test method
- Total: 2-3 hours for all 17 tests

---

### Priority 2: Expand tmp_path Usage ⚠️
**Impact**: Medium | **Effort**: Medium (4-6 hours) | **ROI**: Good

#### Problem
Only 5 test files use `tmp_path`, but 30+ files could benefit.

#### Current Good Examples
```python
# tests/unit/test_cache_manager.py - EXCELLENT
@pytest.fixture
def cache_manager(tmp_path: Path):
    return CacheManager(cache_dir=tmp_path / "cache")

# tests/unit/test_base_asset_finder.py - EXCELLENT
def test_find_assets(tmp_path: Path):
    (tmp_path / "asset.exr").touch()
```

#### Candidates for Migration
Search for these patterns to find candidates:
```bash
# Find tests mocking file operations
grep -r "@patch.*open" tests/unit/*.py
grep -r "@patch.*Path\." tests/unit/*.py
grep -r "Mock.*file" tests/unit/*.py
```

#### Migration Criteria
Use `tmp_path` when test:
- Creates/reads/writes files
- Checks file existence
- Lists directories
- Tests file permissions
- Handles file encoding

DON'T use `tmp_path` when:
- Mocking system boundaries (subprocess, network)
- Testing logic that doesn't touch filesystem
- Performance testing (use in-memory data)

---

### Priority 3: Mock() Audit (Optional) ℹ️
**Impact**: Low | **Effort**: High (8-10 hours) | **ROI**: Code quality only

#### Problem
288 `Mock()` instances - some might be unnecessary.

#### Audit Process
For each `Mock()` usage, ask:

1. **Is this a system boundary?**
   - YES → Keep (subprocess, network, external API)
   - NO → Continue to question 2

2. **Could this be a test double?**
   - YES → Use/create test double from test_doubles_library.py
   - NO → Continue to question 3

3. **Could this be a real object?**
   - YES → Use real object (dataclass, Qt widget, etc.)
   - NO → Keep mock (but document why)

#### Examples

**KEEP**: System boundary mock
```python
# Good: External process is system boundary
mock_process = Mock(spec=subprocess.Popen)
```

**REPLACE**: Mock of your own code
```python
# Bad: Mocking your own Shot class
mock_shot = Mock(spec=Shot)
mock_shot.name = "shot010"

# Good: Use real Shot object
shot = Shot("show", "seq", "shot010", "/path")
```

**Low priority** - This is optimization, not bug fixing.

---

## Implementation Roadmap

### Week 1: Quick Wins (Priority 1)
**Goal**: Eliminate Path operation mocking
**Effort**: 2-3 hours
**Impact**: Removes 17 anti-patterns

**Tasks**:
- [ ] Day 1: Refactor `test_nuke_media_detector.py` (10 tests)
- [ ] Day 2: Refactor `test_nuke_undistortion_parser.py` (7 tests)
- [ ] Day 3: Run full test suite, verify all pass
- [ ] Day 4: Update documentation

**Success Metrics**:
```bash
# Should be 0
grep -r "@patch.*pathlib.Path" tests/unit/*.py | wc -l

# Should increase from 5 to ~12
grep -r "def test.*tmp_path" tests/unit/*.py | wc -l
```

### Week 2-3: Expand tmp_path (Priority 2)
**Goal**: Increase tmp_path usage across test suite
**Effort**: 4-6 hours
**Impact**: Better filesystem testing

**Tasks**:
- [ ] Identify 20 more candidates (grep for file mocking)
- [ ] Refactor 5-10 tests per day
- [ ] Run tests incrementally
- [ ] Document migration patterns

**Success Metrics**:
```bash
# Should be 30+
grep -r "def test.*tmp_path" tests/unit/*.py | wc -l
```

### Month 2+: Mock() Audit (Priority 3 - Optional)
**Goal**: Replace unnecessary Mock() with test doubles/real objects
**Effort**: 8-10 hours (spread over time)
**Impact**: Code quality, not critical

**Tasks**:
- [ ] Audit 10 Mock() usages per week
- [ ] Replace with test doubles where appropriate
- [ ] Create new test doubles as needed
- [ ] Update test_doubles_library.py

---

## Validation Commands

### Before Refactoring (Baseline)
```bash
# Path mocking count (target: 0)
grep -r "@patch.*pathlib.Path" tests/unit/*.py | wc -l
# Current: 17

# tmp_path usage (target: 30+)
grep -r "def test.*tmp_path" tests/unit/*.py | wc -l
# Current: 5

# Test double usage (keep high)
grep -r "TestSubprocess\|TestCompletedProcess" tests/ | wc -l
# Current: 100+
```

### After Week 1 (Expected)
```bash
grep -r "@patch.*pathlib.Path" tests/unit/*.py | wc -l
# Expected: 0 ✅

grep -r "def test.*tmp_path" tests/unit/*.py | wc -l
# Expected: 12+ ✅
```

### After Week 2-3 (Expected)
```bash
grep -r "def test.*tmp_path" tests/unit/*.py | wc -l
# Expected: 30+ ✅
```

---

## Quick Reference: When to Use What

| Scenario | Tool | Example |
|----------|------|---------|
| Testing file I/O | `tmp_path` | `(tmp_path / "config.json").write_text(...)` |
| Testing subprocess | Test double | `test_subprocess.set_response(b"output")` |
| Testing Qt widgets | Real widget + `qtbot` | `qtbot.addWidget(MyWidget())` |
| Mocking dialog response | `monkeypatch` | `monkeypatch.setattr(QMessageBox, "question", ...)` |
| Testing your logic | Real objects | `shot = Shot("show", "seq", "shot010", "/path")` |
| Testing external API | `Mock()` or test double | `Mock(spec=ExternalAPI)` |

---

## Resources

### Created Documentation
1. **MOCKING_VERIFICATION_REPORT.md** - Full analysis with verification
2. **MOCKING_REFACTORING_EXAMPLES.md** - Before/after code examples
3. **This file** - Action plan and roadmap

### pytest Documentation (via context7)
- pytest-mock: System boundary mocking patterns
- pytest-qt: Widget testing with qtbot
- pytest fixtures: tmp_path usage and best practices

### Your Existing Guides
- `tests/unit/UNIFIED_TESTING_GUIDE.md` - Your testing philosophy
- `tests/test_doubles_library.py` - Exemplary test doubles

---

## Decision Framework

### "Should I mock this?"
```
┌─────────────────────────────────┐
│ Is this a system boundary?      │
│ (subprocess, network, external) │
└─────────┬───────────────────────┘
          │
    ┌─────┴─────┐
    │ YES       │ NO
    │           │
    ▼           ▼
 ┌────┐    ┌──────────────────┐
 │MOCK│    │ Is this file I/O?│
 └────┘    └─────┬────────────┘
                 │
           ┌─────┴─────┐
           │ YES       │ NO
           │           │
           ▼           ▼
      ┌─────────┐  ┌──────────────┐
      │tmp_path │  │ Use real obj │
      └─────────┘  └──────────────┘
```

---

## Next Steps

1. ✅ **Review this action plan** - Understand priorities
2. ✅ **Read MOCKING_REFACTORING_EXAMPLES.md** - See code examples
3. 🎯 **Start with Week 1 tasks** - High ROI, low effort
4. 📊 **Track progress** - Use validation commands
5. 🔄 **Iterate** - Expand tmp_path usage over time

**Questions? Consult**:
- pytest-mock docs (context7)
- pytest-qt docs (context7)
- Your UNIFIED_TESTING_GUIDE.md
- MOCKING_VERIFICATION_REPORT.md (this analysis)
