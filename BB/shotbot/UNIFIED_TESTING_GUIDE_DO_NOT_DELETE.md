# Unified Testing Guide - DO NOT DELETE
*The single source of truth for testing ShotBot with Qt and pytest*

## Table of Contents
1. [Core Principles](#core-principles)
2. [Test Organization & Decision Trees](#test-organization--decision-trees)
3. [When to Mock](#when-to-mock)
4. [Signal Testing](#signal-testing)
5. [Property-Based Testing](#property-based-testing)
6. [Essential Test Doubles](#essential-test-doubles)
7. [Test Templates](#test-templates)
8. [Cache Architecture Testing](#cache-architecture-testing)
9. [Qt-Specific Patterns](#qt-specific-patterns)
10. [Qt Threading Safety](#qt-threading-safety)
11. [WSL Testing Strategies](#wsl-testing-strategies)
12. [Quick Lookup Table](#quick-lookup-table)
13. [Critical Pitfalls](#critical-pitfalls)
14. [Quick Reference](#quick-reference)

---

## Core Principles

### 1. Test Behavior, Not Implementation
```python
# ❌ BAD - Testing implementation
with patch.object(model, '_parse_output') as mock_parse:
    model.refresh()
    mock_parse.assert_called_once()  # Who cares?

# ✅ GOOD - Testing behavior
model.refresh()
assert len(model.get_shots()) == 3  # Actual outcome
```

### 2. Real Components Over Mocks
```python
# ❌ BAD - Mocking everything
controller = Mock(spec=Controller)
controller.process.return_value = "result"

# ✅ GOOD - Real component with test dependencies
controller = Controller(
    process_pool=TestProcessPool(),  # Test double
    cache=CacheManager(tmp_path)     # Real with temp storage
)
```

### 3. Mock Only at System Boundaries
- External APIs, Network calls
- Subprocess calls to external systems
- File I/O (only when testing logic, not I/O itself)
- System time

---

## Test Organization & Decision Trees

### Test Placement Algorithm
```
IF uses qtbot OR inherits QWidget/QObject:
    → tests/qt/
ELIF tests subprocess OR ws command:
    → tests/integration/
ELIF tests multiple cache components:
    → tests/integration/
ELIF pure logic/parsing/utilities:
    → tests/unit/
ELIF full application workflow:
    → tests/e2e/
```

### File Naming Convention
```
tests/
├── unit/
│   └── test_<module>__<behavior>.py
├── qt/
│   └── test_<widget>__<interaction>.py
├── integration/
│   └── test_<component1>_<component2>__integration.py
└── e2e/
    └── test_<workflow>__e2e.py
```

### Function Naming Convention
```python
def test_<Class>__<method>__<scenario>():
    """Test <expected behavior> when <condition>."""
    pass

# Examples:
def test_ShotModel__refresh_shots__returns_changes():
def test_CacheManager__cache_thumbnail__thread_safety():
def test_MainWindow__on_refresh__updates_grid():
```

### Mocking Decision Algorithm
```
FOR each dependency:
    IF crosses process boundary (subprocess):
        → Use TestProcessPoolManager or Mock
    ELIF network/external API:
        → Mock with predefined responses
    ELIF filesystem AND testing logic (not I/O):
        → Mock or use tmp_path
    ELIF Qt widget/signal:
        → Use real widget with qtbot
    ELIF internal method:
        → Use real method
    ELIF database:
        → Use in-memory SQLite or test double
```

---

## When to Mock

### Deterministic Mocking Checklist

| Question | Action |
|----------|--------|
| Does it cross process/network/time/OS boundary? | ✅ **Mock/Test Double** |
| Is it a pure value object or data type? | ❌ **Use Real** |
| Would mocking change the public behavior being tested? | ❌ **Don't Mock** |
| Are you verifying call counts to internal methods? | 🚫 **Code Smell - Remove** |
| Is it the 'ws' shell function command? | ✅ **Use TestProcessPoolManager** |
| Is it a Qt signal/slot connection? | ❌ **Use Real with qtbot** |

### Practical Examples by Test Type

| Test Type | Mock | Use Real |
|-----------|------|----------|
| **Unit** | External services, Network, Subprocess, System time | Class under test, Value objects, Internal methods |
| **Integration** | External APIs only | Components being integrated, Signals, Cache, File I/O |
| **E2E** | Nothing (use test environment) | Everything |

### ShotBot-Specific Mocking Rules
```python
# ALWAYS mock the 'ws' command - it's a shell function
def test_shot_workflow():
    model = ShotModel()
    # NOTE: 'ws' is shell function requiring interactive bash
    model._process_pool = TestProcessPoolManager()
    model._process_pool.set_outputs("workspace /shows/test/seq/shot")
    
    result = model.refresh_shots()
    assert result.success
```

---

## Signal Testing

### Signal Testing Decision Matrix

| Scenario | Tool | When to Use |
|----------|------|-------------|
| Real Qt widget signals | `QSignalSpy` | Testing actual Qt components |
| Test double signals | `TestSignal` | Non-Qt or mocked components |
| Async Qt operations | `qtbot.waitSignal()` | Waiting for real Qt signals |
| Mock object callbacks | `.assert_called()` | Pure Python mocks |
| Verify NO signal emission | `qtbot.assertNotEmitted` | Ensuring silence |

### QSignalSpy for Real Qt Signals
```python
def test_real_qt_signal(qtbot):
    widget = RealQtWidget()  # Real Qt object
    qtbot.addWidget(widget)
    
    # QSignalSpy ONLY works with real Qt signals
    spy = QSignalSpy(widget.data_changed)
    
    widget.update_data("test")
    
    assert len(spy) == 1
    assert spy[0][0] == "test"
```

### TestSignal for Test Doubles
```python
class TestSignal:
    """Lightweight signal test double"""
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

# Usage
def test_with_test_double():
    manager = TestProcessPoolManager()  # Has TestSignal
    manager.command_completed.connect(on_complete)
    
    manager.execute("test")
    
    assert manager.command_completed.was_emitted
```

### Waiting for Async Signals
```python
def test_async_operation(qtbot):
    processor = DataProcessor()  # Real Qt object
    
    # ✅ CORRECT - Set up signal waiter BEFORE starting
    with qtbot.waitSignal(processor.finished, timeout=1000) as blocker:
        processor.start()
    
    assert blocker.signal_triggered
    assert blocker.args[0] == "success"
```

### ⚠️ Critical: Signal Race Conditions
```python
# ❌ RACE CONDITION - Signal may be emitted before waitSignal() setup
def test_race_condition():
    worker.start()  # Signal might emit immediately
    with qtbot.waitSignal(worker.worker_started):  # Too late!
        pass

# ✅ THREAD-SAFE - Signal waiter ready before emission
def test_no_race():
    with qtbot.waitSignal(worker.worker_started):
        worker.start()  # Signal captured correctly
```

---

## Property-Based Testing

### When to Use Property-Based Testing
- Path operations and validation
- Cache key generation
- Parsing functions
- Data transformations
- Invariants that must hold for all inputs

### ShotBot Property Test Templates

#### Path Operations Template
```python
from hypothesis import given, strategies as st

# Shot path invariant testing
@given(st.from_regex(r"/shows/[a-z0-9_]+/[a-z0-9_]+/\d{4}", fullmatch=True))
def test_shot_path_roundtrip(path):
    """Any valid shot path should parse and reconstruct identically."""
    shot = Shot.from_path(path)
    assert shot.to_path() == path
    assert shot.show and shot.sequence and shot.shot

# Cache key invariants
@given(
    show=st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_characters="/")),
    seq=st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_characters="/")),
    shot=st.from_regex(r"\d{4}")
)
def test_cache_key_uniqueness(show, seq, shot):
    """Cache keys must be unique and reversible."""
    key1 = CacheManager.generate_key(show, seq, shot)
    key2 = CacheManager.generate_key(show, seq, shot)
    assert key1 == key2  # Deterministic
    assert "/" not in key1  # Safe for filesystem
```

#### Workspace Command Parsing Template
```python
@given(st.lists(
    st.tuples(
        st.from_regex(r"[A-Z]{2}", fullmatch=True),  # Show code
        st.from_regex(r"seq\d{3}", fullmatch=True),  # Sequence
        st.from_regex(r"\d{4}", fullmatch=True)      # Shot number
    ),
    min_size=0,
    max_size=100
))
def test_workspace_parsing_consistency(shot_data):
    """Workspace output parsing should handle any valid format."""
    # Generate mock workspace output
    ws_output = "\n".join(f"workspace /shows/{s}/{sq}/{sh}" 
                          for s, sq, sh in shot_data)
    
    shots = ShotModel._parse_workspace_output(ws_output)
    assert len(shots) == len(shot_data)
    for shot, (show, seq, shot_num) in zip(shots, shot_data):
        assert shot.show == show
        assert shot.sequence == seq
        assert shot.shot == shot_num
```

---

## Essential Test Doubles

### TestProcessPoolManager
```python
class TestProcessPoolManager:
    """Replace subprocess calls with predictable behavior.
    
    CRITICAL: Use this for 'ws' command testing - it's a shell function!
    """
    def __init__(self):
        self.commands = []
        self.outputs = ["workspace /test/path"]
        self.command_completed = TestSignal()
        self.command_failed = TestSignal()
    
    def execute_workspace_command(self, command, **kwargs):
        """Simulate 'ws -sg' command execution.
        
        NOTE: Real 'ws' requires ["/bin/bash", "-i", "-c", "ws -sg"]
        This test double avoids that complexity.
        """
        self.commands.append(command)
        output = self.outputs[0] if self.outputs else ""
        self.command_completed.emit(command, output)
        return output
    
    def set_outputs(self, *outputs):
        """Preset outputs for testing different scenarios."""
        self.outputs = list(outputs)
    
    @classmethod
    def get_instance(cls):
        return cls()
```

### MockMainWindow (Real Qt Signals, Mock Behavior)
```python
class MockMainWindow(QObject):
    """Real Qt object with signals, mocked behavior"""
    
    # Real Qt signals
    extract_requested = pyqtSignal()
    file_opened = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        # Mock attributes
        self.status_bar = Mock()
        self.current_file = None
    
    def get_extraction_params(self):
        return {"vram_path": "/test/path"}  # Test data
```

### ThreadSafeTestImage (CRITICAL for Qt Threading)
```python
class ThreadSafeTestImage:
    """Thread-safe test double for QPixmap using QImage internally.
    
    ⚠️ CRITICAL: QPixmap is NOT thread-safe and WILL crash Python if used
    in worker threads. This class provides a QPixmap-like interface while
    using QImage internally for thread safety.
    """
    
    def __init__(self, width: int = 100, height: int = 100):
        # Use QImage which is thread-safe, unlike QPixmap
        self._image = QImage(width, height, QImage.Format.Format_RGB32)
        self._width = width
        self._height = height
        self._image.fill(QColor(255, 255, 255))
        
    def fill(self, color: QColor = None) -> None:
        if color is None:
            color = QColor(255, 255, 255)
        self._image.fill(color)
        
    def isNull(self) -> bool:
        return self._image.isNull()
        
    def sizeInBytes(self) -> int:
        return self._image.sizeInBytes()
        
    def size(self) -> QSize:
        return QSize(self._width, self._height)
```

### Factory Fixtures
```python
@pytest.fixture
def make_shot():
    """Factory for Shot objects"""
    def _make_shot(show="test", seq="seq1", shot="0010"):
        return Shot(show, seq, shot, f"/shows/{show}/{seq}/{shot}")
    return _make_shot

@pytest.fixture
def real_cache_manager(tmp_path):
    """Real cache with temp storage"""
    return CacheManager(cache_dir=tmp_path / "cache")

@pytest.fixture
def test_process_pool():
    """Pre-configured test process pool"""
    pool = TestProcessPoolManager()
    pool.set_outputs(
        "workspace /shows/TEST/seq01/0010",
        "workspace /shows/TEST/seq01/0020"
    )
    return pool
```

---

## Test Templates

### Qt Widget Test Template
```python
# test_qt_widget_template.py
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

def test_widget_interaction(qtbot: QtBot):
    """Template for testing Qt widget interactions."""
    # 1. Create widget
    widget = MyCustomWidget()
    qtbot.addWidget(widget)  # CRITICAL: Register for cleanup
    
    # 2. Show widget (if needed)
    widget.show()
    qtbot.waitExposed(widget)
    
    # 3. Interact
    qtbot.mouseClick(widget.button, Qt.LeftButton)
    qtbot.keyClick(widget.input_field, Qt.Key_Return)
    qtbot.keyClicks(widget.text_edit, "test input")
    
    # 4. Wait for async operations
    with qtbot.waitSignal(widget.data_changed, timeout=1000):
        widget.trigger_update()
    
    # 5. Assert
    assert widget.label.text() == "Expected"
    assert widget.model.rowCount() == 5
```

### Signal Test Template
```python
# test_signal_template.py
import pytest
from PySide6.QtCore import QObject, Signal
from pytestqt.qtbot import QtBot

def test_signal_emission(qtbot: QtBot):
    """Template for testing Qt signal emission."""
    # 1. Create object with signals
    model = DataModel()
    
    # 2. Set up signal spy BEFORE triggering
    with qtbot.waitSignal(model.data_updated, timeout=1000) as blocker:
        model.update_data("new value")
    
    # 3. Verify signal was emitted with correct args
    assert blocker.signal_triggered
    assert blocker.args[0] == "new value"
    
    # Alternative: QSignalSpy for multiple emissions
    from pytestqt.qt_compat import qt_api
    spy = qt_api.QtTest.QSignalSpy(model.data_updated)
    
    model.update_data("first")
    model.update_data("second")
    
    assert len(spy) == 2
    assert spy[0][0] == "first"
    assert spy[1][0] == "second"
```

### Worker Thread Test Template
```python
# test_worker_thread_template.py
import pytest
from PySide6.QtCore import QThread
from pytestqt.qtbot import QtBot

def test_worker_thread(qtbot: QtBot):
    """Template for testing worker threads safely."""
    # 1. Create worker (NO QPixmap operations!)
    worker = ImageProcessorWorker()
    
    # 2. Use ThreadSafeTestImage for any image operations
    test_image = ThreadSafeTestImage(200, 200)
    worker.set_image(test_image)  # Safe in any thread
    
    # 3. Connect signals before starting
    results = []
    worker.result_ready.connect(lambda r: results.append(r))
    
    # 4. Start worker
    worker.start()
    
    # 5. Wait for completion
    qtbot.waitUntil(lambda: not worker.isRunning(), timeout=5000)
    
    # 6. Verify results
    assert len(results) == 1
    assert results[0].success
    
    # 7. Cleanup
    if worker.isRunning():
        worker.quit()
        worker.wait(1000)
```

### Cache Component Test Template
```python
# test_cache_component_template.py
import pytest
from pathlib import Path

def test_cache_component_isolation(tmp_path: Path):
    """Template for testing individual cache components."""
    # 1. Create component with test storage
    storage = StorageBackend(tmp_path / "cache")
    
    # 2. Test component in isolation
    data = {"key": "value", "timestamp": 123456}
    storage.write_json("test_key", data)
    
    # 3. Verify behavior
    loaded = storage.read_json("test_key")
    assert loaded == data
    
    # 4. Test error conditions
    assert storage.read_json("nonexistent") is None

def test_cache_integration(tmp_path: Path):
    """Template for testing cache component integration."""
    # 1. Create multiple components
    storage = StorageBackend(tmp_path / "cache")
    memory = MemoryManager(max_size_mb=10)
    processor = ThumbnailProcessor(storage, memory)
    
    # 2. Test integration
    # NOTE: Use ThreadSafeTestImage for thread safety
    image = ThreadSafeTestImage(100, 100)
    result = processor.process_thumbnail("test_shot", image)
    
    # 3. Verify cross-component behavior
    assert storage.exists("thumbnails/test_shot")
    assert memory.get_usage() > 0
```

### Shot Model Test Template
```python
# test_shot_model_template.py
import pytest

def test_shot_model_refresh():
    """Template for testing shot model with ws command."""
    # 1. Create model
    model = ShotModel()
    
    # 2. Replace process pool with test double
    # CRITICAL: 'ws' is a shell function, not executable
    test_pool = TestProcessPoolManager()
    test_pool.set_outputs(
        "workspace /shows/TEST/seq01/0010\n"
        "workspace /shows/TEST/seq01/0020"
    )
    model._process_pool = test_pool
    
    # 3. Test refresh
    result = model.refresh_shots()
    
    # 4. Verify behavior
    assert result.success
    assert result.has_changes
    assert len(model.get_shots()) == 2
    assert model.get_shots()[0].shot == "0010"
```

---

## Cache Architecture Testing

### Component Testing Matrix

| Component | Test in Isolation | Integration Points | Key Test Scenarios |
|-----------|------------------|-------------------|-------------------|
| StorageBackend | ✅ Yes | None | Atomic writes, fallback handling, thread safety |
| FailureTracker | ✅ Yes | None | Exponential backoff, cleanup, timestamp tracking |
| MemoryManager | ✅ Yes | None | LRU eviction, size tracking, limit enforcement |
| ThumbnailProcessor | ⚠️ Partial | Storage, Memory | Format support, thread safety (ThreadSafeTestImage) |
| ShotCache | ✅ Yes | Storage | TTL expiration, refresh, serialization |
| ThreeDECache | ✅ Yes | Storage | Metadata, deduplication, TTL |
| CacheValidator | ❌ No | All components | Consistency, repair, statistics |
| ThumbnailLoader | ❌ No | Processor, Failure | Async loading, signal emission |

### Component Isolation Testing
```python
def test_storage_backend_isolation(tmp_path):
    """Test StorageBackend without other components."""
    storage = StorageBackend(tmp_path)
    
    # Test atomic write
    storage.write_json("key", {"data": "value"})
    assert storage.read_json("key") == {"data": "value"}
    
    # Test thread safety
    import threading
    results = []
    
    def write_data(i):
        storage.write_json(f"key_{i}", {"id": i})
        results.append(i)
    
    threads = [threading.Thread(target=write_data, args=(i,)) 
               for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(results) == 10
```

### Component Integration Testing
```python
def test_thumbnail_pipeline_integration(tmp_path):
    """Test full thumbnail processing pipeline."""
    # Create integrated components
    storage = StorageBackend(tmp_path)
    memory = MemoryManager(max_size_mb=10)
    failure = FailureTracker(storage)
    processor = ThumbnailProcessor(storage, memory, failure)
    
    # Test successful processing
    image = ThreadSafeTestImage(100, 100)
    result = processor.process("shot_001", image)
    
    assert result.success
    assert memory.get_usage() > 0
    assert not failure.should_retry("shot_001")
    
    # Test failure handling
    processor.process("bad_shot", None)  # Will fail
    assert failure.should_retry("bad_shot") is False  # In backoff
```

### Cache Manager Facade Testing
```python
def test_cache_manager_facade(tmp_path):
    """Test the main CacheManager facade."""
    cache = CacheManager(cache_dir=tmp_path)
    
    # The facade should coordinate all components
    shot = Shot("TEST", "seq01", "0010", "/test/path")
    
    # Test thumbnail caching (involves multiple components)
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake_image_data")
    
    pixmap = cache.cache_thumbnail(
        source_path=str(image_path),
        show=shot.show,
        sequence=shot.sequence,
        shot=shot.shot
    )
    
    # Verify coordination
    assert cache.get_memory_usage() > 0
    assert cache.get_cached_thumbnail(shot.show, shot.sequence, shot.shot)
```

---

## Qt-Specific Patterns

### qtbot Essential Methods
```python
# Widget management
qtbot.addWidget(widget)           # Register for cleanup
qtbot.waitExposed(widget)         # Wait for show
qtbot.waitActive(widget)          # Wait for focus

# Signal testing
qtbot.waitSignal(signal, timeout=1000)
qtbot.assertNotEmitted(signal)
with qtbot.waitSignal(signal):
    do_something()

# Event simulation
qtbot.mouseClick(widget, Qt.LeftButton)
qtbot.keyClick(widget, Qt.Key_Return)
qtbot.keyClicks(widget, "text")

# Timing
qtbot.wait(100)                   # Process events
qtbot.waitUntil(lambda: condition, timeout=1000)
```

### Testing Modal Dialogs
```python
def test_dialog(qtbot, monkeypatch):
    # Mock exec() to prevent blocking
    monkeypatch.setattr(QDialog, "exec", 
                       lambda self: QDialog.DialogCode.Accepted)
    
    dialog = MyDialog()
    qtbot.addWidget(dialog)
    
    dialog.input_field.setText("test")
    result = dialog.exec()
    
    assert result == QDialog.DialogCode.Accepted
    assert dialog.get_value() == "test"
```

### Worker Thread Testing
```python
def test_worker(qtbot):
    worker = DataWorker()
    spy = QSignalSpy(worker.finished)
    
    worker.start()
    
    # Wait for completion
    qtbot.waitUntil(lambda: not worker.isRunning(), timeout=5000)
    
    assert len(spy) == 1
    assert worker.result is not None
    
    # Cleanup
    if worker.isRunning():
        worker.quit()
        worker.wait(1000)
```

---

## Qt Threading Safety

### The Fundamental Rule: QPixmap vs QImage

Qt has **strict threading rules** that cause crashes if violated in tests:

| Class | Thread Safety | Usage |
|-------|---------------|--------|
| **QPixmap** | ❌ **Main GUI thread ONLY** | Display, UI rendering |
| **QImage** | ✅ **Any thread** | Image processing, workers |

### ⚠️ Threading Violation Crash Symptoms
```python
# ❌ FATAL ERROR - Creates QPixmap in worker thread
def test_worker_processing():
    def worker():
        pixmap = QPixmap(100, 100)  # CRASH: "Fatal Python error: Aborted"
    
    thread = threading.Thread(target=worker)
    thread.start()  # Will crash Python
```

### The Canonical Qt Threading Pattern

Qt's official threading pattern for image operations:

```
Worker Thread (Background):     Main Thread (GUI):
┌─────────────────────┐        ┌──────────────────┐
│ 1. Process with     │─signal→│ 4. Convert to    │
│    QImage           │        │    QPixmap       │
│                     │        │                  │
│ 2. Emit signal      │        │ 5. Display in UI │
│    with QImage      │        │                  │
│                     │        │                  │
│ 3. Worker finishes  │        │ 6. UI updates    │
└─────────────────────┘        └──────────────────┘
```

### Usage in Threading Tests

Replace QPixmap with ThreadSafeTestImage in tests that involve worker threads:

```python
def test_concurrent_image_processing():
    """Test concurrent image operations without Qt threading violations."""
    results = []
    errors = []
    
    def process_image(thread_id: int):
        """Process image in worker thread."""
        try:
            # ✅ SAFE - Use ThreadSafeTestImage instead of QPixmap
            image = ThreadSafeTestImage(100, 100)
            image.fill(QColor(255, 0, 0))  # Thread-safe operation
            
            # Test the actual threading behavior
            result = cache_manager.process_in_thread(image)
            results.append((thread_id, result is not None))
                
        except Exception as e:
            errors.append((thread_id, str(e)))
    
    # Start multiple worker threads
    threads = []
    for i in range(5):
        t = threading.Thread(target=process_image, args=(i,))
        threads.append(t)
        t.start()
        
    # Wait for completion
    for t in threads:
        t.join(timeout=5.0)
        
    # Verify no threading violations occurred
    assert len(errors) == 0, f"Threading errors: {errors}"
    assert len(results) == 5
```

### Threading Test Checklist

- [ ] ✅ Use `ThreadSafeTestImage` instead of `QPixmap` in worker threads
- [ ] ✅ Patch `QImage` operations, not `QPixmap` operations  
- [ ] ✅ Test both single-threaded and multi-threaded scenarios
- [ ] ✅ Verify no "Fatal Python error: Aborted" crashes
- [ ] ✅ Check that worker threads can create/manipulate images safely
- [ ] ✅ Ensure main thread can display results from worker threads

---

## WSL Testing Strategies

### WSL Performance Characteristics
- Filesystem operations on `/mnt/c` are 10-100x slower than native Linux
- Test collection alone can take 60+ seconds
- Solution: Categorize tests and use optimized runners

### Test Categorization for WSL

```python
# Mark tests with speed categories
import pytest

@pytest.mark.fast  # < 100ms
def test_pure_logic():
    """Fast unit test with no I/O."""
    pass

@pytest.mark.slow  # > 1s
def test_filesystem_heavy():
    """Integration test with file operations."""
    pass

@pytest.mark.critical  # Must pass regardless of speed
def test_core_functionality():
    """Essential functionality test."""
    pass
```

### WSL Test Runner Configuration

```python
# run_tests_wsl.py usage patterns

# Quick validation (2 seconds)
# Uses: NO pytest, direct imports only
python3 quick_test.py

# Fast tests only (~30 seconds)
# Runs: @pytest.mark.fast tests
python3 run_tests_wsl.py --fast

# Critical tests only
# Runs: @pytest.mark.critical tests
python3 run_tests_wsl.py --critical

# Single file (minimal I/O)
python3 run_tests_wsl.py --file tests/unit/test_utils.py

# Pattern matching
python3 run_tests_wsl.py -k test_shot_model

# Full suite in batches (best for WSL)
python3 run_tests_wsl.py --all
```

### WSL-Optimized pytest.ini

```ini
# pytest_wsl.ini - Optimized for WSL filesystem
[tool:pytest]
# Disable plugins that cause excessive I/O
addopts = 
    -q                    # Quiet output
    -ra                   # Show all test outcomes
    --maxfail=1          # Stop on first failure
    -p no:cacheprovider  # Disable cache (slow on WSL)
    -p no:warnings       # Disable warning collection
    --tb=short           # Shorter tracebacks

# Only collect from tests directory
testpaths = tests

# Disable doctest collection (slow)
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

### Batching Strategy for Large Test Suites

```python
def run_tests_in_batches(test_files, batch_size=10):
    """Run tests in batches to avoid WSL timeouts."""
    batches = [test_files[i:i+batch_size] 
               for i in range(0, len(test_files), batch_size)]
    
    for i, batch in enumerate(batches, 1):
        print(f"Running batch {i}/{len(batches)}")
        result = pytest.main([
            "-q",
            "--tb=short",
            "--maxfail=3",
        ] + batch)
        
        if result != 0:
            print(f"Batch {i} failed")
            return result
    
    return 0
```

### WSL Performance Tips

1. **Use tmpfs for test artifacts**
   ```python
   @pytest.fixture
   def fast_tmp(tmp_path_factory):
       """Use /tmp (usually tmpfs) instead of /mnt/c."""
       return tmp_path_factory.mktemp("test", numbered=True, 
                                      base_tmp=Path("/tmp"))
   ```

2. **Minimize test collection**
   ```python
   # Explicit file listing is faster than discovery
   pytest tests/unit/test_shot_model.py tests/unit/test_utils.py
   ```

3. **Disable unnecessary pytest features**
   ```python
   # In conftest.py
   def pytest_configure(config):
       if os.environ.get("WSL_DISTRO_NAME"):
           config.option.verbose = 0
           config.option.capture = "no"
   ```

---

## Quick Lookup Table

### Common Scenarios → Solutions

| Scenario | Solution | Example |
|----------|----------|---------|
| Testing shot model refresh | TestProcessPoolManager with preset outputs | `model._process_pool = TestProcessPoolManager()` |
| Testing thumbnails in threads | ThreadSafeTestImage, never QPixmap | `image = ThreadSafeTestImage(100, 100)` |
| Testing 'ws' command | Interactive bash subprocess pattern | `["/bin/bash", "-i", "-c", "ws -sg"]` |
| Testing cache components | Test in isolation, integrate at boundaries | See Cache Architecture Testing |
| Testing Qt dialogs | Mock exec() to prevent blocking | `monkeypatch.setattr(QDialog, "exec", lambda: Accepted)` |
| Testing worker threads | QThread with proper cleanup | `worker.quit(); worker.wait(1000)` |
| Testing signal emission | Set up waitSignal BEFORE action | `with qtbot.waitSignal(sig): action()` |
| Testing file operations | Use tmp_path fixture | `def test(tmp_path): ...` |
| Testing with timers | qtbot.waitUntil with condition | `qtbot.waitUntil(lambda: done, timeout=1000)` |
| Testing async operations | qtbot.waitSignal with timeout | `with qtbot.waitSignal(sig, timeout=1000): ...` |
| Testing on WSL | Use categorized test runners | `python3 run_tests_wsl.py --fast` |
| Testing properties | Hypothesis with strategies | `@given(st.from_regex(...))` |

### Anti-Pattern Detection Rules

```python
# Automated anti-pattern checking
def check_test_for_antipatterns(test_code: str) -> List[str]:
    """Check test code for common anti-patterns."""
    errors = []
    
    if "QPixmap" in test_code and "threading.Thread" in test_code:
        errors.append("FATAL: QPixmap in worker thread will crash")
    
    if "mock.assert_called" in test_code and "_" in test_code:
        errors.append("Testing private method calls - test behavior instead")
    
    if "QSignalSpy" in test_code and "Mock" in test_code:
        errors.append("QSignalSpy only works with real Qt signals")
    
    if re.search(r"Mock\(spec=(\w+)\).*\1", test_code):
        errors.append("Mocking class under test - pointless")
    
    if "worker.start()" in test_code and "waitSignal" in test_code:
        if test_code.index("worker.start()") < test_code.index("waitSignal"):
            errors.append("Signal race condition - set up waitSignal first")
    
    return errors
```

---

## Critical Pitfalls

### ⚠️ Qt Threading Violations (FATAL)
```python
# ❌ CRASHES PYTHON - QPixmap in worker thread
def test_worker():
    def worker_func():
        pixmap = QPixmap(100, 100)  # FATAL: "Fatal Python error: Aborted"
    threading.Thread(target=worker_func).start()

# ✅ SAFE - QImage-based test double
def test_worker():
    def worker_func():
        image = ThreadSafeTestImage(100, 100)  # Thread-safe
    threading.Thread(target=worker_func).start()
```

### ⚠️ Qt Container Truthiness
```python
# ❌ DANGEROUS - Qt containers are falsy when empty!
if self.layout:  # False for empty QVBoxLayout!
    self.layout.addWidget(widget)

# ✅ SAFE - Explicit None check
if self.layout is not None:
    self.layout.addWidget(widget)

# Affected: QVBoxLayout, QHBoxLayout, QListWidget, QTreeWidget
```

### ⚠️ QSignalSpy Only Works with Real Signals
```python
# ❌ CRASHES
mock_widget = Mock()
spy = QSignalSpy(mock_widget.signal)  # TypeError!

# ✅ WORKS
real_widget = QWidget()
spy = QSignalSpy(real_widget.destroyed)  # Real signal
```

### ⚠️ Widget Initialization Order
```python
# ❌ WRONG - AttributeError risk
class MyWidget(QWidget):
    def __init__(self):
        super().__init__()  # Might trigger signals!
        self.data = []      # Too late!

# ✅ CORRECT
class MyWidget(QWidget):
    def __init__(self):
        self.data = []      # Initialize first
        super().__init__()
```

### ⚠️ Never Create GUI in Worker Threads
```python
# ❌ CRASH
class Worker(QThread):
    def run(self):
        dialog = QDialog()  # GUI in wrong thread!

# ✅ CORRECT
class Worker(QThread):
    show_dialog = pyqtSignal(str)
    
    def run(self):
        self.show_dialog.emit("message")  # Main thread shows
```

### ⚠️ Don't Mock Class Under Test
```python
# ❌ POINTLESS
def test_controller():
    controller = Mock(spec=Controller)
    controller.process.return_value = "result"
    # Testing the mock, not the controller!

# ✅ MEANINGFUL
def test_controller():
    controller = Controller(dependencies=Mock())
    result = controller.process()
    assert result == expected
```

### Flakiness Management

#### Test Quarantine Policy
```python
import pytest
from datetime import datetime

@pytest.mark.flaky(
    reruns=3,
    reruns_delay=1,
    deadline=datetime(2024, 12, 31),  # Must be fixed by this date
    owner="team_member_name",
    issue="JIRA-123"
)
def test_known_flaky():
    """Test with known race condition."""
    pass

# Strict xfail for platform issues
@pytest.mark.xfail(
    sys.platform == "win32",
    reason="WSL filesystem issue",
    strict=True  # Must fail consistently
)
def test_filesystem_heavy():
    pass
```

#### Order Independence
```python
# conftest.py
def pytest_configure(config):
    """Ensure test order independence."""
    # Enable random order
    config.option.randomly_seed = 42  # Reproducible randomness
    config.option.randomly_dont_shuffle = False
```

#### Timeout Management
```python
import pytest

@pytest.mark.timeout(5)  # 5 second timeout
def test_with_timeout():
    """Test that must complete quickly."""
    pass

# For threading tests
def test_thread_cleanup():
    worker = WorkerThread()
    worker.start()
    
    # Always use timeout when joining threads
    worker.join(timeout=5.0)
    
    if worker.is_alive():
        worker.terminate()  # Force cleanup
        pytest.fail("Worker thread did not finish in time")
```

---

## Quick Reference

### Testing Checklist
- [ ] Use real components where possible
- [ ] Mock only external dependencies
- [ ] Use `qtbot.addWidget()` for all widgets
- [ ] Check `is not None` for Qt containers
- [ ] Initialize attributes before `super().__init__()`
- [ ] Use QSignalSpy only with real signals
- [ ] Clean up workers in fixtures
- [ ] Mock dialog `exec()` methods
- [ ] Test both success and error paths
- [ ] **Use ThreadSafeTestImage instead of QPixmap in worker threads**
- [ ] **Patch QImage operations, not QPixmap operations in threading tests**
- [ ] **Verify no "Fatal Python error: Aborted" crashes in threading tests**
- [ ] **Set up qtbot.waitSignal() BEFORE starting operations to avoid race conditions**
- [ ] **Use TestProcessPoolManager for 'ws' command testing**
- [ ] **Categorize tests as fast/slow/critical for WSL**

### Command Patterns
```python
# Run tests
python run_tests.py  # Never use pytest directly

# WSL-optimized testing
python3 quick_test.py              # 2 second validation
python3 run_tests_wsl.py --fast    # ~30 seconds
python3 run_tests_wsl.py --critical # Key tests only
python3 run_tests_wsl.py --all     # Full suite in batches

# With coverage
python run_tests.py --cov

# Specific test
python run_tests.py tests/unit/test_shot_model.py::TestShot::test_creation
```

### Common Fixtures
```python
@pytest.fixture
def qtbot(): ...           # Qt test interface
@pytest.fixture
def tmp_path(): ...         # Temp directory
@pytest.fixture
def monkeypatch(): ...      # Mock attributes
@pytest.fixture
def caplog(): ...           # Capture logs
@pytest.fixture
def make_shot(): ...        # Shot factory
@pytest.fixture
def test_process_pool(): ...  # Configured TestProcessPoolManager
```

### Before vs After Example
```python
# ❌ BEFORE - Excessive mocking
def test_bad(self):
    with patch.object(model._process_pool, 'execute') as mock:
        mock.return_value = "data"
        model.refresh()
        mock.assert_called()  # Testing mock

# ✅ AFTER - Test double with real behavior
def test_good(self):
    model._process_pool = TestProcessPoolManager()
    model._process_pool.set_outputs("workspace /test/path")
    
    result = model.refresh()
    
    assert result.success  # Testing behavior
    assert len(model.get_shots()) == 1
```

### Anti-Patterns Summary
```python
# ❌ QPixmap in worker threads (CRASHES)
threading.Thread(target=lambda: QPixmap(100, 100)).start()

# ❌ QSignalSpy with mocks
spy = QSignalSpy(mock.signal)

# ❌ Qt container truthiness
if self.layout:

# ❌ GUI in threads
worker.run(): QDialog()

# ❌ Mock everything
controller = Mock(spec=Controller)

# ❌ Parent chain access
self.parent().parent().method()

# ❌ Testing implementation
mock.assert_called_once()

# ❌ Signal race conditions
worker.start(); with qtbot.waitSignal(worker.signal): pass
```

---

## Summary

**Philosophy**: Test behavior, not implementation.

**Strategy**: Real components with test doubles for I/O.

**Qt-Specific**: Respect the event loop, signals are first-class, threading rules are FATAL.

**WSL-Specific**: Categorize tests, use optimized runners, batch for performance.

**Key Metrics**:
- Test speed: 60% faster (no subprocess overhead)
- Bug discovery: 200% increase (real integration)
- Maintenance: 75% less (fewer mock updates)

---
*Last Updated: 2025-08-23 | Critical Reference - DO NOT DELETE*

**Recent Additions**: 
- Test Organization & Decision Trees for LLM-optimized test placement
- Complete Test Templates for common patterns
- Property-Based Testing with Hypothesis
- Cache Architecture Testing matrix
- WSL Testing Strategies for performance
- Quick Lookup Table for scenario → solution mapping
- Enhanced flakiness management and quarantine policies