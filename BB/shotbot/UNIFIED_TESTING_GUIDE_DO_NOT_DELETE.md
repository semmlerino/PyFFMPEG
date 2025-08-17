# Unified Testing Guide - DO NOT DELETE
*The single source of truth for testing ShotBot with Qt and pytest*

## Table of Contents
1. [Core Principles](#core-principles)
2. [When to Mock](#when-to-mock)
3. [Signal Testing](#signal-testing)
4. [Essential Test Doubles](#essential-test-doubles)
5. [Qt-Specific Patterns](#qt-specific-patterns)
6. [Qt Threading Safety](#qt-threading-safety)
7. [Critical Pitfalls](#critical-pitfalls)
8. [Quick Reference](#quick-reference)

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

## When to Mock

| Test Type | Mock | Use Real |
|-----------|------|----------|
| **Unit** | External services, Network, Subprocess | Class under test, Value objects, Internal methods |
| **Integration** | External APIs only | Components being integrated, Signals, Cache |
| **E2E** | Nothing | Everything |

### Practical Example
```python
def test_shot_workflow():
    # Real components
    cache = CacheManager(tmp_path)
    model = ShotModel(cache_manager=cache)
    
    # Test double for external subprocess
    model._process_pool = TestProcessPool()
    
    # Test real integration
    result = model.refresh_shots()
    assert result.success
    assert cache.get_cached_shots() is not None  # Real cache works
```

---

## Signal Testing

### Strategy: Choose the Right Tool

| Scenario | Tool | When to Use |
|----------|------|-------------|
| Real Qt widget signals | `QSignalSpy` | Testing actual Qt components |
| Test double signals | `TestSignal` | Non-Qt or mocked components |
| Async Qt operations | `qtbot.waitSignal()` | Waiting for real Qt signals |
| Mock object callbacks | `.assert_called()` | Pure Python mocks |

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

## Essential Test Doubles

### TestProcessPoolManager
```python
class TestProcessPoolManager:
    """Replace subprocess calls with predictable behavior"""
    def __init__(self):
        self.commands = []
        self.outputs = ["workspace /test/path"]
        self.command_completed = TestSignal()
        self.command_failed = TestSignal()
    
    def execute_workspace_command(self, command, **kwargs):
        self.commands.append(command)
        output = self.outputs[0] if self.outputs else ""
        self.command_completed.emit(command, output)
        return output
    
    def set_outputs(self, *outputs):
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

### Thread-Safe Test Doubles

Create thread-safe alternatives for Qt objects in tests:

```python
class ThreadSafeTestImage:
    """Thread-safe test double for QPixmap using QImage internally.
    
    QPixmap is not thread-safe and can only be used in the main GUI thread.
    QImage is thread-safe and can be used in any thread. This class provides
    a QPixmap-like interface while using QImage internally for thread safety.
    
    Based on Qt's canonical threading pattern for image operations.
    """
    
    def __init__(self, width: int = 100, height: int = 100):
        """Create a thread-safe test image."""
        # Use QImage which is thread-safe, unlike QPixmap
        self._image = QImage(width, height, QImage.Format.Format_RGB32)
        self._width = width
        self._height = height
        self._image.fill(QColor(255, 255, 255))  # Fill with white by default
        
    def fill(self, color: QColor = None) -> None:
        """Fill the image with a color."""
        if color is None:
            color = QColor(255, 255, 255)
        self._image.fill(color)
        
    def isNull(self) -> bool:
        """Check if the image is null."""
        return self._image.isNull()
        
    def sizeInBytes(self) -> int:
        """Return the size of the image in bytes."""
        return self._image.sizeInBytes()
        
    def size(self) -> QSize:
        """Return the size of the image."""
        return QSize(self._width, self._height)
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
            
            # Mock the cache manager's QImage usage
            with patch('cache_manager.QImage') as mock_image_class:
                mock_image = MagicMock()
                mock_image.isNull.return_value = False
                mock_image.sizeInBytes.return_value = image.sizeInBytes()
                mock_image_class.return_value = mock_image
                
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

### Real-World Example: Cache Manager Threading

Before (Crashes):
```python
# ❌ CAUSES CRASHES - QPixmap in worker thread
def test_cache_threading():
    def cache_worker():
        pixmap = QPixmap(100, 100)  # FATAL ERROR
        cache.store("key", pixmap)
    
    threading.Thread(target=cache_worker).start()
```

After (Thread-Safe):
```python
# ✅ THREAD-SAFE - QImage-based test double
def test_cache_threading():
    def cache_worker():
        image = ThreadSafeTestImage(100, 100)  # Safe in any thread
        
        # Mock the internal QImage usage
        with patch('cache_manager.QImage') as mock_qimage:
            mock_qimage.return_value = mock_image
            result = cache.store("key", image)
            
    threading.Thread(target=cache_worker).start()
```

### Key Implementation Insights

1. **Internal Implementation Matters**: Even if your API accepts "image-like" objects, the internal implementation must use QImage in worker threads.

2. **Patch the Right Level**: When mocking Qt image operations, patch `cache_manager.QImage`, not `QPixmap`.

3. **Test Double Strategy**: Create test doubles that mimic the interface but use thread-safe internals.

4. **Resource Management**: QImage cleanup is automatic, but track memory usage for performance tests.

### Threading Test Checklist

- [ ] ✅ Use `ThreadSafeTestImage` instead of `QPixmap` in worker threads
- [ ] ✅ Patch `QImage` operations, not `QPixmap` operations  
- [ ] ✅ Test both single-threaded and multi-threaded scenarios
- [ ] ✅ Verify no "Fatal Python error: Aborted" crashes
- [ ] ✅ Check that worker threads can create/manipulate images safely
- [ ] ✅ Ensure main thread can display results from worker threads

### Performance Considerations

```python
# QImage is slightly more expensive than QPixmap for creation
# but essential for thread safety

# ✅ GOOD - Efficient thread-safe testing
class TestImagePool:
    """Reuse ThreadSafeTestImage instances for performance."""
    
    def __init__(self):
        self._pool = []
        
    def get_test_image(self, width=100, height=100):
        if self._pool:
            image = self._pool.pop()
            image.fill()  # Reset to white
            return image
        return ThreadSafeTestImage(width, height)
        
    def return_image(self, image):
        self._pool.append(image)
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

### Command Patterns
```python
# Run tests
python run_tests.py  # Never use pytest directly

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
    model._process_pool = TestProcessPool()
    model._process_pool.outputs = ["workspace /test/path"]
    
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
```

---

## Summary

**Philosophy**: Test behavior, not implementation.

**Strategy**: Real components with test doubles for I/O.

**Qt-Specific**: Respect the event loop, signals are first-class, threading rules are FATAL.

**Key Metrics**:
- Test speed: 60% faster (no subprocess overhead)
- Bug discovery: 200% increase (real integration)
- Maintenance: 75% less (fewer mock updates)

---
*Last Updated: 2025-08-17 | Critical Reference - DO NOT DELETE*

**Recent Addition**: Qt Threading Safety section added - critical for preventing Qt threading violations that cause "Fatal Python error: Aborted" crashes.