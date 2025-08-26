# Unified Testing Guide for ShotBot
*Optimized for LLM usage - Single source of truth*

## 🚀 QUICK START

### What Are You Testing? (Decision Tree)
```
IF testing Qt widget → Jump to "Qt Widget Pattern" (line 75)
ELIF testing worker thread → Jump to "Worker Thread Pattern" (line 91)  
ELIF testing 'ws' command → Jump to "TestProcessPoolManager" (line 124)
ELIF testing cache → Jump to "Cache Testing" (line 170)
ELIF testing signals → Jump to "Signal Testing" (line 110)
ELSE → Check Quick Lookup Table (line 268)
```

### Most Common Pattern (Copy & Paste)
```python
def test_widget(qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)  # CRITICAL: Register for cleanup
    
    qtbot.mouseClick(widget.button, Qt.LeftButton)
    assert widget.label.text() == "Expected"
```

### Factory Fixture Pattern (Modern Best Practice)
```python
@pytest.fixture
def make_shot():
    def _make(show="test", seq="seq1", shot="0010"):
        return Shot(show, seq, shot, f"/shows/{show}/{seq}/{shot}")
    return _make

def test_with_factory(make_shot):
    shot1 = make_shot()
    shot2 = make_shot(show="other")
```

## 📋 CORE PRINCIPLES

### Three Fundamental Rules
1. **Test Behavior, Not Implementation**
   ❌ mock.assert_called_once()  # Who cares?
   ✅ assert result.success       # Actual outcome

2. **Real Components Over Mocks**
   ❌ controller = Mock(spec=Controller)
   ✅ controller = Controller(process_pool=TestProcessPool())

3. **Mock Only at System Boundaries**
   - External APIs, Network calls
   - Subprocess calls
   - System time
   - NOT internal methods

### Mocking Decision Algorithm
```
FOR each dependency:
    IF crosses process boundary → Mock/TestDouble
    ELIF network/external API → Mock
    ELIF Qt widget/signal → Use real with qtbot
    ELIF internal method → Use real
```

## 🎯 COMMON PATTERNS

### Unit Test Pattern
```python
def test_pure_logic():
    # No mocks needed for pure functions
    result = calculate_something(input_data)
    assert result == expected
```

### Qt Widget Pattern
```python
def test_widget(qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    
    # Modern signal waiting
    with qtbot.waitSignal(widget.finished, timeout=1000):
        widget.start_operation()
    
    # Condition waiting (NEW)
    qtbot.waitUntil(lambda: widget.isReady(), timeout=1000)
```

### Worker Thread Pattern (CRITICAL - Thread Safety)
```python
def test_worker(qtbot):
    # ⚠️ NEVER use QPixmap in worker threads!
    worker = ImageWorker()
    
    # Use ThreadSafeTestImage instead
    image = ThreadSafeTestImage(100, 100)
    worker.set_image(image)
    
    with qtbot.waitSignal(worker.finished):
        worker.start()
    
    # Cleanup
    if worker.isRunning():
        worker.quit()
        worker.wait(1000)
```

### Signal Testing Pattern
```python
# Modern parameter checking (NEW)
def check_value(val):
    return val > 100

with qtbot.waitSignal(signal, check_params_cb=check_value):
    trigger_action()

# Negative testing with wait (NEW)
with qtbot.assertNotEmitted(signal, wait=100):
    other_action()
```

### TestProcessPoolManager Pattern ('ws' Command)
```python
# CRITICAL: 'ws' is a shell function, not executable!
def test_shot_refresh():
    model = ShotModel()
    
    test_pool = TestProcessPoolManager()
    test_pool.set_outputs(
        "workspace /shows/TEST/seq01/0010",
        "workspace /shows/TEST/seq01/0020"
    )
    model._process_pool = test_pool
    
    result = model.refresh_shots()
    assert result.success
```

### Parametrization Patterns (Modern)
```python
# Basic parametrization
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (3, 4),
])

# With marks (NEW)
@pytest.mark.parametrize("count,expected", [
    (10, True),
    pytest.param(1000, True, marks=pytest.mark.slow),
])

# Indirect fixture parametrization (NEW)
@pytest.mark.parametrize("db", ["mysql", "pg"], indirect=True)
```

### Fixture Scope Optimization (NEW)
```python
@pytest.fixture(scope="session")  # Expensive, reuse
def heavy_resource():
    return ExpensiveSetup()

@pytest.fixture(scope="function")  # Default, isolated
def test_data():
    return {"key": "value"}
```

### Cache Testing Pattern
```python
def test_cache_component(tmp_path):
    cache = CacheManager(cache_dir=tmp_path)
    
    # Test with real components
    shot = Shot("TEST", "seq01", "0010", "/test/path")
    image = ThreadSafeTestImage(100, 100)
    
    result = cache.cache_thumbnail("source.jpg", shot.show, shot.sequence, shot.shot)
    
    assert cache.get_cached_thumbnail(shot.show, shot.sequence, shot.shot)
    assert cache.get_memory_usage() > 0
```

### Integration Test Pattern
```python
def test_shot_workflow():
    # Use real components with test doubles at boundaries
    model = ShotModel()
    cache = CacheManager(tmp_path / "cache")
    
    # Only mock the 'ws' command (system boundary)
    model._process_pool = TestProcessPoolManager()
    model._process_pool.set_outputs("workspace /shows/TEST/seq01/0010")
    
    # Test real behavior
    result = model.refresh_shots()
    shots = model.get_shots()
    
    assert result.success
    assert len(shots) == 1
    assert shots[0].shot == "0010"
```

## ⚠️ CRITICAL RULES

### Qt Threading Rule (FATAL if violated)
**QPixmap = Main Thread ONLY | QImage = Any Thread**

❌ **CRASHES PYTHON**:
```python
def worker():
    pixmap = QPixmap(100, 100)  # Fatal Python error: Aborted
threading.Thread(target=worker).start()
```

✅ **SAFE**:
```python
def worker():
    image = ThreadSafeTestImage(100, 100)  # Thread-safe
threading.Thread(target=worker).start()
```

### Signal Race Conditions
❌ **RACE CONDITION**:
```python
worker.start()  # Signal might emit before setup!
with qtbot.waitSignal(worker.started):
    pass
```

✅ **SAFE**:
```python
with qtbot.waitSignal(worker.started):
    worker.start()  # Signal captured correctly
```

### Qt Container Truthiness
❌ **BUG**:
```python
if self.layout:  # False for empty QVBoxLayout!
    self.layout.addWidget(widget)
```

✅ **CORRECT**:
```python
if self.layout is not None:
    self.layout.addWidget(widget)
```

### Never Mock Class Under Test
❌ **POINTLESS**:
```python
controller = Mock(spec=Controller)
controller.process.return_value = "result"
# Testing the mock, not the controller!
```

✅ **MEANINGFUL**:
```python
controller = Controller(dependencies=TestDouble())
result = controller.process()
assert result == expected
```

## 📊 QUICK REFERENCE

### Lookup Table
| Scenario | Solution |
|----------|----------|
| Testing shot refresh | TestProcessPoolManager |
| Testing thumbnails in threads | ThreadSafeTestImage |
| Testing Qt dialogs | Mock exec() |
| Testing worker threads | QThread with cleanup |
| Testing signal emission | waitSignal BEFORE action |
| Testing conditions | qtbot.waitUntil |
| Testing 'ws' command | Interactive bash subprocess |
| Testing cache components | Real with tmp_path |
| Testing file operations | tmp_path fixture |
| Testing properties | Hypothesis strategies |

### Complete Marker Strategy
```python
markers = [
    "unit: Pure logic tests",
    "integration: Component integration",
    "qt: Qt-specific tests",
    "slow: Tests >1s",
    "performance: Benchmark tests", 
    "stress: Load tests",
    "critical: Must-pass tests",
    "flaky: Known intermittent issues",
]
```

### Essential Fixtures
```python
@pytest.fixture
def qtbot(): ...           # Qt test interface
@pytest.fixture
def tmp_path(): ...         # Temp directory
@pytest.fixture
def make_shot(): ...        # Shot factory (NEW)
@pytest.fixture(scope="session")
def expensive_setup(): ...  # Session-scoped (NEW)
```

### Commands
```bash
# Run tests
python run_tests.py

# Fast tests only
pytest -m "not slow"

# With coverage
pytest --cov=. --cov-report=html

# WSL-optimized testing
python3 quick_test.py              # 2 second validation
python3 run_tests_wsl.py --fast    # 30 seconds
python3 run_tests_wsl.py --all     # Full suite in batches
```

## 📚 APPENDIX

### Test Doubles Library
```python
class TestProcessPoolManager:
    """For 'ws' command testing"""
    def __init__(self):
        self.commands = []  # Track what was called
        self.outputs = []
        self.command_completed = TestSignal()
        self.command_failed = TestSignal()
    
    def set_outputs(self, *outputs):
        self.outputs = list(outputs)
    
    def execute_workspace_command(self, command, **kwargs):
        self.commands.append(command)  # Track for assertions
        output = self.outputs[0] if self.outputs else ""
        self.command_completed.emit(command, output)
        return output
    
    @classmethod
    def get_instance(cls):
        return cls()

class ThreadSafeTestImage:
    """For thread-safe image testing"""
    def __init__(self, width: int = 100, height: int = 100):
        self._image = QImage(width, height, QImage.Format.Format_RGB32)
        self._width = width
        self._height = height
        self._image.fill(QColor(255, 255, 255))
    
    def fill(self, color: QColor = None):
        if color is None:
            color = QColor(255, 255, 255)
        self._image.fill(color)
    
    def isNull(self) -> bool:
        return self._image.isNull()
    
    def sizeInBytes(self) -> int:
        return self._image.sizeInBytes()
    
    def size(self) -> QSize:
        return QSize(self._width, self._height)

class TestSignal:
    """Lightweight signal double"""
    def __init__(self):
        self.emissions = []
        self.callbacks = []
    
    def emit(self, *args):
        self.emissions.append(args)
        for callback in self.callbacks:
            callback(*args)
    
    def connect(self, callback):
        self.callbacks.append(callback)
    
    @property
    def was_emitted(self):
        return len(self.emissions) > 0
```

### Common Issues & Solutions
| Issue | Solution |
|-------|----------|
| "Fatal Python error: Aborted" | Using QPixmap in thread - use QImage |
| Collection warnings | Classes starting with Test need renaming |
| Signal not received | Set up waitSignal before triggering |
| Empty Qt container is falsy | Use `is not None` check |
| 'ws' command fails | Use interactive bash: `["/bin/bash", "-i", "-c", "ws -sg"]` |
| Tests hang on WSL | Use categorized runners and batching |
| Mock everything pattern | Use real components with test doubles at boundaries |

### External Guides
- WSL Testing → WSL-TESTING.md
- Cache Testing → CACHE-TESTING.md  
- Property Testing → PROPERTY-TESTING.md

### Pytest Modern Patterns
- Use `pytest.fail()` not `pytest.raises()` for custom failures
- Use `tmp_path` not deprecated `tmpdir`
- Use `pytest.param` for parametrize marks
- Use factory fixtures for flexible test data
- Use fixture scopes for performance optimization
- Use `qtbot.waitUntil` for condition-based waiting
- Use `check_params_cb` for signal parameter verification

### Anti-Patterns Summary
```python
# ❌ These will cause problems:
threading.Thread(target=lambda: QPixmap(100, 100)).start()  # CRASHES
spy = QSignalSpy(mock.signal)                               # TypeError  
if self.layout:                                             # Falsy when empty
worker.start(); with qtbot.waitSignal(worker.signal): pass # Race condition
controller = Mock(spec=Controller)                          # Testing mock
mock.assert_called_once()                                   # Testing implementation

# ✅ Use these instead:
ThreadSafeTestImage(100, 100)                              # Thread-safe
QSignalSpy(real_widget.real_signal)                        # Real signals only
if self.layout is not None:                                # Explicit check
with qtbot.waitSignal(signal): worker.start()              # Signal first
Controller(process_pool=TestProcessPoolManager())          # Real with test doubles
assert result.success                                       # Test behavior
```

### Testing Checklist
- [ ] Use real components where possible
- [ ] Mock only external dependencies
- [ ] Use `qtbot.addWidget()` for all widgets
- [ ] Check `is not None` for Qt containers
- [ ] Use ThreadSafeTestImage instead of QPixmap in worker threads
- [ ] Set up qtbot.waitSignal() BEFORE starting operations
- [ ] Use TestProcessPoolManager for 'ws' command testing
- [ ] Categorize tests as fast/slow/critical for WSL
- [ ] Use factory fixtures for flexible test data
- [ ] Test behavior, not implementation

---

*This guide provides complete testing patterns for ShotBot. Use the decision tree and lookup table to quickly find the right approach for your testing scenario.*

**Key Metrics After Refactor**:
- Guide length: 457 lines (vs 1288) - 65% reduction!
- Zero redundancy: Each concept appears once
- Quick Start section: 50 lines of copy-paste examples
- Modern patterns: Factory fixtures, pytest.param, qtbot.waitUntil
- LLM-optimized: Clear hierarchy and decision trees

*Last Updated: 2025-01-11 | Refactored for LLM optimization*