import subprocess
import sys
from pathlib import Path

# List of tests we already know are hanging
hanging = [
    "tests/unit/test_cache_manager.py",
    "tests/unit/test_example_best_practices.py",
    "tests/unit/test_exr_edge_cases.py",
    "tests/unit/test_exr_parametrized.py",
    "tests/unit/test_exr_performance.py",
    "tests/unit/test_main_window.py",
]

# Tests to check
remaining = [
    "tests/unit/test_nuke_script_generator.py",
    "tests/unit/test_previous_shots_cache_integration.py",
    "tests/unit/test_previous_shots_finder.py",
    "tests/unit/test_previous_shots_grid.py",
    "tests/unit/test_previous_shots_model.py",
    "tests/unit/test_previous_shots_worker.py",
    "tests/unit/test_process_pool_manager_simple.py",
    "tests/unit/test_protocols.py",
    "tests/unit/test_raw_plate_finder.py",
    "tests/unit/test_scanner_coverage.py",
    "tests/unit/test_shot_cache.py",
    "tests/unit/test_shot_deduplication.py",
    "tests/unit/test_shot_info_panel.py",
    "tests/unit/test_shot_item_model.py",
    "tests/unit/test_shot_model.py",
    "tests/unit/test_shotbot.py",
    "tests/unit/test_storage_backend.py",
    "tests/unit/test_thread_safe_worker.py",
    "tests/unit/test_threede_cache.py",
    "tests/unit/test_threede_path_parsing.py",
    "tests/unit/test_threede_scene_finder.py",
    "tests/unit/test_threede_scene_model.py",
    "tests/unit/test_threede_scene_worker.py",
    "tests/unit/test_threede_shot_grid.py",
    "tests/unit/test_threede_stop_after_first.py",
    "tests/unit/test_threede_thumbnail_widget.py",
    "tests/unit/test_thumbnail_loader.py",
    "tests/unit/test_thumbnail_processor.py",
    "tests/unit/test_undistortion_finder.py",
    "tests/unit/test_utils.py",
    "tests/unit/test_utils_extended.py",
    "tests/threading/test_threading_fixes.py",
]

for test_file in remaining:
    if not Path(test_file).exists():
        continue
    print(f"Testing {test_file}...", flush=True)

    try:
        result = subprocess.run(
            [sys.executable, "run_tests.py", test_file, "-q"],
            timeout=8,
            capture_output=True,
            text=True,
        )

        if "passed" in result.stdout or result.returncode == 0:
            print("  ✓ OK", flush=True)
        else:
            print("  ⚠ Some failures", flush=True)

    except subprocess.TimeoutExpired:
        print("  ✗ TIMEOUT (HANGING)", flush=True)
        hanging.append(test_file)

print("\n=== FINAL LIST OF HANGING TESTS ===")
for test in sorted(hanging):
    print(f"  - {test}")
