#!/usr/bin/env python3
"""Test script to verify FIFO race condition behavior."""

import errno
import os
import subprocess
import time


def test_fifo_race():
    """Test if health check pattern causes bash to exit."""

    # Find the test script's FIFO by looking for the bash process
    time.sleep(1)  # Give bash time to create FIFO

    # Find FIFO path from bash process
    result = subprocess.run(
        ["pgrep", "-f", "test_fifo_race.sh"],
        check=False, capture_output=True,
        text=True
    )

    if not result.stdout.strip():
        print("ERROR: test_fifo_race.sh not running")
        return

    pid = result.stdout.strip().split()[0]
    print(f"Found bash process PID: {pid}")

    # Get FIFO path from /proc/pid/fd
    fd_dir = f"/proc/{pid}/fd"
    fifo_path = None

    try:
        for fd in os.listdir(fd_dir):
            link = os.readlink(f"{fd_dir}/{fd}")
            if "test_fifo_" in link and link.endswith(pid):
                fifo_path = link
                break
    except:
        # Try common pattern
        fifo_path = f"/tmp/test_fifo_{pid}"

    if not fifo_path or not os.path.exists(fifo_path):
        print(f"ERROR: Could not find FIFO (tried {fifo_path})")
        return

    print(f"Found FIFO: {fifo_path}")
    print()

    # Test 1: Simulate health check (open/close with no data)
    print("=" * 60)
    print("TEST 1: Health check simulation (open/close, no data)")
    print("=" * 60)
    time.sleep(0.5)

    for i in range(3):
        print(f"\nHealth check #{i+1}:")
        try:
            fd = os.open(fifo_path, os.O_WRONLY | os.O_NONBLOCK)
            print(f"  - Opened FIFO (fd={fd})")
            os.close(fd)
            print("  - Closed FIFO immediately (no data written)")
            time.sleep(1)

            # Check if bash is still alive
            try:
                os.kill(int(pid), 0)
                print("  ✓ Bash still alive")
            except ProcessLookupError:
                print("  ✗ BASH DIED! (This is the race condition)")
                return

        except OSError as e:
            if e.errno == errno.ENXIO:
                print("  ✗ No reader available (bash died)")
                return
            print(f"  Error: {e}")
            return

    print()
    print("=" * 60)
    print("TEST 2: Send actual command")
    print("=" * 60)
    time.sleep(0.5)

    try:
        fd = os.open(fifo_path, os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, b"test command 1\n")
        os.close(fd)
        print("Sent: 'test command 1'")
        time.sleep(1)

        # Send another command
        fd = os.open(fifo_path, os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, b"test command 2\n")
        os.close(fd)
        print("Sent: 'test command 2'")
        time.sleep(1)

        # Send exit command
        fd = os.open(fifo_path, os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, b"EXIT\n")
        os.close(fd)
        print("Sent: 'EXIT'")

    except OSError as e:
        print(f"Error sending command: {e}")

if __name__ == "__main__":
    print("FIFO Race Condition Test")
    print("=" * 60)
    print()
    print("This test verifies if the health check pattern causes bash to exit")
    print("when using 'read < FIFO' with fresh opens on each iteration.")
    print()
    print("Expected behavior:")
    print("  - Bash should STAY ALIVE through health checks")
    print("  - Bash should receive actual commands correctly")
    print()
    print("Bug behavior:")
    print("  - Bash DIES after first health check (open/close with no data)")
    print()

    test_fifo_race()
