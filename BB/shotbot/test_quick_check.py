import subprocess
import sys
from pathlib import Path

test_files = list(Path("tests/unit").glob("test_*.py"))
test_files += list(Path("tests/threading").glob("test_*.py"))

hanging_tests = []
working_tests = []

for test_file in test_files:
    print(f"Testing {test_file}...", flush=True)

    try:
        # Run test with timeout
        result = subprocess.run(
            [sys.executable, "run_tests.py", str(test_file), "-q"],
            timeout=8,
            capture_output=True,
            text=True,
        )

        if "passed" in result.stdout or result.returncode == 0:
            working_tests.append(str(test_file))
            print(f"  ✓ {test_file} - OK", flush=True)
        else:
            print(f"  ⚠ {test_file} - Some failures", flush=True)
            working_tests.append(str(test_file))

    except subprocess.TimeoutExpired:
        print(f"  ✗ {test_file} - TIMEOUT (HANGING)", flush=True)
        hanging_tests.append(str(test_file))

print("\n=== SUMMARY ===")
print(f"Working tests: {len(working_tests)}")
print(f"Hanging tests: {len(hanging_tests)}")

if hanging_tests:
    print("\nHANGING TESTS:")
    for test in hanging_tests:
        print(f"  - {test}")
