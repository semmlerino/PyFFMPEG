#!/usr/bin/env python3
"""Health check for test suite to identify hanging tests."""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple


def run_test_with_timeout(test_path: str, timeout: int = 10) -> Tuple[str, float]:
    """Run a test file with timeout and return status."""
    start = time.time()
    
    # Set environment for headless Qt
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_LOGGING_RULES"] = "*.debug=false"
    
    try:
        result = subprocess.run(
            ["./venv/bin/python", "run_tests.py", test_path, "-q", "--tb=no"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=Path(__file__).parent,
            env=env
        )
        elapsed = time.time() - start
        
        if result.returncode == 0:
            # Check output for pass/fail counts
            output = result.stdout + result.stderr
            if "passed" in output:
                return "PASSED", elapsed
            elif "FAILED" in output or "ERROR" in output:
                return "FAILED", elapsed
            else:
                return "UNKNOWN", elapsed
        else:
            return "FAILED", elapsed
            
    except subprocess.TimeoutExpired:
        return "TIMEOUT", timeout
    except Exception as e:
        return f"ERROR: {e}", 0

def main():
    """Check health of all test files."""
    print("🔍 Test Suite Health Check")
    print("=" * 60)
    
    test_dirs = ["tests/unit", "tests/integration", "tests/advanced", "tests/performance"]
    results: Dict[str, List[Tuple[str, str, float]]] = {}
    
    for test_dir in test_dirs:
        test_path = Path(test_dir)
        if not test_path.exists():
            continue
            
        print(f"\n📁 Checking {test_dir}...")
        dir_results = []
        
        # Find all test files
        test_files = sorted(test_path.glob("test_*.py"))
        
        for test_file in test_files:
            test_name = test_file.name
            print(f"  Testing {test_name}...", end=" ")
            
            status, elapsed = run_test_with_timeout(str(test_file), timeout=10)
            
            if status == "PASSED":
                print(f"✅ {elapsed:.1f}s")
            elif status == "FAILED":
                print(f"❌ {elapsed:.1f}s")
            elif status == "TIMEOUT":
                print("⏰ TIMEOUT")
            else:
                print(f"❓ {status}")
            
            dir_results.append((test_name, status, elapsed))
        
        results[test_dir] = dir_results
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    total_passed = 0
    total_failed = 0
    total_timeout = 0
    total_other = 0
    
    for test_dir, dir_results in results.items():
        passed = sum(1 for _, status, _ in dir_results if status == "PASSED")
        failed = sum(1 for _, status, _ in dir_results if status == "FAILED")
        timeout = sum(1 for _, status, _ in dir_results if status == "TIMEOUT")
        other = len(dir_results) - passed - failed - timeout
        
        total_passed += passed
        total_failed += failed
        total_timeout += timeout
        total_other += other
        
        print(f"\n{test_dir}:")
        print(f"  ✅ Passed: {passed}")
        print(f"  ❌ Failed: {failed}")
        print(f"  ⏰ Timeout: {timeout}")
        if other > 0:
            print(f"  ❓ Other: {other}")
    
    print("\nTOTAL:")
    print(f"  ✅ Passed: {total_passed}")
    print(f"  ❌ Failed: {total_failed}")
    print(f"  ⏰ Timeout: {total_timeout}")
    if total_other > 0:
        print(f"  ❓ Other: {total_other}")
    
    # List timeout tests
    if total_timeout > 0:
        print("\n⚠️  HANGING TESTS:")
        for test_dir, dir_results in results.items():
            for test_name, status, _ in dir_results:
                if status == "TIMEOUT":
                    print(f"  - {test_dir}/{test_name}")
    
    return 0 if (total_failed == 0 and total_timeout == 0) else 1

if __name__ == "__main__":
    sys.exit(main())