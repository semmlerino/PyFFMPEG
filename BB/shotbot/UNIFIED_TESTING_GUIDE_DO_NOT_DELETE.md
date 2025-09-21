# Unified Testing Guide for ShotBot
*Optimized for LLM usage - Single source of truth*

## 🚀 QUICK START

### What Are You Testing? (Decision Tree)
```
IF testing Qt widget → See "Qt Widget Pattern"
ELIF testing worker thread → See "Worker Thread Pattern"
ELIF testing 'ws' command → See "TestProcessPoolManager Pattern"
ELIF testing cache → See "Cache Testing Pattern"
ELIF testing signals → See "Signal Testing Pattern"
ELIF testing async/conditions → See "Modern pytest-qt Features"
ELIF testing models → See "Model Testing"
ELIF testing custom QApplication → See "Custom QApplication Testing"
ELIF testing Qt logging → See "Qt Logging Integration"
ELIF testing dialogs → See "Dialog Testing"
ELIF need CI/headless → See "CI/CD & Headless Testing"
ELSE → Check Quick Lookup Table
```

### Waiting Method Decision Tree
```
Signal emission → qtbot.waitSignal()
Condition met → qtbot.waitUntil()
Callback execution → qtbot.waitCallback()
Fixed delay → qtbot.wait()
No signal expected → qtbot.assertNotEmitted()
Widget visible → qtbot.waitExposed()
Multiple signals → qtbot.waitSignals()
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

### Modern Qt Testing Patterns
```python
# Signal testing with parameter validation
with qtbot.waitSignal(signal, check_params_cb=lambda v: v > 100):
    trigger_action()

# Wait for condition instead of signal
qtbot.waitUntil(lambda: widget.isReady(), timeout=2000)

# Capture Qt exceptions
with qtbot.captureExceptions() as exceptions:
    widget.trigger_error()

# Wait for callbacks (QWebEngine)
with qtbot.waitCallback() as cb:
    page.runJavaScript("1 + 1", cb)
    cb.assert_called_with(2)

# Assert signal NOT emitted
with qtbot.assertNotEmitted(signal, wait=100):
    other_action()

# Multiple signals with order
with qtbot.waitSignals([sig1, sig2], order='strict'):
    trigger_sequential()
```

### TestProcessPoolManager Pattern ('ws' Command)
```python
# CRITICAL: 'ws' is a shell function, not executable!
def test_shot_refresh():
    model = ShotModel()
    
    test_pool = TestProcessPoolManager()
    test_pool.set_outputs(
        "workspace /shows/TEST/shots/seq01/seq01_0010",  # Correct VFX format
        "workspace /shows/TEST/shots/seq01/seq01_0020"   # Must include shots/ and seq prefix
    )
    model._process_pool = test_pool
    
    result = model.refresh_shots()
    assert result.success
    assert model.shots[0].shot == "0010"  # Parser extracts shot number
```

### Parametrization & Fixtures
```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    pytest.param(1000, True, marks=pytest.mark.slow),
])
@pytest.mark.parametrize("db", ["mysql", "pg"], indirect=True)
def test_with_params(input, expected, db): ...

@pytest.fixture(scope="session")  # Reuse expensive resources
def heavy_resource(): return ExpensiveSetup()
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
    model._process_pool.set_outputs("workspace /shows/TEST/shots/seq01/seq01_0010")

    # Test real behavior
    result = model.refresh_shots()
    shots = model.get_shots()

    assert result.success
    assert len(shots) == 1
    assert shots[0].shot == "0010"
```

### CI/CD & Headless Testing
```python
# Headless configuration
@pytest.fixture(scope="session")
def qapp_args():
    if os.environ.get("CI"):
        return ["-platform", "offscreen"]
    return []

# Essential environment variables
export DISPLAY=:99
export QT_QPA_PLATFORM=offscreen

# Install pytest-xvfb for automatic headless testing
pip install pytest-xvfb
pytest --runxvfb  # Runs with virtual display
```

### AsyncShotLoader Pattern
```python
def test_async_loader(qtbot):
    # CRITICAL: Must provide parse_function from BaseShotModel
    from base_shot_model import BaseShotModel

    base_model = BaseShotModel()
    test_pool = TestProcessPoolDouble()
    test_pool.set_outputs("workspace /shows/TEST/shots/seq01/seq01_0010")

    loader = AsyncShotLoader(
        test_pool,
        parse_function=base_model._parse_ws_output  # Required!
    )

    spy = QSignalSpy(loader.shots_loaded)
    loader.start()
    loader.wait(5000)

    assert spy.count() == 1
    shots = spy.at(0)[0]
    assert shots[0].shot == "0010"
```

### Model Testing & Custom QApplication
```python
# Test QAbstractItemModel implementation
def test_model(qtmodeltester):
    model = MyItemModel()
    qtmodeltester.check(model)  # C++ implementation by default
    qtmodeltester.check(model, force_py=True)  # Force Python impl

# Custom QApplication
@pytest.fixture(scope="session")
def qapp_cls():
    return MyCustomApplication

# Mock QApplication.exit()
def test_exit(qtbot, monkeypatch):
    monkeypatch.setattr(QApplication, "exit", lambda: None)
```


### Qt Logging & Dialogs
```python
# Capture Qt messages
def test_logging(qtlog):
    widget.trigger_warning()
    assert any("warning" in r.message for r in qtlog.records)

# Disable logging: with qtlog.disabled() or @pytest.mark.no_qt_log

# Mock dialogs
def test_dialog(qtbot, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                       lambda *args: ("/path/file.txt", "*.txt"))
    monkeypatch.setattr(QMessageBox, "question",
                       lambda *args: QMessageBox.Yes)
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

### QSignalSpy Indexing
❌ **SEGFAULT**:
```python
# QSignalSpy doesn't support negative indexing!
signal_data = spy.at(-1)  # Segmentation fault in Qt
```

✅ **SAFE**:
```python
# Use count() - 1 for last signal
signal_data = spy.at(spy.count() - 1)
```

### QObject Thread Affinity (CRITICAL)
**Rule: QObjects can ONLY be accessed from the thread they belong to**

❌ **FATAL VIOLATION**:
```python
# ProcessPoolManager is a QObject created in main thread
manager = ProcessPoolManager()  # Created in main thread

def worker():
    # CRASH: Accessing QObject from different thread!
    result = manager.find_files_python(".", "*.txt")

threading.Thread(target=worker).start()  # Will crash/hang
```

✅ **PROPER SOLUTION**:
```python
# Use queue-based communication with main thread
work_queue = queue.Queue()
result_queue = queue.Queue()

def worker():
    work_queue.put((".", "*.txt"))  # Send work request
    result = result_queue.get()     # Receive result

def process_work():
    while not work_queue.empty():
        args = work_queue.get_nowait()
        result = manager.find_files_python(*args)  # Safe in main thread
        result_queue.put(result)

# Use QTimer to process work in main thread
timer = QTimer()
timer.timeout.connect(process_work)
timer.start(10)
```

### Widget Creation Thread Safety
**Rule: Qt widgets must be created in the main thread only**

❌ **FATAL CRASH**:
```python
# Widget creation in background thread - causes Fatal Python error: Aborted
def worker():
    panel = ShotInfoPanel()  # CRASH: Widget created in wrong thread

threading.Thread(target=worker).start()
```

✅ **THREAD-SAFE PATTERN**:
```python
class ShotInfoPanel(QWidget):
    def __init__(self, cache_manager=None):
        # Validate main thread before widget creation
        from PySide6.QtCore import QThread, QCoreApplication

        app_instance = QCoreApplication.instance()
        if app_instance is None:
            raise RuntimeError("No QApplication instance found")

        current_thread = QThread.currentThread()
        main_thread = app_instance.thread()
        if current_thread != main_thread:
            raise RuntimeError(f"Widget must be created in main thread")

        super().__init__()
```

### Qt Object Lifecycle Safety
**Rule: Always guard against accessing deleted Qt objects**

❌ **RUNTIME ERROR**:
```python
# Timer callback accessing deleted Qt object
QTimer.singleShot(timeout, lambda: status_bar.setStyleSheet(style))
# RuntimeError: Internal C++ object (QStatusBar) already deleted
```

✅ **DEFENSIVE PATTERN**:
```python
def restore_style():
    try:
        if status_bar and not status_bar.isHidden():
            status_bar.setStyleSheet(original_style)
    except RuntimeError:
        # Qt object was deleted, ignore gracefully
        pass

QTimer.singleShot(timeout, restore_style)
```

### Integration Test Parallel Execution
**Rule: Qt tests MUST use xdist_group marker for parallel safety**

❌ **SEGFAULT in parallel**:
```python
pytestmark = [pytest.mark.integration, pytest.mark.qt]  # MISSING xdist_group
```

✅ **PARALLEL SAFE**:
```python
pytestmark = [
    pytest.mark.integration,
    pytest.mark.qt,
    pytest.mark.xdist_group("qt_state")  # CRITICAL: Same worker for all Qt tests
]
```

### Test Popup Prevention
**Automated popup prevention implemented in conftest.py at module import time**

❌ **WRONG APPROACH**:
```python
# Don't patch show() in individual tests
def test_widget(qtbot, monkeypatch):
    monkeypatch.setattr(QWidget, "show", lambda self: None)  # Too late!
```

✅ **CORRECT APPROACH**:
```python
# In conftest.py - patches applied before ANY imports
os.environ["QT_QPA_PLATFORM"] = "offscreen"
QWidget.show = _mock_widget_show  # Global patching at import time
QWidget.isVisible = _mock_widget_isVisible  # Virtual visibility tracking
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
| Testing Qt dialogs | Mock exec() with monkeypatch |
| Testing worker threads | QThread with cleanup |
| Testing signal emission | waitSignal BEFORE action |
| Testing conditions | qtbot.waitUntil(lambda: condition) |
| Testing async callbacks | qtbot.waitCallback() |
| Testing signal parameters | check_params_cb in waitSignal |
| Testing Qt exceptions | qtbot.captureExceptions() |
| Testing models | qtmodeltester fixture |
| Testing custom QApplication | qapp_cls fixture |
| Testing Qt logging | qtlog fixture |
| Testing headless CI | pytest-xvfb or QPA offscreen |
| Testing 'ws' command | Interactive bash subprocess |
| Testing cache components | Real with tmp_path |
| Testing file operations | tmp_path fixture |
| Testing multiple signals | waitSignals with order='strict' |
| Testing modal dialogs | monkeypatch dialog.exec |
| Testing cross-thread signals | Qt.QueuedConnection |
| Testing without signal emission | qtbot.assertNotEmitted |

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
    "no_qt_log: Disable Qt logging capture",
    "qt_log: Custom Qt logging configuration",
    "headless: Tests requiring headless environment",
    "gui_deterministic: Tests requiring deterministic GUI",
    "model: QAbstractItemModel tests",
    "thread: Threading-related tests",
]
```

### Essential Fixtures
```python
@pytest.fixture
def qtbot(): ...                    # Qt test interface with wait/signal methods
@pytest.fixture
def tmp_path(): ...                 # Temp directory (Path object)
@pytest.fixture
def make_shot(): ...                # Shot factory for flexible test data
@pytest.fixture
def qtlog(): ...                    # Qt message capture and verification
@pytest.fixture
def qtmodeltester(): ...            # QAbstractItemModel testing
@pytest.fixture
def qapp(): ...                     # QApplication instance (session scope)
@pytest.fixture
def qapp_cls(): ...                 # Override QApplication class
@pytest.fixture
def qapp_args(): ...                # Arguments for QApplication
@pytest.fixture(scope="session")
def expensive_setup(): ...          # Session-scoped resource
@pytest.fixture
def monkeypatch(): ...              # Mock/patch functionality
```

### Commands
```bash
# Run tests
python run_tests.py

# Fast tests only
pytest -m "not slow"

# Qt-specific tests
pytest -m qt

# Model tests only
pytest -m model

# Headless CI testing
DISPLAY=:99 QT_QPA_PLATFORM=offscreen pytest

# With coverage
pytest --cov=. --cov-report=html

# With Qt logging enabled
pytest --qt-log-level=DEBUG

# WSL-optimized testing
python3 quick_test.py              # 2 second validation
python3 run_tests_wsl.py --fast    # 30 seconds
python3 run_tests_wsl.py --all     # Full suite in batches

# Using pytest-xvfb (auto headless)
pytest --runxvfb
```

### Test Isolation
```python
# Isolate QSettings
@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch):
    test_settings = {}
    monkeypatch.setattr(QSettings, "value", lambda k, d=None: test_settings.get(k, d))
    monkeypatch.setattr(QSettings, "setValue", lambda k, v: test_settings.update({k: v}))

# Clean widget state
@pytest.fixture
def clean_widgets():
    initial = QApplication.topLevelWidgets()
    yield
    for w in QApplication.topLevelWidgets():
        if w not in initial: w.deleteLater()
```


## 📚 APPENDIX

### Test Doubles Reference
```python
class TestProcessPoolManager:  # Mock 'ws' command
    __test__ = False  # Prevent pytest collection
    def set_outputs(self, *outputs): ...
    def execute_workspace_command(self, command, **kwargs): ...

class ThreadSafeTestImage:  # Thread-safe QImage replacement
    def __init__(self, width=100, height=100): ...
    def size(self) -> QSize: ...

class TestSignal:  # Lightweight Qt signal mock
    def emit(self, *args): ...
    def connect(self, callback): ...
```


### Critical Anti-Patterns
| ❌ Problem | ✅ Solution |
|-----------|------------|
| `QPixmap` in thread | Use `ThreadSafeTestImage` or `QImage` |
| `if self.layout:` (falsy when empty) | Use `if self.layout is not None:` |
| `spy.at(-1)` (segfault) | Use `spy.at(spy.count() - 1)` |
| `Mock(spec=Controller)` | Use real with test doubles |
| `dialog.exec()` blocks | `monkeypatch.setattr(dialog, "exec", lambda: result)` |
| Signal race conditions | `with qtbot.waitSignal(sig): worker.start()` |
| No widget cleanup | Always use `qtbot.addWidget(widget)` |
| `QApplication.exit()` | Mock with `monkeypatch` |
| Cross-thread signals | Use `Qt.QueuedConnection` |
| `class TestHelper:` | Add `__test__ = False` |
| `qtbot.wait(0)` | Use `qtbot.wait(100)` or `waitUntil()` |
| Widget creation in threads | Use main thread validation |
| Qt object lifecycle after deletion | Use defensive try/except blocks |

---
Testing Checklist
[ ] Use real components where possible
[ ] Mock only external dependencies
[ ] Use `qtbot.addWidget()` for all widgets
[ ] Check `is not None` for Qt containers
[ ] Use ThreadSafeTestImage instead of QPixmap in worker threads
[ ] Set up qtbot.waitSignal() BEFORE starting operations
[ ] Use TestProcessPoolManager for 'ws' command testing
[ ] Categorize tests as fast/slow/critical for WSL
[ ] Use factory fixtures for flexible test data
[ ] Test behavior, not implementation
[ ] Add `__test__ = False` to all test double classes
[ ] Use `spy.at(spy.count() - 1)` not `spy.at(-1)` for QSignalSpy
[ ] Provide parse_function to AsyncShotLoader from BaseShotModel
[ ] Import builtins explicitly for `__import__` access
[ ] Use correct VFX path format: `/shows/{show}/shots/{seq}/{seq}_{shot}`
[ ] Validate main thread before creating Qt widgets
[ ] Use defensive exception handling for Qt object access
[ ] Guard against "Internal C++ object already deleted" errors