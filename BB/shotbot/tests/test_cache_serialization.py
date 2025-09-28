#!/usr/bin/env python3
"""Test that file locking ensures proper serialization of cache writes."""

# Standard library imports
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Standard library imports
import tempfile
import threading
import time
from pathlib import Path

# Local application imports
from cache.storage_backend import StorageBackend


def test_cache_write_serialization() -> bool:
    """Test that file locking ensures writes are properly serialized."""

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = StorageBackend()
        test_file = Path(tmpdir) / "counter.json"

        # Initialize counter file
        storage.write_json(test_file, {"counter": 0, "writers": []})

        successful_increments = []
        errors = []

        def increment_counter(thread_id: int) -> None:
            """Each thread reads, increments, and writes back."""
            try:
                # This would race without proper locking
                for _ in range(5):  # Each thread increments 5 times

                    def update_data(current_data):
                        """Update function for atomic operation."""
                        if current_data is None:
                            current_data = {"counter": 0, "writers": []}

                        # Increment counter
                        current_data["counter"] += 1
                        current_data["writers"].append(thread_id)

                        # Small delay to increase race probability
                        time.sleep(0.001)

                        successful_increments.append(
                            (thread_id, current_data["counter"])
                        )
                        return current_data

                    # Use atomic update
                    storage.atomic_update_json(
                        test_file, update_data, default={"counter": 0, "writers": []}
                    )
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Create threads
        threads = []
        num_threads = 10

        for i in range(num_threads):
            thread = threading.Thread(target=increment_counter, args=(i,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Check final result
        final_data = storage.read_json(test_file)
        final_counter = final_data.get("counter", 0)
        final_writers = final_data.get("writers", [])

        print(f"Expected final counter: {num_threads * 5}")
        print(f"Actual final counter: {final_counter}")
        print(f"Total writes recorded: {len(final_writers)}")
        print(f"Successful increments: {len(successful_increments)}")
        print(f"Errors: {len(errors)}")

        # With proper locking, counter should equal total increments
        expected = num_threads * 5

        if final_counter == expected:
            print("✓ File locking is working correctly!")
            return True
        else:
            print(
                f"✗ Race condition detected: Lost {expected - final_counter} increments"
            )
            return False


if __name__ == "__main__":
    success = test_cache_write_serialization()
    if not success:
        sys.exit(1)
