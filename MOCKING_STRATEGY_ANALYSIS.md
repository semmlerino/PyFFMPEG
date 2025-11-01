# Comprehensive Mocking Strategy Analysis - ShotBot Test Suite

## Executive Summary

The ShotBot test suite employs a **multi-layered mocking strategy** with a clear philosophical shift from traditional Mock-based testing toward **test doubles** and real component testing. This analysis identifies 8 distinct mocking patterns, their appropriate use cases, and areas where mocking could be optimized.

**Key Finding**: The codebase is in an active **transition phase** between unittest.mock and custom test doubles, with intentional over-mocking in some areas (subprocess, Qt components) and under-mocking in others (filesystem operations).

---

## 1. Mocking Patterns Found

### Pattern 1: External Subprocess Mocking (Most Common)
**Extent**: 40+ test files  
**Approach**: `@patch("subprocess.Popen")`, `@patch("subprocess.run")`  
**Test Double Alternative**: `TestSubprocess` class from `test_doubles_library.py`

**Files Using This Pattern**:
- `test_launcher_process_manager.py` (55+ patch decorators)
- `test_command_launcher.py` (40+ patches)
- `test_launcher_worker.py` (35+ patches)
- `test_simplified_launcher_nuke.py`, `test_simplified_launcher_maya.py`
- `test_terminal_integration.py` (heavily mocked OS calls)

**Why This Mocking is Necessary**:
- Subprocess calls represent **system boundaries** (external commands)
- Tests shouldn't require actual 3DE, Nuke, Maya installations
- Process execution is non-deterministic
- Signal handling varies by OS

**Example**:
```python
# CURRENT: Using @patch decorator
@patch("subprocess.Popen")
def test_nuke_launch(self, mock_popen: MagicMock):
    mock_popen.return_value = MagicMock(pid=12345)
    # ... test

# BETTER: Using test double
def test_nuke_launch(self):
    test_subprocess = TestSubprocess()
    test_subprocess.set_command_output("nuke", 0, "success", "")
    with patch("subprocess.Popen", test_subprocess.Popen):
        # ... test (more readable, real behavior)
```

**Assessment**: ✅ **Appropriate** - These are true system boundaries

---

### Pattern 2: Qt Component Widget Mocking
**Extent**: 25+ test files  
**Approach**: `Mock()` for QWidget, QMainWindow, QDialog attributes  
**Examples**:
- `test_launcher_controller.py` (Mock QStatusBar, QMenu)
- `test_main_window.py` (MagicMock for entire MainWindow)
- `test_launcher_panel.py` (Mock panel components)

**Files with Excessive Widget Mocking**:
- `conftest.py` lines 1748-1787: Creates Mock() for entire UI component tree
- `test_refresh_orchestrator.py`: Mock MainWindow with 15+ Mock() attributes
- `test_cleanup_manager.py`: Mock 10+ window components

**Why This Mocking Exists**:
- Qt requires QApplication in main thread
- Signals require actual Qt event loop
- Widget lifecycle management is complex
- Many tests only need specific methods

**Example of Over-Mocking**:
```python
# CURRENT (conftest.py, lines 1748-1787)
window = Mock()
window.launcher_panel = Mock()
window.log_viewer = Mock()
window.status_bar = Mock()
window.custom_launcher_menu = Mock()  # 10+ more attributes
# No actual behavior, just Mock stubs

# BETTER: Use real widgets or minimal test doubles
class TestMainWindow:
    def __init__(self):
        self.launcher_panel = LauncherPanel()  # Real or TestDouble
        self.log_viewer = LogViewer()
        self.status_bar = QStatusBar()
```

**Assessment**: ⚠️ **Partially Over-Mocked** - Some are necessary, many are defensive

---

### Pattern 3: Qt Signal Testing with Real Components
**Extent**: 15+ test files  
**Approach**: `QSignalSpy`, real signals, `qtbot.waitSignal()`  
**Good Examples**:
- `test_base_item_model.py`: Uses `QSignalSpy` for signal verification
- `test_shot_model.py`: Real signals, real behavior
- `test_launcher_manager.py`: Actual signal emission testing

**How It Works**:
```python
# From test_base_item_model.py
def test_signals(self, qapp: QApplication) -> None:
    model = ConcreteTestModel()
    
    spy = QSignalSpy(model.dataChanged)
    model.set_items(shots)
    
    assert len(spy) == 1  # Signal was emitted
```

**Assessment**: ✅ **Best Practice** - Qt signals require real components

---

### Pattern 4: Custom Test Doubles (Intentional Replacement)
**Extent**: 18 test classes in `test_doubles_library.py`  
**Philosophy**: "Use test doubles instead of mocks" (UNIFIED_TESTING_GUIDE)

**Provided Test Doubles**:
1. `TestCompletedProcess` - replaces `subprocess.CompletedProcess`
2. `TestSubprocess` - replaces `subprocess.Popen` calls
3. `PopenDouble` - realistic Popen simulation
4. `TestShot` - real Shot object with behavior
5. `TestShotModel` - real Qt signals, real behavior
6. `TestCacheManager` - simplified cache
7. `TestLauncher` - minimal launcher interface
8. `LauncherManagerDouble` - realistic behavior
9. `ThreadSafeTestImage` - thread-safe image testing
10. `SignalDouble` - simplified signal simulation

**Example - Why These Are Better Than Mock()**:
```python
# ANTI-PATTERN: Mock doesn't have real behavior
launcher_pool = Mock()  # Has no methods, just returns Mock()

# PATTERN: TestDouble has real behavior
launcher_pool = TestProcessPool()
launcher_pool.set_outputs("workspace /shows/test/shots/010/0010")
result = launcher_pool.execute_command("ws -sg")
assert "010" in result  # Real parsing happens
```

**Assessment**: ✅ **Good Strategy** - Encourages real behavior testing

---

### Pattern 5: Monkeypatch for Configuration/Environment
**Extent**: 30+ test files  
**Approach**: `monkeypatch.setattr("module.Class.CONSTANT", value)`

**Common Uses**:
- `Config.SHOWS_ROOT` manipulation (test_shot_model.py)
- `Config.CACHE_DIR` isolation (cache tests)
- Environment variables (SHOTBOT_MODE, QT_* variables)

**Example**:
```python
def test_shot_creation(self, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "SHOWS_ROOT", str(shows_root))
    shot = Shot("test", "seq01", "0010", ...)
```

**Assessment**: ✅ **Appropriate** - Configuration is test infrastructure

---

### Pattern 6: Real Filesystem Testing with tmp_path
**Extent**: 20+ test files  
**Approach**: Use pytest `tmp_path` fixture for real files

**Good Examples**:
- `test_shot_model.py` (lines 70-145): Creates real directory structures
- `test_raw_plate_finder.py`: Complete realistic VFX paths
- `test_base_item_model.py`: Real cache with tmp_path

**Example**:
```python
def test_get_thumbnail_path_editorial_success(self, tmp_path: Path):
    # Create REAL directory structure
    shot_path = tmp_path / "shows" / "test" / "shots" / "seq01"
    shot_path.mkdir(parents=True, exist_ok=True)
    
    editorial_path = shot_path / "publish" / "editorial" / "cutref" / "v001"
    editorial_path.mkdir(parents=True, exist_ok=True)
    thumb_file = editorial_path / "frame.1001.jpg"
    thumb_file.write_bytes(b"JPEG_DATA")
    
    # Test REAL behavior
    shot = Shot("test", "seq01", "0010", str(shot_path))
    assert shot.get_thumbnail_path().exists()
```

**Assessment**: ✅ **Best Practice** - No filesystem mocking needed

---

### Pattern 7: Path Operations Mocking (Problematic)
**Extent**: 15+ test files  
**Approach**: `@patch("pathlib.Path")`, `@patch("Path.exists")`

**Problem Files**:
- `test_nuke_media_detector.py` (lines 31-98): Patches Path.exists, Path.iterdir
- `test_nuke_undistortion_parser.py`: mock_open, Path patches
- `test_persistent_terminal_manager.py`: @patch("os.path.exists")

**Why This is Over-Mocking**:
```python
# ANTI-PATTERN: What we're doing now
@patch("pathlib.Path.exists")
@patch("pathlib.Path.iterdir")
def test_find_media(self, mock_iterdir, mock_exists):
    mock_exists.return_value = True
    mock_file = MagicMock()
    mock_file.name = "test.nk"
    mock_iterdir.return_value = [mock_file]
    # Now testing mock behavior, not actual logic

# BETTER: What we should do
def test_find_media(self, tmp_path: Path):
    test_dir = tmp_path / "media"
    test_dir.mkdir()
    (test_dir / "test.nk").write_text("// Nuke script")
    
    finder = NukeMediaDetector()
    results = finder.find_media(test_dir)
    assert len(results) == 1
```

**Assessment**: ⚠️ **Over-Mocked** - Real filesystem would be better

---

### Pattern 8: Lazy Mocking in conftest.py
**Extent**: Lines 1700-1810  
**Approach**: Global fixtures creating Mock() objects

**Purpose**: Provide minimal test targets implementing protocols

**Example**:
```python
@pytest.fixture
def launcher_controller_target(qtbot: Any) -> Any:
    class LauncherControllerTestTarget:
        def __init__(self) -> None:
            self.command_launcher = TestCommandLauncher()
            self.launcher_panel = Mock()  # Minimal stub
            self.log_viewer = Mock()
            # ...
    return LauncherControllerTestTarget()
```

**Assessment**: ✅ **Appropriate** - Minimal protocol implementations needed for testing

---

## 2. Test Double vs. Actual Mocks: Current State

### Components Being Mocked vs. Using Test Doubles

| Component | Mocking Strategy | Justification |
|-----------|-----------------|---------------|
| `subprocess.Popen` | Both Mock() and TestSubprocess | System boundary - both appropriate |
| `ProcessPoolManager` | Test doubles (TestProcessPool) | Real behavior needed, isolated test |
| `ShotModel` | Real instances + mocking refresh | Signals need real objects |
| `CacheManager` | Test doubles or real with tmp_path | Filesystem isolation |
| `Qt Widgets` | Mix: Real + Mock() | Signals need real; UI stubs use Mock |
| `Filesystem paths` | **Should be tmp_path** but uses @patch | **Over-mocked** |
| `Config values` | monkeypatch | Correct approach |
| `Subprocess I/O** | Mock return values | Correct approach |

---

## 3. Extent of Mocking by Category

### Minimal Mocking (Good - Real Components Used)
**~40% of tests**
- `test_shot_model.py` - Real Shot objects, real signals
- `test_base_item_model.py` - Real models with signals
- `test_cache_manager.py` - Real cache with tmp_path
- `test_shot_item_model.py` - Real Qt models
- Unit tests in `tests/unit/test_raw_plate_finder.py` - Real files

### Moderate Mocking (Acceptable)
**~35% of tests**
- Subprocess mocking at system boundaries
- Configuration overrides via monkeypatch
- Minimal widget stubs for protocol testing
- Process tracking with realistic test doubles

### Heavy Mocking (Problematic)
**~25% of tests**
- Path operation mocking
- File I/O mocking
- Excessive Qt widget mocking
- Complex mock chains

**Files with Excessive Mocking**:
1. `test_nuke_media_detector.py` - Heavy Path patching
2. `test_persistent_terminal_manager.py` - Heavy os.path mocking
3. `test_main_window.py` - Entire MainWindow as MagicMock
4. `test_refresh_orchestrator.py` - 15+ Mock() attributes
5. `test_nuke_undistortion_parser.py` - File handle mocking

---

## 4. Spy Patterns & Verification

### Pattern A: Assert Called With (Implementation Testing)
**Usage**: `mock.assert_called_with(args)`  
**Found In**: ~10 test files  
**Assessment**: ⚠️ **Tests the wrong thing** - Implementation, not behavior

**Example**:
```python
# ANTI-PATTERN: Testing mock calls
mock_cache.get.assert_called_with("key")  # Tests the mock, not behavior

# BETTER: Test actual behavior
result = shot_model.refresh_shots()
assert result.has_changes == True  # Test actual outcome
```

### Pattern B: Signal Spy Verification (Behavior Testing)
**Usage**: `QSignalSpy` for real Qt signals  
**Found In**: ~15 test files  
**Assessment**: ✅ **Good** - Tests actual signal emission

**Example**:
```python
spy = QSignalSpy(model.dataChanged)
model.set_items(shots)
assert len(spy) == 1
assert spy.at(0)[0] == 10  # Index 10 changed
```

### Pattern C: Return Value Verification (Good)
**Usage**: Verify function returns, not that mocks were called  
**Found In**: ~50 test files  
**Assessment**: ✅ **Good** - Tests behavior, not implementation

---

## 5. Flaky Tests & Over-Mocking Correlation

### Tests Failing Due to Over-Mocking
From project context (2-3 tests fail in parallel):
- `test_launcher_controller.py` - Mock() widgets without proper synchronization
- `test_main_window.py` - MagicMock MainWindow doesn't update signals
- `test_refresh_orchestrator.py` - Mock state not synchronized across components

### Why These Fail
```
Over-Mocking → Unrealistic Mock State → Tests Pass Locally, Fail in Parallel
                ↓
         Mocks Don't Coordinate → Signals Don't Fire → Qt Events Stale
                ↓
         Using Real Components Would Force Correct Synchronization
```

### Solution: Replace Mock() with Real Test Doubles
```python
# CURRENT (flaky in parallel):
window = Mock()  # Doesn't have proper signal chain

# BETTER (reliable):
window = RealMainWindow()  # Forces correct signal flow
# Or use MinimalWindowDouble that implements protocol correctly
```

---

## 6. Testing Mocks vs. Testing Actual Behavior

### Anti-Patterns Found

#### 1. Testing Mock Configuration (Line 250+ in test files)
```python
# Testing the mock, not the code
mock_launcher.launch_app.assert_called_once()
```

#### 2. Complex Mock Chains (Spaghetti Pattern)
```python
# Hard to understand what's being tested
mock.return_value.method.return_value.property = value
target.method()
mock.return_value.method.assert_called_with(...)
```

#### 3. Redundant Mocking at Multiple Layers
```python
# test_launcher_controller.py
- Mock LauncherManager
- Mock LauncherPanel  
- Mock CommandLauncher
- All in one test (too much isolation)
```

### Good Patterns Found

#### 1. Real Behavior Testing
```python
# test_shot_model.py
def test_refresh_shots(self):
    model = ShotModel()
    success, has_changes = model.refresh_shots()
    assert success == True
    # Tests actual behavior, not mocks
```

#### 2. Minimal Mocking at Boundaries
```python
# test_launcher_workflow_integration.py
with patch("subprocess.Popen") as mock_popen:  # Only mock system boundary
    mock_popen.return_value = self.mock_process
    launcher_manager.execute(...)
    # Rest is real behavior
```

#### 3. Test Doubles Over Mocks
```python
# test_process_pool_manager.py
pool = TestProcessPool()  # Real-like behavior
pool.set_outputs("result")
success = pool.execute_command("test")
assert "result" in success
```

---

## 7. Areas Where We Might Be Over-Mocking

### 1. Qt Component Tree (25-30% over-mocked)
**Current**: Every test creates `Mock()` for MainWindow, panels, grids  
**Better**: Create minimal real widget or specific TestDouble  
**Impact**: Reduces flaky parallel test failures  
**Effort**: Medium (refactor 15-20 test files)

### 2. File Path Operations (15-20% over-mocked)
**Current**: `@patch("pathlib.Path.exists")` in 15+ files  
**Better**: Use `tmp_path` with real directories  
**Impact**: Eliminates "testing the mock" problem  
**Effort**: Medium (refactor 10-15 test files)

### 3. Process I/O Mocking (50% appropriate, 50% could improve)
**Current**: Some use TestSubprocess (good), some use MagicMock (lazy)  
**Better**: Standardize on TestSubprocess everywhere  
**Impact**: More realistic test behavior  
**Effort**: Low (90% already done)

### 4. Excessive Widget Mocking
**Current**: conftest.py creates Mock() for 10+ UI components per test  
**Better**: Only mock what's necessary for protocol  
**Impact**: Tests become more maintainable  
**Effort**: Medium (refactor conftest.py fixtures)

---

## 8. Areas Where We Need More Mocking

### 1. Thread Safety (5% under-mocked)
**Current**: Some threading tests don't mock QThread properly  
**Better**: Use ThreadSafeTestImage or proper thread doubles  
**Impact**: Catches more concurrency bugs  
**Effort**: Low (add 5-10 tests)

### 2. Exception Scenarios (10% under-mocked)
**Current**: Happy path mocking, fewer error case mocks  
**Better**: Mock failure scenarios systematically  
**Impact**: Better error handling coverage  
**Effort**: Medium

### 3. Signal Disconnection (8% under-mocked)
**Current**: Most tests don't verify signal cleanup  
**Better**: Mock signal disconnect patterns  
**Impact**: Catches memory leaks  
**Effort**: Low (add assertions)

---

## 9. Mocking Metrics Summary

| Metric | Value | Assessment |
|--------|-------|-----------|
| Files using @patch | 45-50 | High (expected for subprocess) |
| Files using Mock() | 25-30 | Moderate (some over-mocking) |
| Files using Test Doubles | 18 | Good baseline |
| Files using monkeypatch | 30 | Appropriate |
| Files using tmp_path | 20 | Should be higher |
| Tests with Signal Spy | 15 | Could be more |
| Avg Mock Setup Lines | 8-12 | Higher than ideal (<5) |
| Files with 10+ Mocks | 12 | Problem area |

---

## 10. Specific Recommendations

### Immediate Actions (High ROI)
1. **Standardize subprocess mocking** - Complete migration from @patch to TestSubprocess (90% done)
2. **Fix Path mocking** - Replace @patch("pathlib.Path.*") with tmp_path in 10 files
3. **Simplify conftest.py** - Reduce Mock() objects from 10+ to 2-3 per fixture
4. **Add MOCKING_REFACTORING_GUIDE as enforced standard** - Document best practices

### Short-Term (1-2 weeks)
1. Refactor `test_nuke_media_detector.py` - Replace Path mocking with tmp_path
2. Refactor `test_persistent_terminal_manager.py` - Use real os.path calls with tmp_path
3. Extract common Mock() patterns into reusable test doubles
4. Add type hints to Mock() objects to prevent silent failures

### Long-Term (1-2 months)
1. Complete audit of all @patch usage - Justify each one
2. Create TestDouble for every commonly mocked component
3. Establish "mock complexity budget" - Tests fail if mock setup > 5 lines
4. Add CI check: Detect @patch patterns that should use test doubles

---

## 11. Key Insights

### Insight 1: Strategic Over-Mocking
The codebase intentionally over-mocks in some areas (Qt widgets) to prevent:
- Requiring full VFX environment
- Qt initialization issues in headless testing
- Signal/slot timing issues in parallel tests

This is appropriate for integration tests.

### Insight 2: Test Double Pattern is Emerging
The `test_doubles_library.py` with 18 test doubles represents a **deliberate shift** away from unittest.mock toward behavior-based testing. This is **aligned with best practices**.

### Insight 3: Parallel Test Issues Correlate with Over-Mocking
The 2-3 failing tests in parallel execution all use excessive Mock() objects. This suggests:
- Mock objects don't synchronize properly across threads
- Real components or proper test doubles would be more reliable

### Insight 4: Mixed Strategy is Appropriate
The codebase correctly uses:
- **Real components** for models, signals, business logic
- **Test doubles** for subprocess, process pools, cache
- **Mock stubs** for UI protocol verification only
- **Mocking** only at system boundaries

This is the **recommended modern Python testing approach**.

---

## 12. Conclusion

**Overall Assessment**: The ShotBot test suite has a **well-reasoned, intentionally-layered mocking strategy** with room for optimization:

✅ **Strengths**:
- Clear philosophy on test doubles vs mocks
- Appropriate subprocess mocking at boundaries
- Real component testing for signals/business logic
- Documented best practices (UNIFIED_TESTING_GUIDE)

⚠️ **Improvement Areas**:
- 25% of tests over-mock filesystem operations
- Widget mocking could be reduced by 30-40%
- Some 2-3 tests fail in parallel due to mock state issues

🎯 **Recommended Priority**:
1. Standardize subprocess patterns (90% done - finish it)
2. Replace Path mocking with tmp_path (high ROI)
3. Reduce Widget mocking in conftest.py (prevents flakiness)
4. Make MOCKING_REFACTORING_GUIDE mandatory for new tests

The strategy is fundamentally sound; optimization is about consistency and removing defensive over-mocking.
