#!/usr/bin/env python3
"""Quick test check to identify problematic tests."""

import os
import subprocess
from pathlib import Path

# Set headless mode
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_LOGGING_RULES"] = "*.debug=false"


def check_test_file(test_path: str, timeout: int = 5):
    """Check if a test file runs successfully."""
    try:
        result = subprocess.run(
            ["./venv/bin/python", "run_tests.py", test_path, "-x", "--tb=no"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )

        output = result.stdout + result.stderr
        if result.returncode == 0:
            if "passed" in output:
                return "✅ PASS"
            return "❓ UNKNOWN"
        if "FAILED" in output or "ERROR" in output:
            # Extract error summary
            lines = output.split("\n")
            for line in lines:
                if "FAILED" in line or "ERROR" in line:
                    return f"❌ {line.strip()[:50]}"
            return "❌ FAIL"
        return "❌ FAIL"
    except subprocess.TimeoutExpired:
        return "⏰ TIMEOUT"
    except Exception as e:
        return f"💥 ERROR: {e}"


def main():
    # Test a few key test files first
    test_files = [
        "tests/unit/test_cache_manager.py",
        "tests/unit/test_shot_model.py",
        "tests/unit/test_utils.py",
        "tests/integration/test_button_launcher_integration.py",
        "tests/integration/test_caching_workflow.py",
        "tests/integration/test_main_window_shot_grid_integration.py",
        "tests/advanced/test_contract_validation.py",
        "tests/advanced/test_property_based.py",
    ]

    print("🔍 Quick Test Check (5s timeout per file)")
    print("=" * 60)

    for test_file in test_files:
        if Path(test_file).exists():
            print(f"{test_file:50} ", end="", flush=True)
            status = check_test_file(test_file)
            print(status)

    print("\n✨ Check complete!")


if __name__ == "__main__":
    main()