#!/usr/bin/env python3
"""Test to verify file locking prevents corruption in StorageBackend."""

# Standard library imports
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Standard library imports
import tempfile
import threading
from pathlib import Path

# Local application imports
from cache.storage_backend import StorageBackend


def test_file_locking_prevents_corruption() -> bool:
    """Test that file locking prevents data corruption (not data loss).

    File locking ensures:
    1. No corrupted/partial JSON from concurrent writes
    2. Writes are serialized (one at a time)
    3. Each write is complete and valid

    Note: Last writer still wins - that's expected behavior.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = StorageBackend()
        test_file = Path(tmpdir) / "test_cache.json"

        corruption_detected = False
        successful_writes = []
        failed_reads = []

        def write_large_data(thread_id: int) -> None:
            """Write large data to increase chance of corruption without locking."""
            # Large data structure to increase write time
            data = {
                "thread_id": thread_id,
                "large_array": [f"item_{i}_thread_{thread_id}" for i in range(1000)],
                "nested": {"level1": {"level2": {"value": f"deep_data_{thread_id}"}}},
            }

            result = storage.write_json(test_file, data)
            if result:
                successful_writes.append(thread_id)

                # Immediately try to read back
                read_data = storage.read_json(test_file)
                if read_data is None:
                    failed_reads.append(thread_id)
                    print(f"Thread {thread_id}: Read failed after write!")
                elif not isinstance(read_data, dict):
                    print(f"Thread {thread_id}: Corrupted data - not a dict!")
                    global corruption_detected
                    corruption_detected = True

        # Create threads
        threads = []
        num_threads = 20  # More threads for higher contention

        for i in range(num_threads):
            thread = threading.Thread(target=write_large_data, args=(i,))
            threads.append(thread)

        # Start all threads simultaneously
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Final validation
        final_data = storage.read_json(test_file)

        print(f"Successful writes: {len(successful_writes)}/{num_threads}")
        print(f"Failed reads: {len(failed_reads)}")

        # Verify final file is valid JSON
        if final_data is None:
            print("ERROR: Final file is unreadable!")
            corruption_detected = True
        elif not isinstance(final_data, dict):
            print("ERROR: Final file is corrupted!")
            corruption_detected = True
        else:
            print(
                f"Final file contains valid data from thread {final_data.get('thread_id')}"
            )

            # Verify structure integrity
            if "large_array" not in final_data or "nested" not in final_data:
                print("ERROR: Final data structure incomplete!")
                corruption_detected = True
            elif len(final_data["large_array"]) != 1000:
                print("ERROR: Array data corrupted!")
                corruption_detected = True

        if not corruption_detected:
            print("✓ No corruption detected - file locking is working!")
        else:
            print("✗ Corruption detected - file locking may not be working!")

        return not corruption_detected  # Return True if locking works


if __name__ == "__main__":
    locking_works = test_file_locking_prevents_corruption()
    print(f"\nFile locking working: {locking_works}")
