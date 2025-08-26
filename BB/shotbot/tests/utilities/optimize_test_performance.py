#!/usr/bin/env python3
"""Test performance optimization script.

This script identifies and fixes performance issues in the test suite:
1. Replaces time.sleep() with proper synchronization
2. Reduces excessive timeout values
3. Identifies slow tests without markers
4. Removes unnecessary waits
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict

def find_performance_issues(test_dir: Path) -> Dict[str, List[Tuple[int, str]]]:
    """Find performance issues in test files."""
    issues = {
        'time_sleep': [],
        'excessive_timeout': [],
        'unnecessary_wait': [],
        'missing_slow_marker': []
    }
    
    for test_file in test_dir.rglob('test_*.py'):
        if '__pycache__' in str(test_file):
            continue
            
        content = test_file.read_text()
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Check for time.sleep
            if re.search(r'time\.sleep\((?!0\.0[01])', line):  # Allow tiny sleeps
                issues['time_sleep'].append((i, str(test_file)))
            
            # Check for excessive timeouts (>2000ms)
            timeout_match = re.search(r'timeout=(\d+)', line)
            if timeout_match and int(timeout_match.group(1)) > 2000:
                issues['excessive_timeout'].append((i, str(test_file)))
            
            # Check for unnecessary waits
            if 'qtbot.wait(' in line and not 'waitSignal' in line:
                issues['unnecessary_wait'].append((i, str(test_file)))
            
            # Check for slow operations without marker
            if any(slow_op in line for slow_op in ['glob.glob', 'os.walk', 'Path().rglob']):
                # Check if test has @pytest.mark.slow
                func_start = max(0, i - 10)
                func_lines = '\n'.join(lines[func_start:i])
                if '@pytest.mark.slow' not in func_lines:
                    issues['missing_slow_marker'].append((i, str(test_file)))
    
    return issues

def generate_fixes(issues: Dict[str, List[Tuple[int, str]]]) -> str:
    """Generate fix recommendations."""
    fixes = []
    
    # Group by file
    by_file = {}
    for issue_type, locations in issues.items():
        for line_num, file_path in locations:
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append((line_num, issue_type))
    
    for file_path, file_issues in by_file.items():
        fixes.append(f"\n## {Path(file_path).name}")
        file_issues.sort(key=lambda x: x[0])  # Sort by line number
        
        for line_num, issue_type in file_issues:
            if issue_type == 'time_sleep':
                fixes.append(f"  - Line {line_num}: Replace time.sleep() with qtbot.wait() or signal wait")
            elif issue_type == 'excessive_timeout':
                fixes.append(f"  - Line {line_num}: Reduce timeout to 1000ms or less")
            elif issue_type == 'unnecessary_wait':
                fixes.append(f"  - Line {line_num}: Use waitSignal() or remove if not needed")
            elif issue_type == 'missing_slow_marker':
                fixes.append(f"  - Line {line_num}: Add @pytest.mark.slow to test function")
    
    return '\n'.join(fixes)

def create_performance_config() -> str:
    """Create pytest configuration for performance."""
    return """# pytest.ini performance configuration

[tool:pytest]
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    fast: marks tests as fast (select with '-m fast')
    unit: unit tests (should be fast)
    integration: integration tests (may be slower)
    qt: tests requiring Qt event loop

# Timeout for all tests (milliseconds)
qt_default_raising = true
qt_wait_signal_raising = true

# Run configuration for CI/local
addopts = 
    --strict-markers
    -ra
    --tb=short
    --maxfail=5
    
# Parallel execution
# -n auto  # Uncomment for parallel execution

testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
"""

def create_fast_test_runner() -> str:
    """Create a fast test runner script."""
    return '''#!/usr/bin/env python3
"""Fast test runner - runs only fast tests and skips slow ones."""

import subprocess
import sys
import time

def run_fast_tests():
    """Run only fast tests."""
    start = time.time()
    
    # Run tests excluding slow markers
    cmd = [
        sys.executable, '-m', 'pytest',
        '-m', 'not slow',  # Skip slow tests
        '--tb=short',      # Short traceback
        '--maxfail=10',    # Stop after 10 failures
        '-q',              # Quiet output
        'tests/'
    ]
    
    result = subprocess.run(cmd)
    
    elapsed = time.time() - start
    print(f"\\n⏱️  Fast tests completed in {elapsed:.1f} seconds")
    
    return result.returncode

if __name__ == '__main__':
    sys.exit(run_fast_tests())
'''

def main():
    """Main function."""
    test_dir = Path('tests')
    
    print("🔍 Analyzing test performance issues...")
    issues = find_performance_issues(test_dir)
    
    # Count total issues
    total = sum(len(v) for v in issues.values())
    
    print(f"\n📊 Found {total} performance issues:")
    print(f"  - time.sleep() calls: {len(issues['time_sleep'])}")
    print(f"  - Excessive timeouts: {len(issues['excessive_timeout'])}")
    print(f"  - Unnecessary waits: {len(issues['unnecessary_wait'])}")
    print(f"  - Missing slow markers: {len(issues['missing_slow_marker'])}")
    
    # Generate report
    fixes = generate_fixes(issues)
    
    # Write report
    report_path = Path('TEST_PERFORMANCE_REPORT.md')
    with open(report_path, 'w') as f:
        f.write("# Test Performance Optimization Report\n")
        f.write(f"\nTotal issues found: {total}\n")
        f.write("\n## Issues by Type\n")
        f.write(f"- time.sleep() calls: {len(issues['time_sleep'])}\n")
        f.write(f"- Excessive timeouts (>2000ms): {len(issues['excessive_timeout'])}\n")
        f.write(f"- Unnecessary waits: {len(issues['unnecessary_wait'])}\n")
        f.write(f"- Missing @pytest.mark.slow: {len(issues['missing_slow_marker'])}\n")
        f.write("\n## Recommended Fixes by File\n")
        f.write(fixes)
        f.write("\n\n## Quick Wins\n")
        f.write("1. Replace all time.sleep() with proper synchronization\n")
        f.write("2. Reduce all timeouts to 1000ms or less\n")
        f.write("3. Mark slow tests with @pytest.mark.slow\n")
        f.write("4. Use -m 'not slow' to skip slow tests during development\n")
    
    print(f"\n✅ Report written to {report_path}")
    
    # Create fast runner script
    runner_path = Path('run_fast_tests.py')
    with open(runner_path, 'w') as f:
        f.write(create_fast_test_runner())
    runner_path.chmod(0o755)
    
    print(f"✅ Fast test runner created: {runner_path}")
    
    # Create optimized pytest.ini
    config_path = Path('pytest_optimized.ini')
    with open(config_path, 'w') as f:
        f.write(create_performance_config())
    
    print(f"✅ Optimized config created: {config_path}")
    
    print("\n🚀 Next steps:")
    print("  1. Review TEST_PERFORMANCE_REPORT.md")
    print("  2. Run ./run_fast_tests.py for quick feedback")
    print("  3. Apply fixes from the report")
    print("  4. Use pytest -m 'not slow' during development")

if __name__ == '__main__':
    main()