# Next Task: Fix ProcessPoolManager Singleton Race Condition

## Issue Description
The current singleton implementation in `ProcessPoolManager` has a race condition between checking `_instance` and setting `_initialized`. Multiple threads could get a partially initialized instance.

## Current Code (UNSAFE)
```python
# process_pool_manager.py:205-242
def __new__(cls, *args, **kwargs):
    with cls._lock:
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._initialized = False  # Race condition here
            cls._instance = instance
        return cls._instance
```

## Fix Implementation (SAFE)

### Option 1: Double-Checked Locking (Recommended)
```python
def __new__(cls, *args, **kwargs):
    # Fast path - no lock if already initialized
    if cls._instance is None:
        with cls._lock:
            # Double-check inside lock
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instance = instance
    return cls._instance
```

### Option 2: Early Initialization
```python
# At module level
_instance = ProcessPoolManager()

class ProcessPoolManager:
    @classmethod
    def get_instance(cls):
        return _instance
```

### Option 3: Thread-Safe Lazy Initialization
```python
import threading

class ProcessPoolManager:
    _instance = None
    _lock = threading.RLock()
    _initialization_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is not None:
            return cls._instance
            
        with cls._initialization_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._initialized = False
                # Complete initialization before assignment
                instance.__init__(*args, **kwargs)
                instance._initialized = True
                cls._instance = instance
            return cls._instance
```

## Testing the Fix

```python
# test_singleton_thread_safety.py
import threading
import time
from process_pool_manager import ProcessPoolManager

def get_instance(results, index):
    instance = ProcessPoolManager.get_instance()
    results[index] = id(instance)

def test_singleton_thread_safety():
    results = {}
    threads = []
    
    # Create 100 threads that all try to get instance simultaneously
    for i in range(100):
        thread = threading.Thread(target=get_instance, args=(results, i))
        threads.append(thread)
    
    # Start all threads at once
    for thread in threads:
        thread.start()
    
    # Wait for completion
    for thread in threads:
        thread.join()
    
    # All should have same instance ID
    instance_ids = set(results.values())
    assert len(instance_ids) == 1, f"Multiple instances created: {instance_ids}"
    print("✅ Singleton is thread-safe")

if __name__ == "__main__":
    test_singleton_thread_safety()
```

## Implementation Steps

1. **Backup current file**:
   ```bash
   cp process_pool_manager.py process_pool_manager.py.backup
   ```

2. **Apply the fix** (use Option 1 - Double-Checked Locking)

3. **Test the fix**:
   ```bash
   python3 test_singleton_thread_safety.py
   ```

4. **Run existing tests**:
   ```bash
   python3 -m pytest tests/unit/test_process_pool_manager.py -v
   ```

5. **Verify no regression**:
   ```bash
   python3 shotbot.py --mock --headless
   ```

## Expected Outcome
- Eliminates race condition in singleton creation
- Ensures only one ProcessPoolManager instance exists
- Maintains backward compatibility
- Improves thread safety score from B+ to A-