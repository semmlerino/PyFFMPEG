# Test Suite Compliance - Quick Reference Guide

## At a Glance

| Aspect | Status | Score | Action |
|--------|--------|-------|--------|
| Qt Signal Testing | EXCELLENT | 95/100 | No changes needed |
| Fixture Isolation | GOOD | 88/100 | Systematize monkeypatch |
| Parallel Execution | EXCELLENT | 92/100 | Add xdist config to ini |
| Mocking Strategy | GOOD | 82/100 | Already excellent |
| Configuration | EXCELLENT | 95/100 | Minor enhancements |
| Code Quality | GOOD | 88/100 | Fix 5 time.sleep() |
| **OVERALL** | **GOOD** | **85/100** | **APPROVE** |

---

## Critical Findings

### ✅ What's Working Well

1. **Qt Signal Handling**
   - 87+ `qtbot.waitSignal()` calls used correctly
   - Proper timeout management
   - No brittle `time.sleep()` in signal tests

2. **Test Isolation**
   - 85+ files marked with `@pytest.mark.xdist_group("qt_state")`
   - Ensures serial execution in parallel runs
   - Prevents Qt state corruption

3. **Real Components**
   - 40+ CacheManager real instances (not mocked)
   - 60+ real Qt widgets
   - 30+ real file system operations

4. **Cleanup**
   - autouse `qt_cleanup` fixture handles Qt state
   - Proper `deleteLater()` cleanup
   - Context managers for temp directories

### ⚠️ Issues to Fix

**HIGH PRIORITY:**
```python
# Replace these 5 instances with qtbot.waitSignal()
Files:
  - test_cross_component_integration.py:99 (✗ time.sleep(0.01))
  - test_cross_component_integration.py:407 (✗ time.sleep(0.01))
  - test_cross_component_integration.py:570 (✗ time.sleep(0.01))
  - test_optimized_threading.py:97 (✗ time.sleep(0.1))
  - test_progress_manager.py:158 (✗ time.sleep(0.02))
```

**LOW PRIORITY:**
```ini
# Add to pytest.ini
[tool:pytest]
addopts =
    --dist=worksteal    # Better distribution than loadgroup
    -n auto             # Enable parallel by default
```

---

## Fixture Pattern Reference

### ✅ CORRECT - Session Scoped
```python
# Only use for QApplication (single instance required)
@pytest.fixture(scope="session")
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
```

### ✅ CORRECT - Function Scoped (Default)
```python
# Use for mutable state - fresh for each test
@pytest.fixture
def cache_manager(tmp_path: Path) -> CacheManager:
    return CacheManager(cache_dir=tmp_path / "cache")
```

### ✅ CORRECT - Global Isolation
```python
# Use monkeypatch for config changes
def test_something(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Config, "SHOWS_ROOT", "/tmp/test")
    # Test runs with isolated config
    # Automatically restored after test
```

### ❌ AVOID - Shared State
```python
# DON'T do this!
class TestExample:
    shared_data = []  # Shared between tests!
    
    def test_one(self):
        self.shared_data.append(1)
    
    def test_two(self):
        # This breaks if test_one doesn't run first
        assert len(self.shared_data) == 1
```

---

## Signal Testing Pattern

### ✅ CORRECT - Wait for Signal
```python
# Use qtbot.waitSignal for synchronous waiting
with qtbot.waitSignal(model.refresh_finished, timeout=1000):
    model.refresh()
    
# Signal was emitted, test continues
assert model.is_loaded()
```

### ✅ CORRECT - Verify Not Emitted
```python
# Use qtbot.assertNotEmitted to verify something doesn't happen
with qtbot.assertNotEmitted(worker.error_occurred, wait=100):
    worker.process()
    
# No error signal was emitted
assert worker.success
```

### ❌ AVOID - Sleep for Signals
```python
# DON'T do this!
model.refresh()
time.sleep(0.1)  # Brittle! May timeout or be too slow
assert model.is_loaded()
```

---

## Mocking Decision Tree

```
Need to test something...

   ├─ Qt component (widget, signal, model)?
   │  └─ Use REAL with qtbot fixture ✅
   │
   ├─ Business logic (calculation, validation)?
   │  └─ Use REAL code, not mocks ✅
   │
   ├─ External dependency (subprocess, network, file)?
   │  └─ Use MOCK at boundary ✅
   │
   ├─ Non-deterministic (time, random, uuid)?
   │  └─ Use MOCK for reproducibility ✅
   │
   ├─ Data structure (dict, list, class)?
   │  └─ Use REAL instance ✅
   │
   └─ Unsure?
      └─ Default to REAL component ✅
```

---

## Parallel Execution Checklist

When adding new Qt tests:

- [ ] Add `@pytest.mark.xdist_group("qt_state")` marker
- [ ] Use `qtbot` fixture for widget management
- [ ] Use `qtbot.waitSignal()` for async operations
- [ ] Use `tmp_path` for file operations
- [ ] Use `monkeypatch` for config changes
- [ ] Don't use `time.sleep()` for synchronization
- [ ] Don't use `QApplication.processEvents()` directly

---

## Running Tests

### Standard Execution
```bash
# Run all tests
uv run pytest

# Run only unit tests
uv run pytest -m unit

# Run excluding slow tests
uv run pytest -m "not slow"
```

### Parallel Execution
```bash
# Run with parallel workers (uses xdist_group for isolation)
uv run pytest -n auto

# Run with specific number of workers
uv run pytest -n 4

# Show which group each test belongs to
uv run pytest --verbose -n auto
```

### Debugging
```bash
# Stop on first failure
uv run pytest -x

# Show print statements
uv run pytest -s

# Run specific test
uv run pytest tests/unit/test_cache_manager.py::test_specific

# Run tests matching pattern
uv run pytest -k "cache" -v
```

---

## Common Mistakes & Fixes

### ❌ Using time.sleep() for signals
```python
# BAD
model.refresh()
time.sleep(0.1)  # May timeout, too slow, brittle
assert model.done

# GOOD
with qtbot.waitSignal(model.finished, timeout=1000):
    model.refresh()
assert model.done
```

### ❌ Not isolating Qt state
```python
# BAD - Qt tests without marker
def test_widget():  # May run in parallel, corrupts Qt state
    w = QWidget()

# GOOD
@pytest.mark.xdist_group("qt_state")
def test_widget():  # Runs serially with other Qt tests
    w = QWidget()
```

### ❌ Session-scoped mutable fixtures
```python
# BAD - Shared between tests
@pytest.fixture(scope="session")
def data():
    return []  # Same list for all tests!

# GOOD
@pytest.fixture
def data():  # Fresh list for each test
    return []
```

### ❌ Not cleaning up config changes
```python
# BAD
Config.SHOWS_ROOT = "/tmp/test"  # Leaks to other tests

# GOOD
def test_something(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Config, "SHOWS_ROOT", "/tmp/test")
    # Automatically restored after test
```

---

## For More Details

See `TEST_SUITE_COMPLIANCE_ANALYSIS.md` for:
- Detailed compliance metrics
- All findings with line numbers
- Specific recommendations
- Examples of best practices
- Future enhancement ideas

---

*Last updated: 2025-11-01*
*Analysis: 69,377 lines of test code across 100+ files*
