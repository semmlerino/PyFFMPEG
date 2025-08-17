#!/usr/bin/env python3
"""Debug script for diagnosing Shotbot crashes with verbose logging.

This script enables comprehensive debug logging across all critical components
and provides detailed output to help diagnose startup crashes, hangs, and
other issues.

Usage:
    python debug_crash_verbose.py

Or with environment variable:
    SHOTBOT_DEBUG_VERBOSE=1 python shotbot.py
"""

import logging
import os
import sys
import time
from datetime import datetime

# Enable verbose debug mode
os.environ["SHOTBOT_DEBUG_VERBOSE"] = "1"
os.environ["SHOTBOT_DEBUG"] = "1"  # Also enable regular debug mode

# Configure comprehensive logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d [%(levelname)8s] %(name)s:%(lineno)d - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            f"debug_crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        ),
    ],
)

logger = logging.getLogger(__name__)
logger.info("=" * 80)
logger.info("SHOTBOT DEBUG CRASH DIAGNOSTIC")
logger.info("=" * 80)
logger.info(f"Python version: {sys.version}")
logger.info(f"Platform: {sys.platform}")
logger.info(f"PID: {os.getpid()}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(
    f"Environment: SHOTBOT_DEBUG_VERBOSE={os.environ.get('SHOTBOT_DEBUG_VERBOSE')}",
)
logger.info("=" * 80)

# Test 1: ProcessPoolManager initialization
logger.info("\n[TEST 1] Testing ProcessPoolManager initialization...")
try:
    from process_pool_manager import ProcessPoolManager

    logger.info("✓ ProcessPoolManager imported successfully")

    # Get instance (should NOT create sessions yet due to lazy init)
    pm = ProcessPoolManager.get_instance()
    logger.info(f"✓ ProcessPoolManager instance created: {pm}")
    logger.info("  Sessions should NOT be created yet (lazy initialization)")

except Exception as e:
    logger.error(f"✗ ProcessPoolManager initialization failed: {e}")
    import traceback

    logger.error(traceback.format_exc())
    sys.exit(1)

# Test 2: Qt Application initialization
logger.info("\n[TEST 2] Testing Qt Application initialization...")
try:
    from PySide6.QtWidgets import QApplication

    logger.info("✓ PySide6.QtWidgets imported successfully")

    app = QApplication.instance()
    if app is None:
        logger.info("Creating new QApplication instance...")
        app = QApplication(sys.argv)
        logger.info(f"✓ QApplication created: {app}")
    else:
        logger.info(f"✓ QApplication already exists: {app}")

except Exception as e:
    logger.error(f"✗ Qt initialization failed: {e}")
    import traceback

    logger.error(traceback.format_exc())
    sys.exit(1)

# Test 3: First command execution (triggers session creation)
logger.info(
    "\n[TEST 3] Testing first command execution (triggers lazy session creation)...",
)
try:
    logger.info("Executing 'echo test' command...")
    start_time = time.time()
    result = pm.execute_workspace_command("echo test", timeout=5)
    elapsed = time.time() - start_time
    logger.info(f"✓ Command executed in {elapsed:.2f}s")
    logger.info(f"  Result: {result[:100] if result else 'empty'}")

except TimeoutError as e:
    logger.error(f"✗ Command timed out: {e}")
except Exception as e:
    logger.error(f"✗ Command execution failed: {e}")
    import traceback

    logger.error(traceback.format_exc())

# Test 4: ShotModel initialization
logger.info("\n[TEST 4] Testing ShotModel initialization...")
try:
    from shot_model import ShotModel

    logger.info("✓ ShotModel imported successfully")

    # Create without cache loading for testing
    shot_model = ShotModel(load_cache=False)
    logger.info(f"✓ ShotModel created: {shot_model}")

except Exception as e:
    logger.error(f"✗ ShotModel initialization failed: {e}")
    import traceback

    logger.error(traceback.format_exc())

# Test 5: Workspace command through ShotModel
logger.info("\n[TEST 5] Testing workspace command through ShotModel...")
try:
    logger.info("Calling shot_model.refresh_shots()...")
    start_time = time.time()
    result = shot_model.refresh_shots()
    elapsed = time.time() - start_time
    logger.info(f"✓ refresh_shots() completed in {elapsed:.2f}s")
    logger.info(f"  Result: success={result.success}, has_changes={result.has_changes}")
    logger.info(f"  Shots found: {len(shot_model.shots)}")

except Exception as e:
    logger.error(f"✗ refresh_shots() failed: {e}")
    import traceback

    logger.error(traceback.format_exc())

# Test 6: MainWindow initialization (without showing)
logger.info("\n[TEST 6] Testing MainWindow initialization...")
try:
    from main_window import MainWindow

    logger.info("✓ MainWindow imported successfully")

    logger.info("Creating MainWindow instance...")
    window = MainWindow()
    logger.info(f"✓ MainWindow created: {window}")

except Exception as e:
    logger.error(f"✗ MainWindow initialization failed: {e}")
    import traceback

    logger.error(traceback.format_exc())

# Test 7: Performance metrics
logger.info("\n[TEST 7] Checking performance metrics...")
try:
    metrics = pm.get_metrics()
    logger.info("ProcessPoolManager metrics:")
    logger.info(f"  Subprocess calls: {metrics.get('subprocess_calls', 0)}")
    logger.info(f"  Cache hits: {metrics.get('cache_stats', {}).get('hits', 0)}")
    logger.info(f"  Cache misses: {metrics.get('cache_stats', {}).get('misses', 0)}")
    logger.info(
        f"  Average response time: {metrics.get('average_response_ms', 0):.2f}ms",
    )

    # Check session status
    if "sessions" in metrics:
        for pool_type, pool_info in metrics["sessions"].items():
            logger.info(f"  {pool_type} pool: {pool_info.get('pool_size', 0)} sessions")
            for session in pool_info.get("sessions", []):
                logger.info(
                    f"    - {session.get('session_id')}: alive={session.get('alive')}, "
                    f"commands={session.get('commands_executed')}, "
                    f"idle={session.get('idle_seconds', 0):.1f}s",
                )

except Exception as e:
    logger.error(f"✗ Failed to get metrics: {e}")

# Cleanup
logger.info("\n[CLEANUP] Shutting down...")
try:
    if "pm" in locals():
        pm.shutdown()
        logger.info("✓ ProcessPoolManager shut down")

    if "app" in locals():
        app.quit()
        logger.info("✓ QApplication shut down")

except Exception as e:
    logger.warning(f"Cleanup warning: {e}")

logger.info("\n" + "=" * 80)
logger.info("DEBUG CRASH DIAGNOSTIC COMPLETE")
logger.info("=" * 80)
logger.info("Check the log file for detailed output")
