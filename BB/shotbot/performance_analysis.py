#!/usr/bin/env python3
"""
Performance Analysis Script for ShotBot Application
Analyzes CPU, memory, and I/O performance characteristics
"""

import sys
import threading
import time
from pathlib import Path

import psutil

# Import key components for analysis
sys.path.insert(0, str(Path(__file__).parent))


# Mock Qt for CLI analysis
class MockQObject:
    def __init__(self, *args, **kwargs):
        pass


class MockSignal:
    def __init__(self, *args):
        pass

    def emit(self, *args):
        pass

    def connect(self, *args):
        pass


class MockQTimer:
    def __init__(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def setInterval(self, *args):
        pass

    def isActive(self):
        return False

    @property
    def timeout(self):
        return MockSignal()


class MockQt:
    class AspectRatioMode:
        KeepAspectRatio = 1

    class TransformationMode:
        SmoothTransformation = 1

    class ItemDataRole:
        DisplayRole = 0
        DecorationRole = 1
        UserRole = 256


# Mock PySide6 modules
sys.modules["PySide6"] = type(sys)("PySide6")
sys.modules["PySide6.QtCore"] = type(sys)("PySide6.QtCore")
sys.modules["PySide6.QtGui"] = type(sys)("PySide6.QtGui")
sys.modules["PySide6.QtWidgets"] = type(sys)("PySide6.QtWidgets")

sys.modules["PySide6.QtCore"].QObject = MockQObject
sys.modules["PySide6.QtCore"].Signal = MockSignal
sys.modules["PySide6.QtCore"].QTimer = MockQTimer
sys.modules["PySide6.QtCore"].Qt = MockQt
sys.modules["PySide6.QtCore"].QAbstractListModel = MockQObject
sys.modules["PySide6.QtCore"].QModelIndex = MockQObject
sys.modules["PySide6.QtCore"].QPersistentModelIndex = MockQObject
sys.modules["PySide6.QtCore"].QSize = MockQObject
sys.modules["PySide6.QtCore"].Slot = lambda *args, **kwargs: lambda f: f
sys.modules["PySide6.QtCore"].QRunnable = MockQObject
sys.modules["PySide6.QtCore"].QThread = MockQObject
sys.modules["PySide6.QtCore"].QThreadPool = type(
    "QThreadPool", (), {"globalInstance": lambda: MockQObject()}
)()

sys.modules["PySide6.QtGui"].QIcon = MockQObject
sys.modules["PySide6.QtGui"].QPixmap = MockQObject
sys.modules["PySide6.QtGui"].QImage = MockQObject

sys.modules["PySide6.QtWidgets"].QApplication = type(
    "QApplication", (), {"instance": lambda: None}
)()


def analyze_cache_manager_performance():
    """Analyze CacheManager performance characteristics."""
    print("\n=== CACHE MANAGER PERFORMANCE ANALYSIS ===")

    try:
        from cache_manager import CacheManager

        # Test cache creation performance
        print("1. Cache Manager Initialization:")
        start_time = time.perf_counter()
        cache_mgr = CacheManager()
        init_time = time.perf_counter() - start_time
        print(f"   - Initialization time: {init_time * 1000:.2f}ms")

        # Test memory usage
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Test cache operations
        print("2. Cache Operations:")
        start_time = time.perf_counter()

        # Simulate getting cached shots (empty cache)
        cache_mgr.get_cached_shots()
        get_time = time.perf_counter() - start_time
        print(f"   - get_cached_shots() time: {get_time * 1000:.2f}ms")

        # Test cache validation
        start_time = time.perf_counter()
        validation_result = cache_mgr.validate_cache()
        validate_time = time.perf_counter() - start_time
        print(f"   - validate_cache() time: {validate_time * 1000:.2f}ms")
        print(f"   - Validation result: {validation_result}")

        # Test memory tracking
        memory_usage = cache_mgr.get_memory_usage()
        print(f"   - Memory usage: {memory_usage}")

        memory_after = process.memory_info().rss / 1024 / 1024
        print(f"   - Process memory delta: {memory_after - memory_before:.1f}MB")

        # Test failed attempts tracking
        print("3. Failed Attempts System:")
        start_time = time.perf_counter()
        cache_mgr.clear_failed_attempts()
        clear_time = time.perf_counter() - start_time
        print(f"   - clear_failed_attempts() time: {clear_time * 1000:.2f}ms")

        status = cache_mgr.get_failed_attempts_status()
        print(f"   - Failed attempts status: {len(status)} entries")

    except Exception as e:
        print(f"   ERROR in cache analysis: {e}")


def analyze_shot_model_performance():
    """Analyze ShotItemModel performance."""
    print("\n=== SHOT ITEM MODEL PERFORMANCE ANALYSIS ===")

    try:
        from shot_item_model import ShotItemModel, ShotRole
        from shot_model import Shot

        # Create test shots
        test_shots = []
        for i in range(100):
            shot = Shot(
                show=f"show_{i // 10}",
                sequence=f"seq_{i // 10}",
                shot=f"shot_{i:03d}",
                workspace_path=f"/fake/path/show_{i // 10}/seq_{i // 10}/shot_{i:03d}",
            )
            test_shots.append(shot)

        print("1. Model Creation:")
        start_time = time.perf_counter()
        model = ShotItemModel()
        create_time = time.perf_counter() - start_time
        print(f"   - Model creation time: {create_time * 1000:.2f}ms")

        print("2. Setting Shots:")
        start_time = time.perf_counter()
        model.set_shots(test_shots)
        set_time = time.perf_counter() - start_time
        print(f"   - set_shots() time for 100 shots: {set_time * 1000:.2f}ms")

        print("3. Data Access:")
        # Test data() method performance
        start_time = time.perf_counter()
        for i in range(50):  # Test first 50
            index = model.index(i, 0)
            model.data(index, MockQt.ItemDataRole.DisplayRole)
            model.data(index, ShotRole.ShotObjectRole)
        access_time = time.perf_counter() - start_time
        print(f"   - data() calls for 50 items: {access_time * 1000:.2f}ms")
        print(f"   - Average per item: {access_time * 1000 / 50:.2f}ms")

        print("4. Memory Usage:")
        process = psutil.Process()
        memory = process.memory_info().rss / 1024 / 1024
        print(f"   - Process memory with 100 shots: {memory:.1f}MB")

        # Test thumbnail cache
        print("5. Thumbnail Cache:")
        model.clear_thumbnail_cache()
        print("   - Thumbnail cache cleared")

    except Exception as e:
        print(f"   ERROR in shot model analysis: {e}")


def analyze_process_pool_performance():
    """Analyze ProcessPoolManager performance."""
    print("\n=== PROCESS POOL MANAGER PERFORMANCE ANALYSIS ===")

    try:
        # Import will fail due to threading complexity in mocked environment
        # But we can analyze the code structure

        print("1. Code Complexity Analysis:")
        with open("process_pool_manager.py", "r") as f:
            lines = f.readlines()

        total_lines = len(lines)
        class_count = sum(1 for line in lines if line.strip().startswith("class "))
        method_count = sum(1 for line in lines if line.strip().startswith("def "))
        comment_lines = sum(1 for line in lines if line.strip().startswith("#"))

        print(f"   - Total lines: {total_lines}")
        print(f"   - Classes: {class_count}")
        print(f"   - Methods: {method_count}")
        print(f"   - Comment lines: {comment_lines}")
        print(f"   - Comment ratio: {comment_lines / total_lines * 100:.1f}%")

        # Analyze complexity patterns
        print("2. Complexity Patterns:")
        thread_patterns = sum(
            1 for line in lines if "threading" in line or "Thread" in line
        )
        subprocess_patterns = sum(
            1 for line in lines if "subprocess" in line or "Popen" in line
        )
        time_sleep_patterns = sum(1 for line in lines if "time.sleep" in line)
        exception_patterns = sum(
            1 for line in lines if "except" in line or "raise" in line
        )

        print(f"   - Threading references: {thread_patterns}")
        print(f"   - Subprocess references: {subprocess_patterns}")
        print(f"   - time.sleep() calls: {time_sleep_patterns}")
        print(f"   - Exception handling: {exception_patterns}")

    except Exception as e:
        print(f"   ERROR in process pool analysis: {e}")


def analyze_file_sizes():
    """Analyze codebase file sizes and complexity."""
    print("\n=== CODEBASE SIZE ANALYSIS ===")

    py_files = list(Path(".").glob("*.py"))
    py_files.extend(Path("tests").rglob("*.py"))

    file_stats = []
    for file_path in py_files:
        if file_path.is_file():
            try:
                lines = len(file_path.read_text().splitlines())
                size = file_path.stat().st_size
                file_stats.append((str(file_path), lines, size))
            except (OSError, UnicodeDecodeError):
                pass

    file_stats.sort(key=lambda x: x[1], reverse=True)

    print("Largest Python files by line count:")
    for i, (path, lines, size) in enumerate(file_stats[:10]):
        print(f"   {i + 1:2d}. {path:40s} {lines:4d} lines ({size:6d} bytes)")

    # Test file analysis
    test_files = [f for f in file_stats if "test_" in f[0] or "/test" in f[0]]
    total_test_lines = sum(lines for _, lines, _ in test_files)
    print("\nTest suite statistics:")
    print(f"   - Test files: {len(test_files)}")
    print(f"   - Total test lines: {total_test_lines}")
    print(f"   - Average lines per test: {total_test_lines / len(test_files):.1f}")


def run_micro_benchmarks():
    """Run micro-benchmarks on key operations."""
    print("\n=== MICRO-BENCHMARKS ===")

    print("1. File System Operations:")
    # Test Path operations
    start_time = time.perf_counter()
    for i in range(1000):
        p = Path(f"/tmp/test_{i}.txt")
        p.exists()
    path_time = time.perf_counter() - start_time
    print(f"   - 1000 Path.exists() calls: {path_time * 1000:.2f}ms")

    print("2. String Operations:")
    # Test string operations common in the codebase
    test_strings = [
        f"show_01/seq_{i:03d}/shot_{j:04d}" for i in range(10) for j in range(10)
    ]

    start_time = time.perf_counter()
    for s in test_strings:
        parts = s.split("/")
        "_".join(parts)
    string_time = time.perf_counter() - start_time
    print(f"   - 100 string split/join operations: {string_time * 1000:.2f}ms")

    print("3. Threading Overhead:")

    # Test threading creation overhead
    def dummy_work():
        time.sleep(0.001)  # 1ms work

    start_time = time.perf_counter()
    threads = []
    for i in range(10):
        t = threading.Thread(target=dummy_work)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    threading_time = time.perf_counter() - start_time
    print(f"   - 10 thread create/join cycle: {threading_time * 1000:.2f}ms")


if __name__ == "__main__":
    print("ShotBot Performance Analysis")
    print("=" * 50)

    # System info
    print(f"Python version: {sys.version}")
    print(f"CPU count: {psutil.cpu_count()}")
    print(f"Memory: {psutil.virtual_memory().total / 1024**3:.1f}GB")

    # Run analyses
    analyze_file_sizes()
    run_micro_benchmarks()
    analyze_cache_manager_performance()
    analyze_shot_model_performance()
    analyze_process_pool_performance()

    print("\nAnalysis complete!")
