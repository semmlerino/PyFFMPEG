#!/usr/bin/env python3
"""Test script to verify thread cleanup fix without PySide6."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class MockWorker:
    """Mock worker to test zombie thread handling."""

    def __init__(self):
        self._stop_requested = False
        self._zombie = False
        self._thread = None

    def is_zombie(self):
        """Check if thread is a zombie."""
        return self._zombie

    def request_stop(self):
        """Request thread to stop."""
        logger.info("Stop requested")
        self._stop_requested = True

    def should_stop(self):
        """Check if thread should stop."""
        return self._stop_requested

    def run_parallel_task(self):
        """Simulate parallel scanning with ThreadPoolExecutor."""
        logger.info("Starting parallel task")

        def cancel_flag():
            return self.should_stop()

        with ThreadPoolExecutor(max_workers=3) as executor:
            # Submit some work
            futures = []
            for i in range(10):
                future = executor.submit(self.process_item, i)
                futures.append(future)

            # Process results
            try:
                for future in futures:
                    if cancel_flag():
                        logger.info("Cancelling remaining futures")
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                    try:
                        result = future.result(timeout=0.1)
                        logger.debug(f"Got result: {result}")
                    except:
                        if cancel_flag():
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        result = future.result()
            except Exception as e:
                logger.error(f"Error: {e}")
                for f in futures:
                    if not f.done():
                        f.cancel()
                executor.shutdown(wait=False, cancel_futures=True)

        logger.info("Parallel task completed")

    def process_item(self, item):
        """Process a single item."""
        for i in range(5):
            if self.should_stop():
                logger.debug(f"Item {item} cancelled at step {i}")
                return None
            time.sleep(0.1)
        return f"Processed {item}"

    def run(self):
        """Main thread execution."""
        try:
            self.run_parallel_task()
        finally:
            logger.info("Worker thread exiting")

    def start(self):
        """Start the worker thread."""
        self._thread = threading.Thread(target=self.run)
        self._thread.start()

    def stop_with_timeout(self, timeout=2):
        """Try to stop thread with timeout."""
        self.request_stop()
        self._thread.join(timeout)

        if self._thread.is_alive():
            logger.warning("Thread still running after timeout - marking as zombie")
            self._zombie = True
            return False
        else:
            logger.info("Thread stopped successfully")
            return True

def test_cleanup():
    """Test the thread cleanup behavior."""
    logger.info("=== Testing thread cleanup ===")

    worker = MockWorker()
    worker.start()

    # Let it run briefly
    time.sleep(0.5)

    # Try to stop it
    logger.info("Requesting shutdown...")
    stopped = worker.stop_with_timeout(timeout=2)

    if not stopped and worker.is_zombie():
        logger.warning("Worker is a zombie - NOT deleting to prevent crash")
        # In real code, we would NOT call deleteLater() here
    else:
        logger.info("Worker stopped cleanly - safe to delete")
        # In real code, we would call deleteLater() here

    logger.info("=== Test complete ===")

if __name__ == "__main__":
    test_cleanup()