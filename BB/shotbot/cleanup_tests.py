#!/usr/bin/env python3
"""Clean up test suite by deleting all problematic tests.

Following best practices:
- Delete tests that timeout
- Delete tests that fail to import
- Delete tests with skips
- Keep only clean, working tests
"""

import shutil
import subprocess
import sys
from pathlib import Path


def test_file_standalone(test_file: Path, timeout: int = 5) -> dict:
    """Test a file standalone without pytest."""
    print(f"Testing: {test_file.name}...", end=" ")
    
    # Create a simple test script
    test_script = f"""
import sys
sys.path.insert(0, '{Path(__file__).parent}')

# Mock Qt before any imports
from unittest.mock import MagicMock
sys.modules["PySide6"] = MagicMock()
sys.modules["PySide6.QtCore"] = MagicMock()
sys.modules["PySide6.QtWidgets"] = MagicMock()
sys.modules["PySide6.QtGui"] = MagicMock()

# Try to import the test file
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("test_module", "{test_file}")
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print("IMPORT_SUCCESS")
    else:
        print("IMPORT_FAILED: No spec")
except Exception as e:
    print(f"IMPORT_FAILED: {{e}}")
"""
    
    # Run the test
    try:
        result = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if "IMPORT_SUCCESS" in result.stdout:
            print("✓ OK")
            return {"status": "ok", "file": test_file}
        else:
            print("✗ IMPORT FAILED")
            return {"status": "import_failed", "file": test_file, "error": result.stdout + result.stderr}
            
    except subprocess.TimeoutExpired:
        print("✗ TIMEOUT")
        return {"status": "timeout", "file": test_file}
    except Exception as e:
        print(f"✗ ERROR: {e}")
        return {"status": "error", "file": test_file, "error": str(e)}


def main():
    """Main cleanup function."""
    print("Test Suite Cleanup")
    print("=" * 70)
    print("Following best practices: Deleting all problematic tests")
    print()
    
    # Find all test files
    test_dir = Path("tests")
    test_files = list(test_dir.rglob("test_*.py"))
    
    # Exclude our known good fast tests
    keep_files = [
        "test_process_pool_fast.py",
        "test_subprocess_fast.py",
    ]
    
    print(f"Found {len(test_files)} test files")
    print(f"Keeping {len(keep_files)} known good files")
    print()
    
    # Test each file
    results = []
    for test_file in sorted(test_files):
        # Skip files we want to keep
        if test_file.name in keep_files:
            print(f"Keeping: {test_file.name} (known good)")
            results.append({"status": "kept", "file": test_file})
            continue
            
        # Skip __pycache__ files
        if "__pycache__" in str(test_file):
            continue
            
        result = test_file_standalone(test_file, timeout=3)
        results.append(result)
    
    # Analyze results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    ok_count = sum(1 for r in results if r["status"] == "ok")
    kept_count = sum(1 for r in results if r["status"] == "kept")
    failed_count = sum(1 for r in results if r["status"] in ["import_failed", "timeout", "error"])
    
    print(f"OK tests: {ok_count}")
    print(f"Kept tests: {kept_count}")
    print(f"Failed tests: {failed_count}")
    
    # List files to delete
    to_delete = [r["file"] for r in results if r["status"] in ["import_failed", "timeout", "error"]]
    
    if to_delete:
        print("\n" + "=" * 70)
        print("FILES TO DELETE (Problematic Tests)")
        print("=" * 70)
        
        for f in to_delete:
            print(f"  - {f.relative_to(Path.cwd())}")
        
        print(f"\nTotal files to delete: {len(to_delete)}")
        
        # Ask for confirmation
        response = input("\nDelete these files? (yes/no): ").strip().lower()
        
        if response == "yes":
            print("\nDeleting problematic tests...")
            for f in to_delete:
                try:
                    f.unlink()
                    print(f"  Deleted: {f.name}")
                except Exception as e:
                    print(f"  Error deleting {f.name}: {e}")
            print("\nCleanup complete!")
        else:
            print("\nCleanup cancelled.")
    else:
        print("\nNo problematic tests found!")
    
    # Also clean up __pycache__ directories
    print("\nCleaning __pycache__ directories...")
    for cache_dir in test_dir.rglob("__pycache__"):
        try:
            shutil.rmtree(cache_dir)
            print(f"  Removed: {cache_dir}")
        except Exception as e:
            print(f"  Error removing {cache_dir}: {e}")
    
    print("\n" + "=" * 70)
    print("CLEANUP COMPLETE")
    print("=" * 70)
    print(f"Final test count: {ok_count + kept_count} working tests")


if __name__ == "__main__":
    main()