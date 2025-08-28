#!/usr/bin/env python3
"""Generate coverage report for key modules."""

import subprocess
import sys

# Key modules to analyze
modules = [
    "shot_model",
    "base_shot_model", 
    "cache_manager",
    "previous_shots_worker",
    "process_pool_manager",
    "cache.storage_backend",
    "cache.failure_tracker",
    "cache.memory_manager",
    "cache.thumbnail_processor",
    "cache.shot_cache",
    "cache.threede_cache",
    "cache.cache_validator",
    "cache.thumbnail_loader",
]

# Build coverage command
cov_args = []
for module in modules:
    cov_args.extend(["--cov", module])

cmd = [
    "./venv/bin/pytest",
    "-x",  # Stop on first failure
    "-q",  # Quiet mode
    "--tb=no",  # No traceback
    "--no-header",  # No header
    *cov_args,
    "--cov-report=term-missing:skip-covered",
    "--cov-report=html",
    "--cov-branch",
]

print("Running coverage analysis...")
print("=" * 60)

result = subprocess.run(cmd, capture_output=True, text=True)

# Parse output for coverage info
output_lines = result.stdout.split("\n")
in_coverage = False

for line in output_lines:
    if "Name" in line and "Stmts" in line:
        in_coverage = True
    if in_coverage:
        if line.strip():
            print(line)
        if "TOTAL" in line:
            break

print("\n" + "=" * 60)
print("Coverage report generated in htmlcov/index.html")

# Summary of modules needing attention
print("\nModules needing more test coverage (<70%):")
for line in output_lines:
    if any(module in line for module in modules):
        parts = line.split()
        if len(parts) >= 4:
            try:
                coverage = int(parts[-1].rstrip("%"))
                if coverage < 70:
                    print(f"  - {parts[0]}: {parts[-1]} coverage")
            except (ValueError, IndexError):
                pass