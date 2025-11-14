#!/usr/bin/env python3
"""Test script to verify FIFO race condition behavior."""

import os
import time
import glob
import errno

def test_fifo_race():
    """Test if health check pattern causes bash to exit."""
    
    # Find FIFO
    fifos = glob.glob("/tmp/test_fifo_*")
    if not fifos:
        print("ERROR: No test FIFO found")
        return
    
    fifo_path = fifos[0]
    pid = fifo_path.split("_")[-1]
    
    print(f"Found FIFO: {fifo_path}")
    print(f"Bash PID: {pid}")
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
            print(f"  - Closed FIFO immediately (no data written)")
            time.sleep(1)
            
            # Check if bash is still alive
            try:
                os.kill(int(pid), 0)
                print(f"  ✓ Bash still alive")
            except ProcessLookupError:
                print(f"  ✗ BASH DIED! (This is the race condition)")
                return
                
        except OSError as e:
            if e.errno == errno.ENXIO:
                print(f"  ✗ No reader available (bash died)")
                return
            else:
                print(f"  Error: {e}")
                return
    
    print()
    print("=" * 60)
    print("TEST 2: Send actual commands")
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
        time.sleep(1)
        
        print("\n✓ All commands sent successfully")
        
    except OSError as e:
        print(f"✗ Error sending command: {e}")

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
