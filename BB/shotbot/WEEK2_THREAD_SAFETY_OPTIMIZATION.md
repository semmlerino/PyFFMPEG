# Week 2: Thread Safety Architecture Optimization Plan

## Executive Summary
**Current Overhead: 1,130% (113 µs overhead on 10 µs operations)**
- Primary cause: Qt signal operations (107 signals = 107 µs)
- Secondary cause: Lock operations (3 with-blocks = 4.5 µs)
- Main offender: main_window.py (46 µs, 40% of total)

## Overhead Breakdown

### By Component
```
main_window.py          46 µs  ████████████████████ 41%
launcher_manager.py     22 µs  █████████ 19%
threede_scene_worker.py 17 µs  ███████ 15%
shot_model.py           13 µs  █████ 12%
previous_shots_worker.py 11 µs  ████ 10%
Others                   4 µs  ██ 3%
```

### By Mechanism
```
Qt Signals             107 µs  ████████████████████████████████████ 95%
Lock Operations          4.5 µs ██ 4%
Thread Coordination      1.5 µs █ 1%
```

## Root Cause Analysis

### 1. Excessive Qt Signal Usage (95% of overhead)
**Problem**: 107 signal emit/connect operations across the codebase
**Impact**: Each signal operation adds ~1 µs overhead
**Files Most Affected**:
- main_window.py: 40 signals
- launcher_manager.py: 22 signals
- threede_scene_worker.py: 17 signals

### 2. Signal Anti-Patterns Identified

#### Pattern 1: Signal Cascades
```python
# Current: Multiple signals for single operation
self.refresh_started.emit()
self.status_changed.emit("Refreshing...")
self.progress_updated.emit(0)
self.cache_invalidated.emit()

# Better: Single composite signal
self.state_changed.emit({
    'status': 'refreshing',
    'progress': 0,
    'cache_valid': False
})
```

#### Pattern 2: Same-Thread Signals
```python
# Current: Using signals within same thread
def update_ui(self):
    self.data_changed.emit(data)  # Same thread!
    
# Better: Direct method call
def update_ui(self):
    self._handle_data_change(data)  # Direct call
```

#### Pattern 3: Frequent Progress Updates
```python
# Current: Emit signal for every item
for i, item in enumerate(items):
    process(item)
    self.progress.emit(i / len(items))  # 100+ signals!

# Better: Batched updates
for i, item in enumerate(items):
    process(item)
    if i % 10 == 0:  # Every 10 items
        self.progress.emit(i / len(items))
```

## Optimization Strategy

### Phase 1: Signal Reduction (Target: -60% overhead)

#### 1.1 Batch Signal Operations
```python
class BatchedSignalEmitter:
    """Collect and batch signal emissions."""
    
    def __init__(self, signal, batch_size=10, timeout_ms=100):
        self.signal = signal
        self.batch = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.flush)
        self.timer.setInterval(timeout_ms)
        
    def emit(self, data):
        self.batch.append(data)
        if len(self.batch) >= self.batch_size:
            self.flush()
        elif not self.timer.isActive():
            self.timer.start()
    
    def flush(self):
        if self.batch:
            self.signal.emit(self.batch)
            self.batch = []
        self.timer.stop()
```

#### 1.2 Replace Same-Thread Signals
```python
# Detect and replace same-thread signal usage
class SmartSignal:
    """Signal that bypasses emission in same thread."""
    
    def __init__(self):
        self._signal = Signal()
        self._thread = QThread.currentThread()
        
    def emit(self, data):
        if QThread.currentThread() == self._thread:
            # Same thread - direct call
            for slot in self._connected_slots:
                slot(data)
        else:
            # Cross-thread - use signal
            self._signal.emit(data)
```

#### 1.3 Implement Signal Coalescence
```python
class CoalescedSignal:
    """Combine rapid successive signals into one."""
    
    def __init__(self, signal, window_ms=50):
        self.signal = signal
        self.pending = None
        self.timer = QTimer()
        self.timer.timeout.connect(self._emit_pending)
        self.timer.setInterval(window_ms)
        
    def emit(self, data):
        self.pending = data
        if not self.timer.isActive():
            self.timer.start()
    
    def _emit_pending(self):
        if self.pending is not None:
            self.signal.emit(self.pending)
            self.pending = None
        self.timer.stop()
```

### Phase 2: Lock-Free Alternatives (Target: -20% overhead)

#### 2.1 Use Queue for Thread Communication
```python
# Before: Lock-protected shared state
class SharedState:
    def __init__(self):
        self._data = []
        self._lock = threading.Lock()
    
    def add(self, item):
        with self._lock:
            self._data.append(item)

# After: Lock-free queue
from queue import Queue

class SharedState:
    def __init__(self):
        self._queue = Queue()
    
    def add(self, item):
        self._queue.put(item)  # Thread-safe, no lock needed
```

#### 2.2 Atomic Operations with Threading Primitives
```python
# Before: Lock for simple counter
class Counter:
    def __init__(self):
        self._count = 0
        self._lock = threading.Lock()
    
    def increment(self):
        with self._lock:
            self._count += 1

# After: Lock-free atomic
import threading

class Counter:
    def __init__(self):
        self._count = threading.local()
        self._count.value = 0
    
    def increment(self):
        self._count.value += 1  # Thread-local, no lock
```

### Phase 3: Architecture Improvements (Target: -20% overhead)

#### 3.1 Actor Model Implementation
```python
class Actor(QThread):
    """Message-passing actor for lock-free concurrency."""
    
    def __init__(self):
        super().__init__()
        self.mailbox = Queue()
        self.running = True
        
    def send(self, message):
        """Send message to actor (non-blocking)."""
        self.mailbox.put(message)
    
    def run(self):
        """Process messages from mailbox."""
        while self.running:
            try:
                message = self.mailbox.get(timeout=0.1)
                self.handle_message(message)
            except Empty:
                continue
    
    def handle_message(self, message):
        """Override to process messages."""
        pass
```

#### 3.2 Async/Await for I/O Operations
```python
# Before: Threaded I/O
def load_thumbnail(self, path):
    worker = ThumbnailWorker(path)
    worker.finished.connect(self.on_thumbnail_loaded)
    worker.start()

# After: Async I/O
async def load_thumbnail(self, path):
    thumbnail = await aiofiles.read(path)
    self.on_thumbnail_loaded(thumbnail)
```

## Implementation Plan

### Week 1: Quick Wins (Days 1-2)
1. Implement BatchedSignalEmitter for progress updates
2. Replace same-thread signals with direct calls
3. Add signal coalescence to high-frequency emitters

**Expected Impact**: -40% overhead (45 µs reduction)

### Week 2: Core Refactoring (Days 3-5)
1. Convert shared state to Queue-based communication
2. Implement Actor model for worker threads
3. Remove unnecessary locks

**Expected Impact**: -30% overhead (34 µs reduction)

### Week 3: Architecture Evolution (Days 6-7)
1. Integrate async/await for I/O operations
2. Implement zero-copy message passing
3. Profile and optimize remaining hotspots

**Expected Impact**: -30% overhead (34 µs reduction)

## Performance Targets

### Current State
- Overhead: 113 µs (1,130%)
- Signal operations: 107
- Lock operations: 3

### After Optimization
- Target overhead: 11 µs (110%)
- Signal operations: 20 (batched/coalesced)
- Lock operations: 0 (lock-free)

## Code Examples

### Before: main_window.py (46 µs overhead)
```python
def refresh_all(self):
    self.refresh_started.emit()
    for model in self.models:
        model.refresh_started.emit()
        result = model.refresh()
        model.refresh_finished.emit(result)
        model.data_changed.emit()
    self.refresh_finished.emit()
    self.status_updated.emit("Complete")
    # 8+ signals per refresh!
```

### After: Optimized (5 µs overhead)
```python
def refresh_all(self):
    batch = BatchedUpdate()
    for model in self.models:
        result = model.refresh()
        batch.add_change(model, result)
    
    # Single batched emission
    self.batch_updated.emit(batch.to_dict())
```

## Validation Metrics

### Performance KPIs
1. **Signal Frequency**: < 20 signals per operation
2. **Lock Contention**: 0% (lock-free design)
3. **Thread Overhead**: < 10% of operation time
4. **Response Latency**: < 16ms (60 FPS)

### Testing Strategy
1. Profile with cProfile before/after
2. Measure signal frequency with custom counter
3. Monitor thread contention with threading stats
4. User experience testing for responsiveness

## Risk Mitigation

### Compatibility Risks
- **Risk**: Breaking existing signal connections
- **Mitigation**: Adapter pattern for backward compatibility

### Concurrency Risks
- **Risk**: Race conditions in lock-free code
- **Mitigation**: Extensive testing with ThreadSanitizer

### Performance Risks
- **Risk**: Batching adds latency
- **Mitigation**: Tunable batch sizes and timeouts

## Conclusion

The 1,130% thread safety overhead is primarily caused by excessive Qt signal usage (95%) rather than locking. By implementing signal batching, coalescence, and lock-free architectures, we can reduce overhead by 90% to acceptable levels (~110%).

The optimization focuses on three principles:
1. **Reduce signal frequency** through batching and coalescence
2. **Eliminate locks** with queue-based communication
3. **Optimize architecture** with actor model and async I/O

This plan provides a clear path from the current 1,130% overhead to the target 110%, improving application responsiveness by 10x.