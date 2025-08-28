#!/usr/bin/env python3
"""Establish performance baseline metrics for shotbot application.

Measures key performance indicators to track improvements over time.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict

# Suppress Qt warnings for headless testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_LOGGING_RULES"] = "*.debug=false"

# Set up minimal logging
logging.basicConfig(level=logging.WARNING)


def measure_import_times() -> dict[str, float]:
    """Measure import times for critical modules."""
    import_times = {}

    # Measure PySide6 import
    start = time.perf_counter()
    import_times["PySide6"] = time.perf_counter() - start

    # Measure application module imports
    modules = [
        "config",
        "utils",
        "shot_model",
        "cache_manager",
        "launcher_manager",
        "previous_shots_worker",
        "main_window",
    ]

    for module in modules:
        start = time.perf_counter()
        __import__(module)
        import_times[module] = time.perf_counter() - start

    return import_times


def measure_startup_time() -> dict[str, float]:
    """Measure application startup time."""
    from PySide6.QtWidgets import QApplication

    # Create Qt application
    app = QApplication.instance()
    if not app:
        app = QApplication([])

    metrics = {}

    # Measure MainWindow creation
    start = time.perf_counter()
    from main_window import MainWindow

    window = MainWindow()
    metrics["window_creation"] = time.perf_counter() - start

    # Measure initial shot loading (mocked)
    start = time.perf_counter()
    from unittest.mock import MagicMock, patch

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="test_show seq01 shot001 /shows/test", returncode=0
        )
        window.shot_model.refresh_shots()
    metrics["initial_refresh"] = time.perf_counter() - start

    # Cleanup
    window.close()
    app.quit()

    return metrics


def measure_memory_usage() -> dict[str, Any]:
    """Measure memory usage patterns."""
    tracemalloc.start()

    from PySide6.QtWidgets import QApplication

    from cache_manager import CacheManager
    from main_window import MainWindow

    app = QApplication.instance()
    if not app:
        app = QApplication([])

    # Create main components
    cache = CacheManager()
    window = MainWindow()

    # Get memory snapshot
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")

    metrics = {
        "total_blocks": sum(stat.count for stat in top_stats),
        "total_size_mb": sum(stat.size for stat in top_stats) / 1024 / 1024,
        "top_consumers": [],
    }

    # Get top 10 memory consumers
    for stat in top_stats[:10]:
        metrics["top_consumers"].append(
            {
                "file": stat.traceback.format()[0] if stat.traceback else "unknown",
                "size_kb": stat.size / 1024,
                "count": stat.count,
            }
        )

    # Cleanup
    window.close()
    app.quit()
    tracemalloc.stop()

    return metrics


def measure_cache_performance() -> dict[str, float]:
    """Measure cache operation performance."""
    import tempfile

    from cache_manager import CacheManager
    from shot_model import Shot

    metrics = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        cache = CacheManager(cache_dir=Path(tmpdir))

        # Create test shots
        shots = [
            Shot(f"show{i}", f"seq{i:02d}", f"shot{i:03d}", f"/path/{i}")
            for i in range(100)
        ]

        # Measure cache write performance
        start = time.perf_counter()
        cache.cache_shots(shots)
        metrics["cache_100_shots"] = time.perf_counter() - start

        # Measure cache read performance
        start = time.perf_counter()
        cached = cache.get_cached_shots()
        metrics["read_100_shots"] = time.perf_counter() - start

        # Measure thumbnail cache simulation
        from unittest.mock import MagicMock

        mock_image = MagicMock()

        start = time.perf_counter()
        for i in range(10):
            cache.cache_thumbnail(
                Path(f"/fake/path/{i}.jpg"), f"show{i}", f"seq{i}", f"shot{i}"
            )
        metrics["cache_10_thumbnails"] = time.perf_counter() - start

    return metrics


def measure_test_performance() -> dict[str, float]:
    """Measure test suite execution performance."""
    import subprocess

    metrics = {}

    # Run unit tests for key modules
    test_modules = [
        "tests/unit/test_shot_model.py",
        "tests/unit/test_cache_manager.py",
        "tests/unit/test_launcher_manager.py",
        "tests/unit/test_previous_shots_worker.py",
    ]

    for test_module in test_modules:
        if Path(test_module).exists():
            start = time.perf_counter()
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_module, "-q"],
                capture_output=True,
                timeout=30,
            )
            elapsed = time.perf_counter() - start

            module_name = Path(test_module).stem
            metrics[f"{module_name}_time"] = elapsed
            metrics[f"{module_name}_passed"] = result.returncode == 0

    return metrics


def main():
    """Run all performance measurements and save baseline."""
    print("Establishing Performance Baseline for ShotBot")
    print("=" * 50)

    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python_version": sys.version,
        "platform": sys.platform,
    }

    # Run measurements
    print("\n1. Measuring import times...")
    results["import_times"] = measure_import_times()

    print("2. Measuring startup time...")
    results["startup_metrics"] = measure_startup_time()

    print("3. Measuring memory usage...")
    gc.collect()  # Clean slate
    results["memory_metrics"] = measure_memory_usage()

    print("4. Measuring cache performance...")
    results["cache_metrics"] = measure_cache_performance()

    print("5. Measuring test performance...")
    results["test_metrics"] = measure_test_performance()

    # Calculate summary metrics
    total_import_time = sum(results["import_times"].values())
    total_startup_time = sum(results["startup_metrics"].values())

    results["summary"] = {
        "total_import_time": total_import_time,
        "total_startup_time": total_startup_time,
        "total_memory_mb": results["memory_metrics"]["total_size_mb"],
        "cache_write_speed": 100
        / results["cache_metrics"]["cache_100_shots"],  # shots/sec
        "cache_read_speed": 100
        / results["cache_metrics"]["read_100_shots"],  # shots/sec
    }

    # Save results
    output_file = Path("PERFORMANCE_BASELINE.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Print summary
    print("\n" + "=" * 50)
    print("Performance Baseline Summary:")
    print(f"  Total Import Time: {total_import_time:.3f}s")
    print(f"  Total Startup Time: {total_startup_time:.3f}s")
    print(f"  Memory Usage: {results['memory_metrics']['total_size_mb']:.1f} MB")
    print(
        f"  Cache Write Speed: {results['summary']['cache_write_speed']:.0f} shots/sec"
    )
    print(f"  Cache Read Speed: {results['summary']['cache_read_speed']:.0f} shots/sec")

    print(f"\nResults saved to: {output_file}")

    return results


if __name__ == "__main__":
    main()