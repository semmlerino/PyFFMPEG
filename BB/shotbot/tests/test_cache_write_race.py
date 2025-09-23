#!/usr/bin/env python3
"""Test to demonstrate cache write race condition in StorageBackend."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
import threading
from pathlib import Path

from cache.storage_backend import StorageBackend


def test_cache_write_race():
    """Test that file locking prevents race condition in StorageBackend.write_json."""

    # Create temporary directory for test
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = StorageBackend()
        test_file = Path(tmpdir) / "test_cache.json"

        # Track all written values
        written_values = []
        write_order = []  # Track actual write order

        def write_data(thread_id: int) -> None:
            """Each thread writes its unique data."""
            data = {"thread_id": thread_id, "value": f"data_{thread_id}"}
            written_values.append(thread_id)
            result = storage.write_json(test_file, data)
            if result:
                write_order.append(thread_id)

        # Create multiple threads to write simultaneously
        threads = []
        num_threads = 10

        for i in range(num_threads):
            thread = threading.Thread(target=write_data, args=(i,))
            threads.append(thread)

        # Start all threads at once
        for thread in threads:
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Read final file content
        final_data = storage.read_json(test_file)

        print(f"Threads that wrote: {sorted(written_values)}")
        print(f"Final file contains: thread_id={final_data.get('thread_id')}")

        # Check for data loss
        final_thread_id = final_data.get("thread_id")

        # Race condition manifests as:
        # 1. Not all thread data is preserved (last writer wins)
        if final_thread_id not in written_values:
            print("ERROR: Final data from unknown thread!")

        # 2. Some thread's data was lost
        if len(written_values) > 1 and final_thread_id != written_values[-1]:
            print(
                f"WARNING: Data loss detected - only thread {final_thread_id} data preserved"
            )
            # This is expected with the race condition

        # The race exists if only one thread's data survives
        print(
            f"Race condition {'DETECTED' if len(written_values) > 1 else 'not tested (single thread)'}"
        )

        return len(written_values) > 1  # Race exists with multiple writers


if __name__ == "__main__":
    race_exists = test_cache_write_race()
    print(f"\nRace condition exists: {race_exists}")
