#!/usr/bin/env python3
"""Test reliability improvement script.

Identifies and fixes common reliability issues:
1. Race conditions in Qt signal tests
2. File system timing issues
3. Thread synchronization problems
4. Resource cleanup issues
"""

import re
from pathlib import Path
from typing import List, Tuple, Dict

def find_reliability_issues(test_dir: Path) -> Dict[str, List[Tuple[int, str, str]]]:
    """Find reliability issues in test files."""
    issues = {
        'race_conditions': [],
        'resource_leaks': [],
        'thread_issues': [],
        'filesystem_timing': [],
        'signal_timing': []
    }
    
    for test_file in test_dir.rglob('test_*.py'):
        if '__pycache__' in str(test_file):
            continue
            
        content = test_file.read_text()
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Check for race conditions
            if 'emit()' in line and i + 1 < len(lines):
                next_line = lines[i]  # 0-indexed
                if 'assert' in next_line or 'spy' in next_line:
                    issues['race_conditions'].append((
                        i, str(test_file), 
                        "Signal emission followed immediately by assertion"
                    ))
            
            # Check for resource leaks
            if any(create in line for create in ['open(', 'QTimer(', 'QThread(', 'QProcess(']):
                # Check if in a context manager or has cleanup
                if 'with ' not in line:
                    func_end = min(i + 20, len(lines))
                    func_lines = '\n'.join(lines[i:func_end])
                    if not any(cleanup in func_lines for cleanup in ['close()', 'quit()', 'wait()', 'deleteLater()']):
                        issues['resource_leaks'].append((
                            i, str(test_file),
                            "Resource created without cleanup"
                        ))
            
            # Check for thread issues
            if 'QThread' in line or 'threading.Thread' in line:
                func_end = min(i + 10, len(lines))
                func_lines = '\n'.join(lines[i:func_end])
                if '.wait()' not in func_lines and '.join()' not in func_lines:
                    issues['thread_issues'].append((
                        i, str(test_file),
                        "Thread started without wait/join"
                    ))
            
            # Check for filesystem timing issues
            if any(fs_op in line for fs_op in ['mkdir', 'write_text', 'write_bytes', 'unlink']):
                if i + 1 < len(lines):
                    next_line = lines[i]
                    if 'assert' in next_line and 'exists' in next_line:
                        issues['filesystem_timing'].append((
                            i, str(test_file),
                            "Filesystem operation immediately followed by existence check"
                        ))
            
            # Check for signal timing issues
            if 'waitSignal' in line:
                if 'timeout=' not in line or 'timeout=None' in line:
                    issues['signal_timing'].append((
                        i, str(test_file),
                        "waitSignal without explicit timeout"
                    ))
    
    return issues

def generate_fixes(issues: Dict[str, List[Tuple[int, str, str]]]) -> str:
    """Generate fix recommendations."""
    fixes = []
    fixes.append("# Test Reliability Fixes\n")
    
    # Group by issue type
    for issue_type, locations in issues.items():
        if not locations:
            continue
            
        fixes.append(f"\n## {issue_type.replace('_', ' ').title()}\n")
        
        if issue_type == 'race_conditions':
            fixes.append("**Fix:** Use qtbot.waitSignal() or qtbot.wait() between emission and assertion\n")
        elif issue_type == 'resource_leaks':
            fixes.append("**Fix:** Use context managers or ensure cleanup in teardown\n")
        elif issue_type == 'thread_issues':
            fixes.append("**Fix:** Always wait for threads to complete with .wait() or .join()\n")
        elif issue_type == 'filesystem_timing':
            fixes.append("**Fix:** Add small delay or use polling to wait for filesystem operations\n")
        elif issue_type == 'signal_timing':
            fixes.append("**Fix:** Always specify explicit timeout (e.g., timeout=1000)\n")
        
        # List affected files
        files_seen = set()
        for line_num, file_path, description in locations[:10]:  # Show first 10
            file_name = Path(file_path).name
            if file_name not in files_seen:
                fixes.append(f"\n### {file_name}")
                files_seen.add(file_name)
            fixes.append(f"  - Line {line_num}: {description}")
    
    return '\n'.join(fixes)

def create_reliability_fixtures() -> str:
    """Create pytest fixtures for reliable testing."""
    return '''"""Reliability fixtures for consistent test execution."""

import pytest
import tempfile
import shutil
from pathlib import Path
from PySide6.QtCore import QTimer, QThread, QObject
from typing import Generator, List

@pytest.fixture
def reliable_temp_dir():
    """Create a temporary directory that's properly cleaned up."""
    temp_dir = tempfile.mkdtemp(prefix='shotbot_test_')
    temp_path = Path(temp_dir)
    
    yield temp_path
    
    # Cleanup with retry
    for _ in range(3):
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            break
        except:
            QTimer.singleShot(100, lambda: None)  # Small delay

@pytest.fixture
def managed_threads(qtbot):
    """Fixture to track and cleanup threads."""
    threads: List[QThread] = []
    
    def create_thread():
        thread = QThread()
        threads.append(thread)
        return thread
    
    yield create_thread
    
    # Cleanup all threads
    for thread in threads:
        if thread.isRunning():
            thread.quit()
            thread.wait(1000)
            if thread.isRunning():
                thread.terminate()

@pytest.fixture
def signal_waiter(qtbot):
    """Helper for reliable signal waiting."""
    def wait_for_signal(signal, timeout=1000, raising=True):
        """Wait for signal with proper error handling."""
        with qtbot.waitSignal(signal, timeout=timeout, raising=raising) as blocker:
            return blocker
    
    return wait_for_signal

@pytest.fixture(autouse=True)
def cleanup_qt_objects(qtbot):
    """Automatically cleanup Qt objects after each test."""
    yield
    # Process events to handle deleteLater
    qtbot.wait(10)

@pytest.fixture
def stable_filesystem(tmp_path):
    """Filesystem operations with stability checks."""
    class StableFS:
        def write_file(self, path: Path, content: str):
            path.write_text(content)
            # Ensure write is complete
            assert path.exists()
            assert path.read_text() == content
        
        def create_dir(self, path: Path):
            path.mkdir(parents=True, exist_ok=True)
            # Ensure directory is created
            assert path.is_dir()
        
        def remove_file(self, path: Path):
            if path.exists():
                path.unlink()
            # Ensure file is removed
            assert not path.exists()
    
    return StableFS()
'''

def create_reliability_patterns() -> str:
    """Create documentation of reliable test patterns."""
    return '''# Reliable Test Patterns

## 1. Signal Testing Pattern

### ❌ Unreliable
```python
def test_signal_emission():
    obj.some_signal.emit("data")
    assert spy.count() == 1  # Race condition!
```

### ✅ Reliable
```python
def test_signal_emission(qtbot):
    spy = QSignalSpy(obj.some_signal)
    
    with qtbot.waitSignal(obj.some_signal, timeout=1000):
        obj.trigger_action()  # Triggers signal
    
    assert spy.count() == 1
    assert spy.at(0)[0] == "expected_data"
```

## 2. Thread Testing Pattern

### ❌ Unreliable
```python
def test_thread_operation():
    thread = QThread()
    worker = Worker()
    worker.moveToThread(thread)
    thread.start()
    # Thread might not be finished!
```

### ✅ Reliable
```python
def test_thread_operation(qtbot, managed_threads):
    thread = managed_threads()  # Auto-cleanup
    worker = Worker()
    worker.moveToThread(thread)
    
    with qtbot.waitSignal(worker.finished, timeout=2000):
        thread.start()
        QTimer.singleShot(0, worker.process)
    
    thread.quit()
    thread.wait(1000)
```

## 3. Filesystem Testing Pattern

### ❌ Unreliable
```python
def test_file_operations(tmp_path):
    file = tmp_path / "test.txt"
    file.write_text("content")
    assert file.exists()  # Might fail on slow filesystems
```

### ✅ Reliable
```python
def test_file_operations(stable_filesystem, tmp_path):
    file = tmp_path / "test.txt"
    stable_filesystem.write_file(file, "content")
    # write_file ensures the file exists and has correct content
```

## 4. Resource Cleanup Pattern

### ❌ Unreliable
```python
def test_resource():
    timer = QTimer()
    timer.start(100)
    # Timer keeps running after test!
```

### ✅ Reliable
```python
def test_resource(qtbot):
    timer = QTimer()
    qtbot.addWidget(timer)  # Auto cleanup
    timer.start(100)
    
    # Or use context manager
    with closing(resource) as r:
        r.do_something()
```

## 5. Process Testing Pattern

### ❌ Unreliable
```python
def test_process():
    proc = subprocess.Popen(["cmd"])
    # Process might still be running
```

### ✅ Reliable
```python
def test_process():
    proc = subprocess.Popen(["cmd"])
    try:
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(1)
```
'''

def main():
    """Main function."""
    test_dir = Path('tests')
    
    print("🔍 Analyzing test reliability issues...")
    issues = find_reliability_issues(test_dir)
    
    # Count total issues
    total = sum(len(v) for v in issues.values())
    
    print(f"\n📊 Found {total} reliability issues:")
    for issue_type, locations in issues.items():
        if locations:
            print(f"  - {issue_type.replace('_', ' ').title()}: {len(locations)}")
    
    # Generate report
    fixes = generate_fixes(issues)
    
    # Write report
    report_path = Path('TEST_RELIABILITY_REPORT.md')
    with open(report_path, 'w') as f:
        f.write(fixes)
        f.write("\n\n## Summary\n")
        f.write(f"Total reliability issues: {total}\n\n")
        f.write("### Priority Fixes\n")
        f.write("1. Fix race conditions in signal tests\n")
        f.write("2. Add proper thread cleanup\n")
        f.write("3. Fix resource leaks\n")
        f.write("4. Add explicit timeouts to all waitSignal calls\n")
    
    print(f"\n✅ Report written to {report_path}")
    
    # Create fixtures file
    fixtures_path = Path('tests/reliability_fixtures.py')
    with open(fixtures_path, 'w') as f:
        f.write(create_reliability_fixtures())
    
    print(f"✅ Reliability fixtures created: {fixtures_path}")
    
    # Create patterns documentation
    patterns_path = Path('RELIABLE_TEST_PATTERNS.md')
    with open(patterns_path, 'w') as f:
        f.write(create_reliability_patterns())
    
    print(f"✅ Pattern documentation created: {patterns_path}")
    
    print("\n🚀 Next steps:")
    print("  1. Review TEST_RELIABILITY_REPORT.md")
    print("  2. Import fixtures: from tests.reliability_fixtures import *")
    print("  3. Apply patterns from RELIABLE_TEST_PATTERNS.md")
    print("  4. Run tests multiple times to verify reliability")

if __name__ == '__main__':
    main()