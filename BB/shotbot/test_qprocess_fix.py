#!/usr/bin/env python3
"""Test script to verify QProcess threading fix."""

import logging
import sys
import time

from PySide6.QtCore import QCoreApplication, QTimer

from qprocess_manager_fixed import QProcessManager

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_simple_command():
    """Test a simple echo command."""
    app = QCoreApplication(sys.argv)
    
    # Create process manager
    manager = QProcessManager()
    
    # Track test results
    test_results = {
        'started': False,
        'finished': False,
        'output': [],
        'exit_code': None
    }
    
    def on_started(process_id, info):
        logger.info(f"Process {process_id} started")
        test_results['started'] = True
    
    def on_finished(process_id, info):
        logger.info(f"Process {process_id} finished with code {info.exit_code}")
        test_results['finished'] = True
        test_results['exit_code'] = info.exit_code
        
        # Quit the app after process finishes
        QTimer.singleShot(100, app.quit)
    
    def on_output(process_id, line):
        logger.info(f"Output: {line}")
        test_results['output'].append(line)
    
    # Connect signals
    manager.process_started.connect(on_started)
    manager.process_finished.connect(on_finished)
    manager.process_output.connect(on_output)
    
    # Execute simple command
    logger.info("Starting test: echo 'Hello from QProcess'")
    process_id = manager.execute(
        command="echo",
        arguments=["Hello from QProcess"],
        capture_output=True,
        timeout_ms=5000
    )
    
    if not process_id:
        logger.error("Failed to start process")
        sys.exit(1)
    
    # Set a timeout for the test
    QTimer.singleShot(10000, lambda: (
        logger.error("Test timeout!"),
        app.quit()
    ))
    
    # Run event loop
    app.exec()
    
    # Verify results
    logger.info("\n=== Test Results ===")
    logger.info(f"Started: {test_results['started']}")
    logger.info(f"Finished: {test_results['finished']}")
    logger.info(f"Exit code: {test_results['exit_code']}")
    logger.info(f"Output: {test_results['output']}")
    
    # Check if test passed
    if (test_results['started'] and 
        test_results['finished'] and 
        test_results['exit_code'] == 0 and
        'Hello from QProcess' in ' '.join(test_results['output'])):
        logger.info("✅ TEST PASSED!")
        return 0
    else:
        logger.error("❌ TEST FAILED!")
        return 1


def test_longer_running_process():
    """Test a process that runs for a few seconds."""
    app = QCoreApplication(sys.argv)
    
    manager = QProcessManager()
    
    test_results = {
        'started': False,
        'finished': False,
        'duration': 0
    }
    
    start_time = time.time()
    
    def on_started(process_id, info):
        logger.info(f"Long process {process_id} started")
        test_results['started'] = True
    
    def on_finished(process_id, info):
        test_results['duration'] = time.time() - start_time
        logger.info(f"Long process finished after {test_results['duration']:.2f} seconds")
        test_results['finished'] = True
        QTimer.singleShot(100, app.quit)
    
    manager.process_started.connect(on_started)
    manager.process_finished.connect(on_finished)
    
    # Execute a command that takes 2 seconds
    logger.info("Starting test: sleep 2")
    process_id = manager.execute_shell(
        command="sleep 2 && echo 'Done sleeping'",
        capture_output=True,
        timeout_ms=5000
    )
    
    if not process_id:
        logger.error("Failed to start long process")
        sys.exit(1)
    
    # Set test timeout
    QTimer.singleShot(10000, lambda: (
        logger.error("Long test timeout!"),
        app.quit()
    ))
    
    app.exec()
    
    # Verify results
    logger.info("\n=== Long Process Test Results ===")
    logger.info(f"Started: {test_results['started']}")
    logger.info(f"Finished: {test_results['finished']}")
    logger.info(f"Duration: {test_results['duration']:.2f}s")
    
    if (test_results['started'] and 
        test_results['finished'] and 
        1.5 < test_results['duration'] < 3.0):
        logger.info("✅ LONG PROCESS TEST PASSED!")
        return 0
    else:
        logger.error("❌ LONG PROCESS TEST FAILED!")
        return 1


def test_timeout():
    """Test that timeout works correctly."""
    app = QCoreApplication(sys.argv)
    
    manager = QProcessManager()
    
    test_results = {
        'started': False,
        'finished': False,
        'timed_out': False
    }
    
    def on_started(process_id, info):
        logger.info("Timeout test process started")
        test_results['started'] = True
    
    def on_finished(process_id, info):
        logger.info("Timeout test process finished")
        test_results['finished'] = True
        # Check if it was terminated (non-zero exit)
        if info.exit_code != 0:
            test_results['timed_out'] = True
        QTimer.singleShot(100, app.quit)
    
    manager.process_started.connect(on_started)
    manager.process_finished.connect(on_finished)
    
    # Execute a command that would take 10 seconds but timeout at 2 seconds
    logger.info("Starting timeout test: sleep 10 with 2s timeout")
    process_id = manager.execute_shell(
        command="sleep 10",
        timeout_ms=2000  # 2 second timeout
    )
    
    if not process_id:
        logger.error("Failed to start timeout test")
        sys.exit(1)
    
    # Set test timeout
    QTimer.singleShot(5000, lambda: (
        logger.info("Test completed"),
        app.quit()
    ))
    
    app.exec()
    
    # Verify results
    logger.info("\n=== Timeout Test Results ===")
    logger.info(f"Started: {test_results['started']}")
    logger.info(f"Finished: {test_results['finished']}")
    logger.info(f"Timed out: {test_results['timed_out']}")
    
    if test_results['started'] and test_results['timed_out']:
        logger.info("✅ TIMEOUT TEST PASSED!")
        return 0
    else:
        logger.error("❌ TIMEOUT TEST FAILED!")
        return 1


def run_single_test():
    """Run a single test specified by command line argument."""
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name == "simple":
            return test_simple_command()
        elif test_name == "long":
            return test_longer_running_process()
        elif test_name == "timeout":
            return test_timeout()
        else:
            logger.error(f"Unknown test: {test_name}")
            return 1
    else:
        # Run just the simple test by default
        return test_simple_command()


if __name__ == "__main__":
    import subprocess
    
    # Check if running a single test
    if len(sys.argv) > 1:
        sys.exit(run_single_test())
    
    # Otherwise run all tests
    logger.info("=" * 60)
    logger.info("Testing QProcess Threading Fix")
    logger.info("=" * 60)
    
    # Run tests in separate processes to avoid QCoreApplication conflicts
    results = []
    
    tests = [
        ("Simple Command", "simple"),
        ("Longer Process", "long"),
        ("Timeout", "timeout")
    ]
    
    for test_name, test_arg in tests:
        logger.info(f"\n📝 Running Test: {test_name}")
        
        # Run test in subprocess
        result = subprocess.run(
            [sys.executable, __file__, test_arg],
            capture_output=False,
            text=True
        )
        
        passed = result.returncode == 0
        results.append((test_name, passed))
        
        if passed:
            logger.info(f"✅ {test_name} test passed")
        else:
            logger.error(f"❌ {test_name} test failed")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        logger.info("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        logger.error("\n❌ SOME TESTS FAILED!")
        sys.exit(1)