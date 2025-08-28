#!/usr/bin/env python3
"""Profile ShotBot application startup performance."""

import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))


def profile_imports():
    """Profile import times for key modules."""
    print("Profiling module imports...")
    print("-" * 60)
    
    import_times = {}
    
    # Profile each import
    modules = [
        "PySide6.QtWidgets",
        "PySide6.QtCore", 
        "PySide6.QtGui",
        "shot_model",
        "cache_manager",
        "main_window",
        "process_pool_manager",
    ]
    
    for module in modules:
        start = time.perf_counter()
        try:
            __import__(module)
            elapsed = (time.perf_counter() - start) * 1000
            import_times[module] = elapsed
            print(f"  {module:<30} {elapsed:>8.2f} ms")
        except ImportError as e:
            print(f"  {module:<30} FAILED: {e}")
    
    print("-" * 60)
    total = sum(import_times.values())
    print(f"  {'TOTAL':<30} {total:>8.2f} ms")
    print()
    
    return import_times


def profile_window_creation():
    """Profile MainWindow initialization."""
    print("Profiling MainWindow creation...")
    print("-" * 60)
    
    # Import after modules are loaded
    from main_window import MainWindow
    from PySide6.QtWidgets import QApplication
    
    # Need QApplication for Qt widgets
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    # Profile window creation
    profiler = cProfile.Profile()
    profiler.enable()
    
    start = time.perf_counter()
    window = MainWindow()
    elapsed = (time.perf_counter() - start) * 1000
    
    profiler.disable()
    
    print(f"  MainWindow creation: {elapsed:.2f} ms")
    print()
    
    # Get top time consumers
    print("Top 20 time-consuming functions:")
    print("-" * 60)
    
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(20)
    
    # Parse and display nicely
    for line in s.getvalue().split('\n')[6:27]:  # Skip header, show top 20
        if line.strip():
            print(f"  {line}")
    
    return elapsed, window


def profile_shot_model_init():
    """Profile ShotModel initialization and loading."""
    print("\nProfiling ShotModel initialization...")
    print("-" * 60)
    
    from shot_model import ShotModel
    from cache_manager import CacheManager
    
    timings = {}
    
    # Profile without cache
    start = time.perf_counter()
    model_no_cache = ShotModel(load_cache=False)
    timings['init_no_cache'] = (time.perf_counter() - start) * 1000
    
    # Profile with cache (first time)
    cache_mgr = CacheManager()
    start = time.perf_counter()
    model_with_cache = ShotModel(cache_manager=cache_mgr, load_cache=True)
    timings['init_with_cache'] = (time.perf_counter() - start) * 1000
    
    # Profile refresh
    start = time.perf_counter()
    success, changed = model_with_cache.refresh_shots()
    timings['refresh'] = (time.perf_counter() - start) * 1000
    
    for key, value in timings.items():
        print(f"  {key:<30} {value:>8.2f} ms")
    
    return timings


def profile_cache_operations():
    """Profile cache manager operations."""
    print("\nProfiling cache operations...")
    print("-" * 60)
    
    from cache_manager import CacheManager
    from shot_model import Shot
    
    cache = CacheManager()
    timings = {}
    
    # Create test shot
    shot = Shot(
        show="test_show",
        sequence="seq01", 
        shot="0010",
        workspace_path="/test/path"
    )
    
    # Profile cache operations
    operations = [
        ('cache_shots', lambda: cache.cache_shots([shot])),
        ('get_cached_shots', lambda: cache.get_cached_shots()),
        ('clear_cache', lambda: cache.clear_cache()),
    ]
    
    for name, operation in operations:
        start = time.perf_counter()
        try:
            operation()
            timings[name] = (time.perf_counter() - start) * 1000
            print(f"  {name:<30} {timings[name]:>8.2f} ms")
        except Exception as e:
            print(f"  {name:<30} FAILED: {e}")
    
    return timings


def main():
    """Run all profiling tasks."""
    print("=" * 60)
    print("SHOTBOT STARTUP PERFORMANCE PROFILE")
    print("=" * 60)
    print()
    
    # Profile imports
    import_times = profile_imports()
    
    # Profile shot model
    shot_timings = profile_shot_model_init()
    
    # Profile cache
    cache_timings = profile_cache_operations()
    
    # Profile window creation (do this last as it's heaviest)
    try:
        window_time, window = profile_window_creation()
    except Exception as e:
        print(f"Failed to profile window creation: {e}")
        window_time = None
    
    # Summary
    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    
    total_import = sum(import_times.values())
    print(f"Total import time:        {total_import:>8.2f} ms")
    
    if window_time:
        print(f"MainWindow creation:      {window_time:>8.2f} ms")
        print(f"Total startup time:       {total_import + window_time:>8.2f} ms")
    
    # Identify bottlenecks
    print("\nBottlenecks (>100ms):")
    all_timings = {**import_times}
    if window_time:
        all_timings['MainWindow'] = window_time
    
    bottlenecks = {k: v for k, v in all_timings.items() if v > 100}
    if bottlenecks:
        for name, time_ms in sorted(bottlenecks.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {name}: {time_ms:.2f} ms")
    else:
        print("  None identified")
    
    print("\nOptimization opportunities:")
    if 'PySide6.QtWidgets' in import_times and import_times['PySide6.QtWidgets'] > 200:
        print("  - Consider lazy loading Qt modules")
    if window_time and window_time > 500:
        print("  - Consider deferring widget creation in MainWindow")
    if shot_timings.get('refresh', 0) > 1000:
        print("  - Consider async shot loading")
    print()


if __name__ == '__main__':
    main()