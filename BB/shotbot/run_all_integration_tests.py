#!/usr/bin/env python3
"""Master test runner for all integration tests."""

import subprocess
import sys
import time
from pathlib import Path


def run_test(test_script: str, description: str) -> tuple[bool, str]:
    """Run a single test script and return success status and output."""
    print(f"\n{'='*80}")
    print(f"RUNNING: {description}")
    print(f"Script: {test_script}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            [sys.executable, test_script],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout per test
        )
        
        elapsed = time.time() - start_time
        
        # Print the output
        print(result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        success = result.returncode == 0
        status_msg = f"{'✅ PASSED' if success else '❌ FAILED'} in {elapsed:.2f}s"
        print(f"\n{status_msg}")
        
        return success, status_msg
        
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        status_msg = f"❌ TIMEOUT after {elapsed:.2f}s"
        print(f"\n{status_msg}")
        return False, status_msg
    
    except Exception as e:
        elapsed = time.time() - start_time
        status_msg = f"❌ ERROR: {e} after {elapsed:.2f}s"
        print(f"\n{status_msg}")
        return False, status_msg

def main():
    """Run all integration tests."""
    print("=" * 80)
    print("SHOTBOT INTEGRATION TEST SUITE")
    print("=" * 80)
    print(f"Running from: {Path.cwd()}")
    print(f"Python: {sys.executable}")
    
    # Define all integration tests
    tests = [
        ("test_launcher_integration_standalone.py", "Launcher Integration Tests"),
        ("test_process_pool_integration_standalone.py", "Process Pool Integration Tests"),
        ("test_threede_discovery_integration_standalone.py", "3DE Discovery Integration Tests"),
        ("test_subprocess_fixes_standalone.py", "Subprocess Fixes Integration Tests"),
        ("test_caching_workflow_standalone.py", "Caching Workflow Integration Tests"),
    ]
    
    results = []
    total_start = time.time()
    
    # Check that all test files exist
    missing_tests = []
    for test_script, _ in tests:
        if not Path(test_script).exists():
            missing_tests.append(test_script)
    
    if missing_tests:
        print("❌ MISSING TEST FILES:")
        for missing in missing_tests:
            print(f"  - {missing}")
        return 1
    
    # Run each test
    for test_script, description in tests:
        success, status = run_test(test_script, description)
        results.append((description, success, status))
    
    total_elapsed = time.time() - total_start
    
    # Summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for description, success, status in results:
        status_icon = "✅" if success else "❌"
        print(f"{status_icon} {description}: {status}")
        if success:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"TOTAL RESULTS: {passed} PASSED, {failed} FAILED")
    print(f"TOTAL TIME: {total_elapsed:.2f}s")
    print("=" * 80)
    
    if failed == 0:
        print("🎉 ALL INTEGRATION TESTS PASSED!")
        return 0
    else:
        print(f"💥 {failed} INTEGRATION TESTS FAILED")
        
        # Detailed failure report
        print("\nFAILED TESTS:")
        for description, success, status in results:
            if not success:
                print(f"  - {description}: {status}")
        
        return 1

if __name__ == "__main__":
    sys.exit(main())