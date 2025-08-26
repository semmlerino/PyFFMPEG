# Test Reliability Fixes


## Resource Leaks

**Fix:** Use context managers or ensure cleanup in teardown


### test_doubles_library.py
  - Line 125: Resource created without cleanup
  - Line 133: Resource created without cleanup

### test_command_launcher_refactored.py
  - Line 55: Resource created without cleanup

## Thread Issues

**Fix:** Always wait for threads to complete with .wait() or .join()


### test_doubles_library.py
  - Line 33: Thread started without wait/join
  - Line 532: Thread started without wait/join

### test_cache_integration.py
  - Line 383: Thread started without wait/join

### test_cache_manager.py
  - Line 6: Thread started without wait/join
  - Line 311: Thread started without wait/join
  - Line 568: Thread started without wait/join
  - Line 581: Thread started without wait/join
  - Line 922: Thread started without wait/join
  - Line 1073: Thread started without wait/join
  - Line 1139: Thread started without wait/join

## Signal Timing

**Fix:** Always specify explicit timeout (e.g., timeout=1000)


### test_previous_shots_model.py
  - Line 158: waitSignal without explicit timeout

### test_previous_shots_worker.py
  - Line 252: waitSignal without explicit timeout

## Summary
Total reliability issues: 40

### Priority Fixes
1. Fix race conditions in signal tests
2. Add proper thread cleanup
3. Fix resource leaks
4. Add explicit timeouts to all waitSignal calls
