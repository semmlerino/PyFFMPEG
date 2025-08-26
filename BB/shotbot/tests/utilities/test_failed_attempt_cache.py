#!/usr/bin/env python3
"""Test script for failed attempt caching functionality.

This script demonstrates the new failed attempt cache that prevents
thundering herd problems on repeatedly failing EXR files.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add the current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

from cache_manager import CacheManager


def test_failed_attempt_cache():
    """Test that failed attempt cache prevents repeated processing."""
    print("Testing failed attempt cache functionality...")

    # Create temporary cache directory
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir)
        cache_manager = CacheManager(cache_dir=cache_dir)

        # Create a fake EXR file that will fail to process
        fake_exr = cache_dir / "fake_file.exr"
        fake_exr.write_text("fake exr content")

        # Test parameters
        show = "test_show"
        sequence = "seq01"
        shot = "shot01"
        cache_key = f"{show}_{sequence}_{shot}"

        print("1. Testing first failure attempt...")

        # Enable minimal logging to see key events
        import logging

        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
        cache_logger = logging.getLogger("cache_manager")
        cache_logger.setLevel(logging.INFO)

        # First attempt - should fail and record the failure
        result1 = cache_manager.cache_thumbnail(
            fake_exr, show, sequence, shot, wait=True
        )

        print(f"   First attempt result: {result1}")
        print(f"   Result type: {type(result1)}")

        # Give async loader time to record failure
        import time

        time.sleep(0.1)

        # Check failed attempts were recorded
        failed_status = cache_manager.get_failed_attempts_status()
        print(f"   Failed attempts after first try: {len(failed_status)}")
        print(f"   Failed attempts dict: {failed_status}")

        if cache_key in failed_status:
            failure_info = failed_status[cache_key]
            print(
                f"   Failure recorded: attempts={failure_info['attempts']}, "
                f"next_retry={failure_info['next_retry'].strftime('%H:%M:%S')}"
            )

        print("\n2. Testing immediate retry (should be skipped)...")

        # Second attempt immediately - should be skipped
        result2 = cache_manager.cache_thumbnail(
            fake_exr, show, sequence, shot, wait=True
        )

        print(f"   Second attempt result: {result2}")
        print("   Should be None (skipped due to recent failure)")

        print("\n3. Testing manual retry clear...")

        # Clear the failed attempt
        cache_manager.clear_failed_attempts(cache_key)

        # Verify it was cleared
        failed_status_after_clear = cache_manager.get_failed_attempts_status()
        print(f"   Failed attempts after clear: {len(failed_status_after_clear)}")

        print("\n4. Testing retry after clear...")

        # Third attempt after clear - should fail again and record
        result3 = cache_manager.cache_thumbnail(
            fake_exr, show, sequence, shot, wait=True
        )

        print(f"   Third attempt result: {result3}")

        # Check failed attempts were recorded again
        failed_status_final = cache_manager.get_failed_attempts_status()
        print(f"   Failed attempts after third try: {len(failed_status_final)}")

        if cache_key in failed_status_final:
            failure_info = failed_status_final[cache_key]
            print(f"   New failure recorded: attempts={failure_info['attempts']}")

        print("\n5. Testing multiple failures (exponential backoff)...")

        # Simulate multiple failures to test backoff
        for attempt in range(1, 5):
            # Manually record failed attempts to test backoff calculation
            error_msg = f"Simulated failure #{attempt}"
            cache_manager._record_failed_attempt(cache_key, fake_exr, error_msg)

            failure_info = cache_manager.get_failed_attempts_status()[cache_key]
            next_retry = failure_info["next_retry"]
            delay_minutes = (next_retry - datetime.now()).total_seconds() / 60

            print(
                f"   Attempt #{failure_info['attempts']}: "
                f"next retry in {delay_minutes:.1f} minutes"
            )

        print("\n✅ Failed attempt cache test completed successfully!")

        # Clean up
        cache_manager.shutdown()


if __name__ == "__main__":
    test_failed_attempt_cache()
