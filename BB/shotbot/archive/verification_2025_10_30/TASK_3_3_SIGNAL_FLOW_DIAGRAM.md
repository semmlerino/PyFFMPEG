# Task 3.3: Signal-Slot Type Flow Diagram

Visual explanation of the lambda closure and signal parameter mapping.

---

## Signal Definition

**File:** `launcher/worker.py` (line 33)

```python
class LauncherWorker(ThreadSafeWorker):
    command_finished = Signal(str, bool, int)  # launcher_id, success, return_code
```

---

## Signal Emission Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ LauncherWorker (worker thread)                                  │
│                                                                   │
│   def run(self):                                                 │
│       # Execute command...                                       │
│       success = (result.returncode == 0)                         │
│       self.command_finished.emit(                                │
│           self.launcher_id,    # ← Parameter 1: str             │
│           success,             # ← Parameter 2: bool            │
│           result.returncode    # ← Parameter 3: int             │
│       )                                                          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ Qt Signal (across threads)
                            │ QueuedConnection
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Lambda Slot (main thread)                                       │
│                                                                   │
│   lambda lid, success, rc:                                      │
│       ↑     ↑         ↑                                         │
│       │     │         └── Parameter 3: int                      │
│       │     └─────────── Parameter 2: bool                      │
│       └───────────────── Parameter 1: str                       │
│                                                                   │
│   Captured from outer scope:                                    │
│       worker_key  # ← str (created before lambda)               │
│                                                                   │
│   Calls:                                                         │
│       self._on_worker_finished(worker_key, lid, success, rc)   │
│            ↑                ↑          ↑    ↑       ↑           │
│            │                │          │    │       │           │
│            │                │          └────┼───────┘           │
│            │                │               │                    │
│            │                └───────────────┘                    │
│            │                                                     │
│            └── Captured variable (not from signal)              │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ Direct method call
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Handler Method (main thread)                                    │
│                                                                   │
│   def _on_worker_finished(                                      │
│       self,                                                      │
│       worker_key: str,     # ← From lambda capture              │
│       launcher_id: str,    # ← From signal param 1              │
│       success: bool,       # ← From signal param 2              │
│       return_code: int     # ← From signal param 3              │
│   ) -> None:                                                    │
│       # Clean up worker immediately...                          │
│       with QMutexLocker(self._process_lock):                   │
│           if worker_key in self._active_workers:               │
│               del self._active_workers[worker_key]             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Parameter Mapping Table

| Source | Signal Param | Lambda Param | Handler Param | Type | Origin |
|--------|-------------|--------------|---------------|------|--------|
| Worker emit | `self.launcher_id` | `lid` | `launcher_id` | `str` | Signal param 1 |
| Worker emit | `success` | `success` | `success` | `bool` | Signal param 2 |
| Worker emit | `result.returncode` | `rc` | `return_code` | `int` | Signal param 3 |
| Lambda closure | N/A | (captured) | `worker_key` | `str` | Outer scope |

---

## Critical Implementation Order

### ❌ WRONG (NameError)

```python
# STEP 1: Create worker
worker = LauncherWorker(launcher_id, command, working_dir)

# STEP 2: Connect signal FIRST
worker.command_finished.connect(
    lambda lid, success, rc: self._on_worker_finished(
        worker_key,  # ← NameError: name 'worker_key' is not defined!
        lid, success, rc
    ),
    Qt.ConnectionType.QueuedConnection,
)

# STEP 3: Create worker_key AFTER (TOO LATE!)
worker_key = f"{launcher_id}_{timestamp}_{uuid}"
```

**Error:** Lambda tries to capture `worker_key` before it exists.

---

### ✅ CORRECT (Variable exists before capture)

```python
# STEP 1: Create worker
worker = LauncherWorker(launcher_id, command, working_dir)

# STEP 2: Generate worker_key FIRST
timestamp = int(time.time() * 1000)
unique_suffix = uuid.uuid4().hex[:8]
worker_key = f"{launcher_id}_{timestamp}_{unique_suffix}"
#          ↑
#          └── Variable now exists in scope

# STEP 3: Connect signal (captures existing variable)
worker.command_finished.connect(
    lambda lid, success, rc: self._on_worker_finished(
        worker_key,  # ← Captures existing variable (str)
        lid, success, rc
    ),
    Qt.ConnectionType.QueuedConnection,
)

# STEP 4: Store in tracking dict
with QMutexLocker(self._process_lock):
    self._active_workers[worker_key] = worker

# STEP 5: Start worker thread
worker.start()
```

---

## Type Safety Verification

### Lambda Closure Analysis

```python
lambda lid, success, rc: self._on_worker_finished(worker_key, lid, success, rc)
│      │   │       │                              │          │   │       │
│      │   │       │                              │          │   │       └─ Forwarded: int
│      │   │       │                              │          │   └───────── Forwarded: bool
│      │   │       │                              │          └───────────── Forwarded: str
│      │   │       │                              └──────────────────────── Captured: str
│      │   │       └─ Received from signal: int
│      │   └───────── Received from signal: bool
│      └───────────── Received from signal: str
│
└─ Lambda signature: (str, bool, int) -> None
   Matches Signal(str, bool, int) ✅
```

### Closure Capture Safety

**Captured variable:** `worker_key: str`

**Properties:**
- ✅ Immutable type (string)
- ✅ Exists before lambda creation
- ✅ Remains valid for worker lifetime
- ✅ No race conditions (created in main thread, used in main thread)

**Lifetime:**
1. Created: Line ~169 (main thread)
2. Captured: Line ~171 (lambda definition, main thread)
3. Used: When signal fires → lambda executes → handler called (main thread)

**Thread safety:**
- Worker thread: Emits signal (different thread)
- Qt signal system: Queues call (QueuedConnection)
- Lambda executes: Main thread (same thread as creation)
- Handler executes: Main thread

✅ **No threading issues** - all accesses in main thread via Qt event loop

---

## Handler Implementation

```python
def _on_worker_finished(
    self,
    worker_key: str,      # ← Lambda provides this (not from signal)
    launcher_id: str,     # ← Signal param 1
    success: bool,        # ← Signal param 2
    return_code: int      # ← Signal param 3
) -> None:
    """Handle worker thread completion with immediate cleanup.

    This handler receives an EXTRA parameter (worker_key) compared to the
    signal signature. The lambda closure provides this parameter.
    """
    # Immediate cleanup (no 5-second delay)
    with QMutexLocker(self._process_lock):
        if worker_key in self._active_workers:
            worker = self._active_workers[worker_key]

            # Disconnect signals to prevent warnings
            try:
                worker.command_started.disconnect()
                worker.command_finished.disconnect()
                worker.command_error.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected

            # Remove from tracking dictionary
            del self._active_workers[worker_key]
            self.worker_removed.emit(worker_key)

    # Forward to higher-level signal
    self.process_finished.emit(launcher_id, success, return_code)
```

---

## Why This Pattern Works

### Problem Solved

**Before (5-second delay):**
```
Worker finishes → Signal emitted → Handler called → Do nothing
                                                      ↓
                  [Wait 5 seconds with timer]
                                                      ↓
                  Periodic cleanup → Check all workers → Remove finished ones
```

**After (immediate cleanup):**
```
Worker finishes → Signal emitted → Lambda called → Handler called
                                                    ↓
                                    [Immediate cleanup with worker_key]
                                                    ↓
                                    Worker removed from dict instantly
```

### Benefits

1. **Immediate resource cleanup** - No 5-second delay
2. **Exact worker identification** - `worker_key` provides precise lookup
3. **Type-safe** - All parameters properly typed and matched
4. **Thread-safe** - Qt's QueuedConnection handles cross-thread safely
5. **No race conditions** - `worker_key` created before use

---

## Basedpyright Verification

**Type checker sees:**
```python
# Signal definition
command_finished: Signal[str, bool, int]

# Lambda closure
lambda lid: str, success: bool, rc: int -> None:
    self._on_worker_finished(
        worker_key: str,   # Captured from outer scope
        lid: str,          # From signal param 1
        success: bool,     # From signal param 2
        rc: int            # From signal param 3
    ) -> None

# Handler signature
def _on_worker_finished(
    self,
    worker_key: str,
    launcher_id: str,
    success: bool,
    return_code: int
) -> None:
```

✅ **All types match** - No errors from basedpyright

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Creating worker_key after lambda
```python
worker.command_finished.connect(lambda ...: ... worker_key ...)
worker_key = "..."  # NameError!
```

### ❌ Mistake 2: Wrong parameter order in handler
```python
# Signal emits: (launcher_id, success, return_code)
# Handler expects: (success, launcher_id, return_code)  # WRONG ORDER!
```

### ❌ Mistake 3: Mutable capture
```python
# DON'T capture mutable objects that might change
worker_key = [launcher_id]  # List (mutable)
lambda ...: worker_key[0]   # Dangerous!
```

### ✅ Correct: Immutable string capture
```python
worker_key = f"{launcher_id}_{timestamp}_{uuid}"  # str (immutable)
lambda ...: worker_key  # Safe!
```

---

## Testing Strategy

```python
def test_worker_cleanup_immediate():
    """Test that worker is cleaned up immediately on finish."""
    manager = LauncherProcessManager()

    # Execute command
    worker_key = manager.execute_with_worker("test", "echo hello")

    # Verify worker in active dict
    assert worker_key in manager._active_workers

    # Wait for worker to finish
    QTest.qWait(100)

    # Verify worker removed immediately (not after 5 seconds)
    assert worker_key not in manager._active_workers
```

---

## Summary

**Key Points:**
1. Create `worker_key` BEFORE lambda definition
2. Lambda captures immutable `worker_key` string
3. Signal emits 3 parameters → Lambda receives 3 parameters
4. Lambda adds 1 captured parameter → Handler receives 4 parameters
5. All types match and verified by basedpyright ✅
