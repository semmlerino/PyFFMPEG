#!/usr/bin/env python3
"""Simple runner script for thread safety validation tests.

This script provides an easy way to run the comprehensive thread safety
validation test suite for the 3DE parallel scanning implementation.

Usage:
    python run_thread_safety_tests.py [--quick] [--performance-only] [--verbose]
    
Options:
    --quick: Run only the most critical thread safety tests (faster execution)
    --performance-only: Run only performance benchmark tests
    --verbose: Enable verbose output with detailed logging
"""

import argparse
import logging
import sys
import unittest
from pathlib import Path

# Ensure we can import from the current directory
sys.path.insert(0, str(Path(__file__).parent))

from test_thread_safety_validation import (
    ThreadSafetyValidationTests, 
    run_validation_tests
)


def run_quick_tests():
    """Run only the most critical thread safety tests for faster validation."""
    print("Running QUICK thread safety validation tests...")
    
    suite = unittest.TestSuite()
    
    # Add only the most critical tests
    critical_tests = [
        'test_threadsafe_progress_tracker',
        'test_cancellation_event_system', 
        'test_threadpool_manager',
        'test_threading_utils_import',
    ]
    
    for test_name in critical_tests:
        suite.addTest(ThreadSafetyValidationTests(test_name))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return len(result.failures) == 0 and len(result.errors) == 0


def run_performance_tests():
    """Run only performance benchmark tests."""
    print("Running PERFORMANCE benchmark tests...")
    
    # Run only the performance test from ThreadSafetyValidationTests
    suite = unittest.TestSuite()
    suite.addTest(ThreadSafetyValidationTests('test_performance_baseline'))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return len(result.failures) == 0 and len(result.errors) == 0


def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(description='Run thread safety validation tests')
    parser.add_argument('--quick', action='store_true',
                       help='Run only critical tests for faster validation')
    parser.add_argument('--performance-only', action='store_true',
                       help='Run only performance benchmark tests')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging output')
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(levelname)s: %(message)s'
        )
    
    success = False
    
    try:
        if args.quick:
            success = run_quick_tests()
        elif args.performance_only:
            success = run_performance_tests()
        else:
            # Run full comprehensive test suite
            success = run_validation_tests()
            
    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Test execution failed with error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
    
    if success:
        print("\n🎉 Thread safety validation PASSED!")
        print("✅ All thread safety fixes are working correctly")
        print("✅ No performance regressions detected")
        return 0
    else:
        print("\n💥 Thread safety validation FAILED!")
        print("❌ Issues detected - see output above for details")
        return 1


if __name__ == "__main__":
    exit(main())