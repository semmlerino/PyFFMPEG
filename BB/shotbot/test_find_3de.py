#!/usr/bin/env python3
"""Test script to find 3DE files in publish directories."""

import subprocess
from pathlib import Path


def test_find_3de_files():
    """Test finding 3DE files in publish directories."""
    
    # Test on GF_256_1420 which we know has 3 files
    test_path = "/shows/jack_ryan/shots/GF_256/GF_256_1420/publish"
    
    if not Path(test_path).exists():
        print(f"Path does not exist: {test_path}")
        return
    
    print(f"Searching for .3de files in: {test_path}")
    print("-" * 60)
    
    # Run find command similar to what the scanner uses
    find_cmd = [
        "find",
        test_path,
        "-maxdepth", "15",
        "-type", "f",
        "(",
        "-name", "*.3de",
        "-o",
        "-name", "*.3DE",
        ")",
    ]
    
    try:
        result = subprocess.run(
            find_cmd, capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0 and result.stdout.strip():
            files = result.stdout.strip().split("\n")
            print(f"Found {len(files)} .3de files:")
            for f in files:
                print(f"  {f}")
        else:
            print("No .3de files found")
            if result.stderr:
                print(f"Error: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        print("Find command timed out")
    except Exception as e:
        print(f"Error running find: {e}")
    
    print("-" * 60)
    
    # Also test another shot that should have published files
    test_paths = [
        "/shows/jack_ryan/shots/GF_256/GF_256_0980/publish",
        "/shows/jack_ryan/shots/GF_256/GF_256_1100/publish",
        "/shows/gator/shots/012_DC/012_DC_1100/publish",
    ]
    
    for path in test_paths:
        if Path(path).exists():
            print(f"\nChecking {path}:")
            find_cmd[1] = path
            result = subprocess.run(find_cmd, capture_output=True, text=True, timeout=5)
            if result.stdout.strip():
                files = result.stdout.strip().split("\n")
                print(f"  Found {len(files)} .3de files")
            else:
                print("  No .3de files found")

if __name__ == "__main__":
    test_find_3de_files()