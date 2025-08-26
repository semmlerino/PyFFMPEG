# Test Refactoring Guide: From Mocks to Behavior Testing

## Overview

This guide demonstrates how to refactor tests from mock-heavy anti-patterns to behavior-focused testing following the UNIFIED_TESTING_GUIDE principles.

## Anti-Patterns to Avoid

### ❌ WRONG: Excessive Mocking
```python
# DON'T DO THIS - Testing implementation details
@patch('module.subprocess.Popen')
@patch('module.os.chdir')  
@patch('module.json.load')
def test_something(mock_json, mock_chdir, mock_popen):
    mock_json.return_value = {'data': 'value'}
    manager = Manager()
    manager._internal_method = Mock()
    
    result = manager.do_something()
    
    # WRONG: Testing that methods were called
    mock_json.assert_called_once()
    mock_chdir.assert_called_with('/some/path')
    manager._internal_method.assert_called()
```

### ❌ WRONG: Mocking Internal Dependencies
```python
# DON'T DO THIS - Mocking internal components
def test_launcher():
    manager = LauncherManager()
    manager._validator = Mock(return_value=True)
    manager._cache = Mock()
    manager._worker_pool = Mock()
    
    # This doesn't test if the code actually works!
```

### ❌ WRONG: Testing Implementation Details
```python
# DON'T DO THIS - Testing HOW, not WHAT
def test_variable_substitution():
    manager = Manager()
    manager._substitute_method = Mock(return_value="result")
    
    result = manager.process("input")
    
    # WRONG: Testing internal method was called
    manager._substitute_method.assert_called_with("input")
```

## Best Practices to Follow

### ✅ CORRECT: Test Doubles at System Boundaries Only
```python
class ProcessDouble:
    """Test double for subprocess.Popen - at SYSTEM BOUNDARY."""
    
    def __init__(self, command: str, return_code: int = 0):
        self.command = command
        self.return_code = return_code
        self._running = True
        
    def poll(self) -> Optional[int]:
        if not self._running:
            return self.return_code
        return None
        
    def terminate(self):
        self._running = False

def test_launcher_execution(qtbot):
    # Use REAL components
    manager = LauncherManager()
    
    # Mock ONLY at system boundary
    with patch('subprocess.Popen', return_value=ProcessDouble("cmd")):
        result = manager.execute("test_command")
    
    # Test BEHAVIOR
    assert result == True
```

### ✅ CORRECT: Test Through State Changes
```python
def test_launcher_lifecycle(qtbot):
    """Test complete lifecycle through state changes."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Use REAL manager with temp directory
        manager = LauncherManager(temp_dir)
        
        # CREATE: Test state after creation
        launcher_id = manager.create_launcher("Test", "echo test")
        assert launcher_id is not None
        assert len(manager.list_launchers()) == 1
        
        # UPDATE: Test state after update
        manager.update_launcher(launcher_id, name="Updated")
        launcher = manager.get_launcher(launcher_id)
        assert launcher.name == "Updated"
        
        # DELETE: Test state after deletion
        manager.delete_launcher(launcher_id)
        assert len(manager.list_launchers()) == 0
```

### ✅ CORRECT: Test Through Signal Emissions
```python
def test_signal_emissions(qtbot):
    """Test behavior through Qt signals."""
    manager = LauncherManager()
    
    # Use QSignalSpy to verify behavior
    started_spy = QSignalSpy(manager.execution_started)
    finished_spy = QSignalSpy(manager.execution_finished)
    error_spy = QSignalSpy(manager.execution_error)
    
    # Execute action
    with patch('subprocess.Popen', side_effect=FileNotFoundError()):
        result = manager.execute_launcher("test")
    
    # Test BEHAVIOR through signals
    assert result == False
    assert error_spy.count() == 1
    assert "not found" in error_spy.at(0)[1].lower()
```

## Refactoring Process

### Step 1: Identify What to Test
Instead of testing implementation details, identify the **behavior** and **outcomes**:
- What should happen when this method is called?
- What state changes occur?
- What signals are emitted?
- What errors are handled?

### Step 2: Remove Internal Mocks
Replace mocked internal components with real ones:
```python
# BEFORE
manager = Manager()
manager._cache = Mock()
manager._validator = Mock(return_value=True)

# AFTER
manager = Manager()  # Use real cache and validator
```

### Step 3: Mock Only System Boundaries
Identify actual system boundaries:
- `subprocess.Popen` - process execution
- `open()` - file I/O (or use temp files)
- `requests.get()` - network calls
- `time.sleep()` - time delays

### Step 4: Use Test Doubles with Realistic Behavior
```python
class NetworkDouble:
    """Realistic network behavior for testing."""
    
    def __init__(self):
        self.responses = {}
        self.call_count = 0
        
    def get(self, url: str):
        self.call_count += 1
        if url in self.responses:
            return self.responses[url]
        raise ConnectionError(f"No response configured for {url}")
        
    def set_response(self, url: str, response: dict):
        self.responses[url] = response
```

### Step 5: Test Error Recovery
```python
def test_error_recovery(qtbot):
    """Test that system recovers from errors."""
    manager = LauncherManager()
    
    # Cause an error
    with patch('subprocess.Popen', side_effect=OSError("Failed")):
        result1 = manager.execute("cmd1")
    
    assert result1 == False
    
    # Test recovery - manager still works
    with patch('subprocess.Popen', return_value=ProcessDouble("cmd2")):
        result2 = manager.execute("cmd2")
    
    assert result2 == True  # Recovered and working
```

## Practical Refactoring Example

### Original Test (Anti-pattern)
```python
@patch('launcher_manager.subprocess.Popen')
@patch('launcher_manager.LauncherWorker')
@patch.object(LauncherManager, '_validate_launcher')
@patch.object(LauncherManager, '_substitute_variables')
def test_execute_launcher(mock_sub, mock_validate, mock_worker, mock_popen):
    """Heavy mocking - doesn't test if code actually works."""
    mock_validate.return_value = True
    mock_sub.return_value = "substituted command"
    mock_worker_instance = Mock()
    mock_worker.return_value = mock_worker_instance
    
    manager = LauncherManager()
    manager.execute_launcher("test")
    
    # Testing implementation details
    mock_validate.assert_called_once_with("test")
    mock_sub.assert_called_once()
    mock_worker.assert_called_once()
    mock_worker_instance.start.assert_called_once()
```

### Refactored Test (Best Practice)
```python
def test_execute_launcher_behavior(qtbot):
    """Test actual behavior with minimal mocking."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Real manager
        manager = LauncherManager(temp_dir)
        
        # Create real launcher
        launcher_id = manager.create_launcher(
            name="Test App",
            command="echo $shot",
            description="Test launcher"
        )
        
        # Set up signal monitoring
        started_spy = QSignalSpy(manager.execution_started)
        finished_spy = QSignalSpy(manager.execution_finished)
        
        # Create shot context
        shot = Shot("show", "seq", "shot001", temp_dir)
        
        # Mock only subprocess at system boundary
        executed_commands = []
        
        def capture_execution(*args, **kwargs):
            executed_commands.append(args[0])
            return ProcessDouble("echo", return_code=0)
        
        with patch('subprocess.Popen', side_effect=capture_execution):
            result = manager.execute_in_shot_context(launcher_id, shot)
        
        # Test BEHAVIOR
        assert result == True
        assert started_spy.count() == 1
        assert finished_spy.count() == 1
        
        # Verify variable substitution happened (not HOW)
        assert len(executed_commands) == 1
        command = ' '.join(executed_commands[0])
        assert "shot001" in command  # Variable was substituted
        assert "$shot" not in command  # Template was replaced
```

## Common Refactoring Patterns

### Pattern 1: File I/O Testing
```python
# BEFORE: Mocking file operations
@patch('builtins.open')
@patch('json.load')
def test_load_config(mock_json, mock_open):
    mock_json.return_value = {'key': 'value'}
    # Not testing actual file I/O

# AFTER: Real file I/O with temp directory
def test_load_config():
    with tempfile.TemporaryDirectory() as temp_dir:
        config_file = Path(temp_dir) / "config.json"
        config_file.write_text('{"key": "value"}')
        
        manager = Manager(temp_dir)
        config = manager.load_config()
        
        assert config['key'] == 'value'
```

### Pattern 2: Process Execution Testing
```python
# BEFORE: Mock everything
@patch('subprocess.run')
@patch('subprocess.Popen')
def test_process(mock_popen, mock_run):
    # Too many mocks, fragile test

# AFTER: Test double at boundary
def test_process():
    process = ProcessDouble("cmd", return_code=0)
    
    with patch('subprocess.Popen', return_value=process):
        result = execute_command("cmd")
    
    assert result.success == True
    assert process._terminated == False  # Graceful completion
```

### Pattern 3: Threading Testing
```python
# BEFORE: Mock thread internals
@patch.object(QThread, 'start')
@patch.object(QThread, 'wait')
def test_threading(mock_wait, mock_start):
    # Doesn't test actual threading behavior

# AFTER: Test actual thread behavior
def test_threading(qtbot):
    worker = Worker()
    
    with qtbot.waitSignal(worker.finished, timeout=1000):
        worker.start()
    
    assert worker.result is not None
    assert worker.state == WorkerState.FINISHED
```

## Benefits of Refactored Tests

1. **More Reliable**: Test actual behavior, not mocked responses
2. **Less Fragile**: Don't break when implementation changes
3. **Better Coverage**: Catch real integration issues
4. **Clearer Intent**: Obviously testing behavior, not internals
5. **Easier Maintenance**: Fewer mocks to maintain
6. **Real Confidence**: Know the code actually works

## Summary

The key to successful test refactoring is:
1. **Test behavior, not implementation**
2. **Use real components where possible**
3. **Mock only at system boundaries**
4. **Verify through state changes and signals**
5. **Test error recovery and edge cases**

Following these principles results in tests that are more valuable, maintainable, and give real confidence that the code works correctly.