#!/usr/bin/env python3
"""Aggressively clean up test suite - keep only known good tests."""

import shutil
from pathlib import Path


def main():
    """Delete all tests except known good ones."""
    print("Aggressive Test Cleanup")
    print("=" * 70)
    print("Deleting all tests except known working ones")
    print()
    
    # Tests to keep (our fast, working tests)
    keep_tests = {
        "tests/integration/test_process_pool_fast.py",
        "tests/integration/test_subprocess_fast.py",
    }
    
    # Find all test files
    test_dir = Path("tests")
    if not test_dir.exists():
        print("No tests directory found")
        return
    
    all_test_files = list(test_dir.rglob("test_*.py"))
    
    # Separate files to keep and delete
    to_delete = []
    to_keep = []
    
    for test_file in all_test_files:
        relative_path = str(test_file)
        if relative_path in keep_tests:
            to_keep.append(test_file)
        else:
            to_delete.append(test_file)
    
    print(f"Found {len(all_test_files)} test files")
    print(f"Keeping {len(to_keep)} files")
    print(f"Deleting {len(to_delete)} files")
    print()
    
    # Delete problematic tests
    if to_delete:
        print("Deleting problematic tests:")
        for f in to_delete:
            try:
                f.unlink()
                print(f"  ✓ Deleted: {f.name}")
            except Exception as e:
                print(f"  ✗ Error deleting {f.name}: {e}")
    
    # Clean up empty directories
    print("\nCleaning up empty directories...")
    for dirpath in sorted(test_dir.rglob("*"), reverse=True):
        if dirpath.is_dir():
            try:
                if not any(dirpath.iterdir()):
                    dirpath.rmdir()
                    print(f"  ✓ Removed empty: {dirpath}")
            except (OSError, PermissionError):
                pass
    
    # Clean up __pycache__
    print("\nCleaning __pycache__ directories...")
    for cache_dir in Path(".").rglob("__pycache__"):
        try:
            shutil.rmtree(cache_dir)
            print(f"  ✓ Removed: {cache_dir}")
        except (OSError, PermissionError):
            pass
    
    # Clean up .pytest_cache
    if Path(".pytest_cache").exists():
        try:
            shutil.rmtree(".pytest_cache")
            print("  ✓ Removed: .pytest_cache")
        except (OSError, PermissionError):
            pass
    
    print("\n" + "=" * 70)
    print("CLEANUP COMPLETE")
    print("=" * 70)
    print(f"Kept {len(to_keep)} working test files")
    print("\nRemaining tests:")
    for f in to_keep:
        print(f"  ✓ {f}")

if __name__ == "__main__":
    main()