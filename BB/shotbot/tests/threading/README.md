# Threading Test Utilities

This directory contains comprehensive type-safe threading test utilities for ShotBot. The utilities are designed to work seamlessly with the existing `ThreadSafeWorker` and `LauncherManager` architecture while providing powerful tools for testing thread safety, race conditions, deadlocks, and performance.

## Features

- **Type Safety**: Full basedpyright compatibility with Python 3.8 annotations
- **Integration**: Works with existing `ThreadSafeWorker` and `LauncherManager`
- **Race Condition Testing**: Deterministic race condition creation and detection
- **Deadlock Detection**: Analysis of lock hierarchies and cycle detection
- **Performance Benchmarking**: Thread operation performance measurement
- **pytest Integration**: Fixtures for isolated testing environments

## Quick Start

```python
from tests.threading.threading_test_utils import (
    ThreadingTestHelpers,
    RaceConditionFactory,
    DeadlockDetector,
    PerformanceMetrics,
)

# Test worker state transitions
result = ThreadingTestHelpers.wait_for_worker_state(
    worker, WorkerState.RUNNING, timeout_ms=1000
)
assert result.success

# Create deterministic race condition
race_result = RaceConditionFactory.create_state_race(
    workers=[worker1, worker2], 
    target_state=WorkerState.STOPPED
)

# Detect deadlocks
analysis = DeadlockDetector.detect_deadlock(timeout_ms=5000)
assert not analysis.deadlock_detected

# Benchmark performance
perf_result = PerformanceMetrics.measure_thread_creation(
    worker_factory, iterations=10
)
```

## Core Components

### 1. ThreadingTestHelpers

Static helper methods for common threading test operations:

- `wait_for_worker_state()`: Wait for specific worker state with timeout
- `trigger_race_condition()`: Create deterministic race conditions
- `monitor_thread_safety()`: Detect thread safety violations
- `create_concurrent_workers()`: Spawn multiple workers safely

### 2. DeadlockDetector

Deadlock detection and analysis:

- `detect_deadlock()`: Analyze threads for deadlock conditions
- `get_lock_graph()`: Build wait-for dependency graph
- `find_cycles()`: Detect circular dependencies in lock graph
- `get_thread_stacks()`: Capture stack traces for analysis

### 3. RaceConditionFactory

Create deterministic race conditions for testing:

- `create_state_race()`: Race in worker state transitions
- `create_signal_race()`: Race Qt signal emissions vs disconnections
- `create_resource_race()`: Race for shared resource access
- `create_cleanup_race()`: Race cleanup vs active operations

### 4. PerformanceMetrics

Benchmark threading operation performance:

- `measure_thread_creation()`: Benchmark worker creation time
- `measure_lock_contention()`: Measure lock wait times under contention
- `measure_signal_latency()`: Qt signal performance across threads
- `compare_before_after()`: A/B test performance improvements

### 5. pytest Fixtures

Type-safe fixtures for test isolation:

- `isolated_launcher_manager`: Manager with temporary configuration
- `monitored_worker`: Worker with automatic monitoring and cleanup
- `deadlock_timeout`: Auto-detect deadlocks during test execution
- `thread_pool`: Managed pool of test threads with cleanup

## Result Types

All utilities return strongly-typed results using NamedTuple:

```python
class StateTransitionResult(NamedTuple):
    success: bool
    final_state: WorkerState
    transition_time_ms: float
    timeout_occurred: bool
    error_message: Optional[str] = None

class RaceConditionResult(NamedTuple):
    race_occurred: bool
    winner_thread: Optional[threading.Thread]
    participants: int
    setup_time_ms: float
    race_duration_ms: float
    violations_detected: List[str] = field(default_factory=list)

class DeadlockAnalysisResult(NamedTuple):
    deadlock_detected: bool
    involved_threads: List[threading.Thread]
    lock_graph: Dict[str, List[str]]
    cycles: List[List[str]]
    analysis_time_ms: float
    stack_traces: Dict[int, List[str]] = field(default_factory=dict)

class PerformanceResult(NamedTuple):
    operation_name: str
    duration_ms: float
    iterations: int
    avg_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    std_deviation_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
```

## Usage Examples

### Testing Worker State Transitions

```python
def test_worker_state_transition(monitored_worker):
    # Start worker
    monitored_worker.start()
    
    # Wait for RUNNING state
    result = ThreadingTestHelpers.wait_for_worker_state(
        monitored_worker, WorkerState.RUNNING, timeout_ms=1000
    )
    
    assert result.success
    assert result.final_state == WorkerState.RUNNING
    assert result.transition_time_ms < 1000
```

### Testing Race Conditions

```python
def test_concurrent_stop_requests(workers):
    # Create race between multiple stop requests
    result = RaceConditionFactory.create_state_race(
        workers, WorkerState.STOPPED, timeout_ms=2000
    )
    
    assert result.participants == len(workers)
    assert result.race_duration_ms < 1000
    # Verify thread safety - no violations should occur
    assert len(result.violations_detected) == 0
```

### Testing Deadlock Detection

```python
def test_deadlock_detection():
    # Analyze current threads for deadlocks
    analysis = DeadlockDetector.detect_deadlock(timeout_ms=3000)
    
    # Should not detect deadlocks in normal operation
    assert not analysis.deadlock_detected
    assert len(analysis.cycles) == 0
    assert analysis.analysis_time_ms < 3000
```

### Performance Benchmarking

```python
def test_worker_creation_performance():
    def worker_factory():
        return LauncherWorker("perf_test", "echo hello")
    
    result = PerformanceMetrics.measure_thread_creation(
        worker_factory, iterations=10
    )
    
    # Verify reasonable performance
    assert result.avg_duration_ms < 100  # Less than 100ms average
    assert result.std_deviation_ms < result.avg_duration_ms * 0.5
```

### Using Context Managers

```python
def test_temporary_worker():
    with temporary_worker(LauncherWorker, "temp", "echo test") as worker:
        worker.start()
        
        result = ThreadingTestHelpers.wait_for_worker_state(
            worker, WorkerState.RUNNING, timeout_ms=1000
        )
        assert result.success
    # Worker is automatically cleaned up
```

### Thread Safety Monitoring

```python
def test_thread_safety():
    with thread_safety_monitor(["_active_processes"]) as violations:
        # Perform operations that should be thread-safe
        manager.get_active_process_count()
        manager.execute_launcher("test")
    
    # Verify no thread safety violations
    assert len(violations) == 0
```

## Integration with Existing Tests

The utilities integrate seamlessly with existing test patterns:

```python
def test_launcher_manager_concurrency(isolated_launcher_manager, qtbot):
    manager = isolated_launcher_manager
    
    # Use existing patterns
    launcher_id = manager.create_launcher(
        name="Test Launcher",
        command="echo 'test'"
    )
    
    # Add threading utilities
    operations = [
        lambda: manager.get_launcher(launcher_id),
        lambda: manager.list_launchers(),
        lambda: manager.get_active_process_count(),
    ]
    
    result = RaceConditionFactory.create_resource_race(
        operations, "launcher_manager"
    )
    
    # Verify thread safety
    assert len(result.violations_detected) == 0
```

## Best Practices

1. **Use Type Annotations**: All utilities are fully typed - leverage this for better IDE support
2. **Check Results**: Always check result objects for success/failure status
3. **Set Appropriate Timeouts**: Use reasonable timeouts based on expected operation duration
4. **Clean Up Resources**: Use fixtures and context managers for automatic cleanup
5. **Monitor Performance**: Use performance utilities to detect regressions
6. **Test Real Scenarios**: Create tests that mirror actual usage patterns

## Performance Considerations

- **Efficient Polling**: Default poll intervals are optimized for responsive testing
- **Minimal Overhead**: Utilities add minimal overhead to test execution
- **Resource Cleanup**: Automatic cleanup prevents resource leaks
- **Timeout Management**: Configurable timeouts prevent test hangs

## Type Safety

All utilities are compatible with basedpyright and include:

- **Comprehensive Type Hints**: Full typing for all parameters and returns
- **Protocol Interfaces**: Duck-typed interfaces for flexibility
- **Generic Support**: TypeVar usage for type-safe generic operations
- **Union Types**: Python 3.8 compatible Union syntax
- **NamedTuple Results**: Immutable, type-safe result objects

## Error Handling

The utilities include comprehensive error handling:

- **Custom Exceptions**: Specific exception types for different error conditions
- **Graceful Degradation**: Operations continue where possible on partial failures
- **Detailed Error Messages**: Informative error messages for debugging
- **Resource Cleanup**: Guaranteed cleanup even on exceptions

## Running Tests

```bash
# Run all threading tests
python run_tests.py tests/threading/

# Run specific test file
python run_tests.py tests/threading/test_threading_utilities_example.py

# Run with coverage
python run_tests.py tests/threading/ --cov

# Type check the utilities
source venv/bin/activate
basedpyright tests/threading/
```

## Contributing

When adding new threading test utilities:

1. Maintain full type safety with basedpyright
2. Follow existing naming conventions
3. Include comprehensive docstrings with examples
4. Add corresponding tests in the example file
5. Update this README with new functionality

## Troubleshooting

### Common Issues

**TimeoutError during tests**:
- Increase timeout values for slow operations
- Check for actual deadlocks using DeadlockDetector
- Verify worker lifecycle management

**Type checking errors**:
- Ensure Python 3.8 compatible annotations (Union vs |)
- Check import statements for circular dependencies
- Verify Protocol implementations match expected interfaces

**Resource leaks**:
- Use provided fixtures and context managers
- Ensure worker cleanup in test teardown
- Monitor resource usage with performance utilities

**Race condition tests not triggering races**:
- Adjust timing parameters (start_delay_ms, etc.)
- Use barriers for more precise synchronization
- Consider system load impact on timing

For additional help, see the example test file or existing threading tests in the project.