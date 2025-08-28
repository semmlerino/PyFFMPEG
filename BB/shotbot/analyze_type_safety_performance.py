#!/usr/bin/env python3
"""Analyze performance impacts of Week 2 type safety changes.

This script measures the specific performance overhead introduced by:
1. TypedDict structures vs plain dictionaries
2. Modular cache architecture vs monolithic approach
3. Thread safety mechanisms in new components
4. Memory usage patterns with new type definitions
"""

from __future__ import annotations

import cProfile
import json
import os
import pstats
import tempfile
import threading
import time
import tracemalloc
from pathlib import Path
from typing import List

# Set minimal environment
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_LOGGING_RULES"] = "*.debug=false"

# Import type definitions for testing
from type_definitions import CacheMetricsDict, ShotDict, ThreeDESceneDict


def profile_typeddict_overhead():
    """Profile TypedDict overhead vs plain dictionaries."""
    print("Profiling TypedDict vs plain dict performance...")
    
    results = {}
    iterations = 100000
    
    # Test plain dict creation
    start = time.perf_counter()
    plain_dicts = []
    for i in range(iterations):
        plain_dict = {
            "show": f"SHOW_{i}",
            "sequence": f"seq{i:02d}",
            "shot": f"{i:04d}",
            "workspace_path": f"/shows/SHOW_{i}/seq{i:02d}/{i:04d}"
        }
        plain_dicts.append(plain_dict)
    plain_time = time.perf_counter() - start
    
    # Test TypedDict creation
    start = time.perf_counter()
    typed_dicts: list[ShotDict] = []
    for i in range(iterations):
        shot_dict: ShotDict = {
            "show": f"SHOW_{i}",
            "sequence": f"seq{i:02d}",
            "shot": f"{i:04d}",
            "workspace_path": f"/shows/SHOW_{i}/seq{i:02d}/{i:04d}"
        }
        typed_dicts.append(shot_dict)
    typed_time = time.perf_counter() - start
    
    # Test access patterns
    start = time.perf_counter()
    plain_accesses = [d["show"] for d in plain_dicts[:1000]]
    plain_access_time = time.perf_counter() - start
    
    start = time.perf_counter()
    typed_accesses = [d["show"] for d in typed_dicts[:1000]]
    typed_access_time = time.perf_counter() - start
    
    results = {
        "iterations": iterations,
        "plain_dict_creation_time": plain_time,
        "typed_dict_creation_time": typed_time,
        "creation_overhead_percent": ((typed_time - plain_time) / plain_time) * 100,
        "plain_access_time": plain_access_time,
        "typed_access_time": typed_access_time,
        "access_overhead_percent": ((typed_access_time - plain_access_time) / plain_access_time) * 100
    }
    
    # Memory usage comparison
    tracemalloc.start()
    _ = [{"show": f"SHOW_{i}", "sequence": f"seq{i:02d}", "shot": f"{i:04d}", "workspace_path": "/path"} for i in range(10000)]
    plain_memory = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    tracemalloc.start()
    _ = [ShotDict({"show": f"SHOW_{i}", "sequence": f"seq{i:02d}", "shot": f"{i:04d}", "workspace_path": "/path"}) for i in range(10000)]
    typed_memory = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    results["plain_memory_bytes"] = plain_memory
    results["typed_memory_bytes"] = typed_memory
    results["memory_overhead_percent"] = ((typed_memory - plain_memory) / plain_memory) * 100
    
    return results


def profile_cache_architecture():
    """Profile modular cache architecture vs monolithic approach."""
    print("Profiling modular cache architecture performance...")
    
    from cache.memory_manager import MemoryManager
    from cache.shot_cache import ShotCache
    from cache.storage_backend import StorageBackend
    from cache_manager import CacheManager
    
    results = {}
    
    # Profile CacheManager initialization
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir)
        
        # Time full CacheManager creation (modular)
        start = time.perf_counter()
        cache_manager = CacheManager(cache_dir=cache_dir)
        modular_init_time = time.perf_counter() - start
        
        # Time individual component creation
        start = time.perf_counter()
        storage = StorageBackend()
        storage_time = time.perf_counter() - start
        
        start = time.perf_counter()
        memory_mgr = MemoryManager()
        memory_time = time.perf_counter() - start
        
        start = time.perf_counter()
        shot_cache = ShotCache(cache_dir / "shots.json", storage)
        shot_cache_time = time.perf_counter() - start
        
        results = {
            "modular_init_time": modular_init_time,
            "storage_backend_time": storage_time,
            "memory_manager_time": memory_time,
            "shot_cache_time": shot_cache_time,
            "total_component_time": storage_time + memory_time + shot_cache_time
        }
        
        # Test cache operations
        test_shots = [
            ShotDict({
                "show": f"TEST_{i}",
                "sequence": f"seq{i:02d}",
                "shot": f"{i:04d}",
                "workspace_path": f"/test/path_{i}"
            })
            for i in range(100)
        ]
        
        # Time caching operation
        start = time.perf_counter()
        cache_manager.cache_shots(test_shots)
        cache_operation_time = time.perf_counter() - start
        
        # Time retrieval operation
        start = time.perf_counter()
        retrieved_shots = cache_manager.get_cached_shots()
        retrieval_time = time.perf_counter() - start
        
        results["cache_operation_time"] = cache_operation_time
        results["retrieval_time"] = retrieval_time
        results["shots_cached"] = len(test_shots)
        results["shots_retrieved"] = len(retrieved_shots) if retrieved_shots else 0
    
    return results


def profile_thread_safety_overhead():
    """Profile thread safety mechanisms in new cache components."""
    print("Profiling thread safety overhead...")
    
    from cache.memory_manager import MemoryManager
    from cache.storage_backend import StorageBackend
    
    results = {}
    iterations = 10000
    
    # Create components
    memory_mgr = MemoryManager()
    storage = StorageBackend()
    
    # Profile single-threaded memory manager operations
    with tempfile.TemporaryDirectory() as tmpdir:
        test_files = [Path(tmpdir) / f"test_{i}.txt" for i in range(100)]
        for f in test_files:
            f.write_text("test data")
        
        start = time.perf_counter()
        for i in range(iterations):
            memory_mgr.track_item(test_files[i % len(test_files)])
        single_thread_time = time.perf_counter() - start
        
        # Clear tracking
        memory_mgr.clear_all_tracking()
        
        # Profile multi-threaded operations
        def worker(start_idx: int, count: int):
            for i in range(start_idx, start_idx + count):
                memory_mgr.track_item(test_files[i % len(test_files)])
        
        num_threads = 4
        operations_per_thread = iterations // num_threads
        
        start = time.perf_counter()
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(
                target=worker, 
                args=(i * operations_per_thread, operations_per_thread)
            )
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        multi_thread_time = time.perf_counter() - start
        
        results = {
            "iterations": iterations,
            "single_thread_time": single_thread_time,
            "multi_thread_time": multi_thread_time,
            "thread_safety_overhead_percent": ((multi_thread_time - single_thread_time) / single_thread_time) * 100,
            "operations_per_second_single": iterations / single_thread_time,
            "operations_per_second_multi": iterations / multi_thread_time
        }
    
    return results


def profile_memory_patterns():
    """Profile memory usage patterns with new type definitions."""
    print("Profiling memory usage patterns...")
    
    results = {}
    
    # Profile different data structure patterns
    tracemalloc.start()
    
    # Complex nested structure with TypedDicts
    complex_data = []
    for i in range(1000):
        shot: ShotDict = {
            "show": f"SHOW_{i}",
            "sequence": f"seq{i:02d}",
            "shot": f"{i:04d}",
            "workspace_path": f"/shows/SHOW_{i}/seq{i:02d}/{i:04d}"
        }
        
        scene: ThreeDESceneDict = {
            "filepath": f"/path/to/scene_{i}.3de",
            "show": f"SHOW_{i}",
            "sequence": f"seq{i:02d}",
            "shot": f"{i:04d}",
            "user": f"user_{i}",
            "filename": f"scene_{i}.3de",
            "modified_time": time.time(),
            "workspace_path": f"/workspace/{i}"
        }
        
        metrics: CacheMetricsDict = {
            "total_size_bytes": i * 1024,
            "item_count": i,
            "hit_rate": 0.8,
            "miss_rate": 0.2,
            "eviction_count": 0,
            "last_cleanup": time.time()
        }
        
        complex_data.append({
            "shot": shot,
            "scene": scene, 
            "metrics": metrics
        })
    
    complex_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    # Compare with simple structure
    tracemalloc.start()
    simple_data = []
    for i in range(1000):
        simple_data.append({
            "id": i,
            "name": f"item_{i}",
            "path": f"/path/{i}",
            "size": i * 1024,
            "time": time.time()
        })
    
    simple_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    results = {
        "complex_structure_bytes": complex_memory[0],
        "simple_structure_bytes": simple_memory[0],
        "complex_peak_bytes": complex_memory[1],
        "simple_peak_bytes": simple_memory[1],
        "structure_overhead_percent": ((complex_memory[0] - simple_memory[0]) / simple_memory[0]) * 100,
        "items_tested": 1000
    }
    
    return results


def profile_detailed_cache_operations():
    """Profile detailed cache operations with cProfile."""
    print("Profiling detailed cache operations...")
    
    from cache_manager import CacheManager
    
    results = {}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir)
        
        # Profile cache initialization
        profiler = cProfile.Profile()
        profiler.enable()
        
        cache_manager = CacheManager(cache_dir=cache_dir)
        
        # Perform various operations
        test_shots = [
            ShotDict({
                "show": f"PROF_{i}",
                "sequence": f"seq{i:02d}",
                "shot": f"{i:04d}",
                "workspace_path": f"/profile/test_{i}"
            })
            for i in range(50)
        ]
        
        cache_manager.cache_shots(test_shots)
        cached_shots = cache_manager.get_cached_shots()
        cache_manager.get_memory_usage()
        
        profiler.disable()
        
        # Extract profiling data
        stats = pstats.Stats(profiler)
        stats.sort_stats("cumulative")
        
        # Get top functions
        top_functions = []
        for (file, line, func), (cc, nc, tt, ct, callers) in list(stats.stats.items())[:10]:
            top_functions.append({
                "function": f"{func}:{line}",
                "file": Path(file).name if file else "unknown",
                "cumulative_time": ct,
                "total_time": tt,
                "calls": nc
            })
        
        results = {
            "top_functions": top_functions,
            "total_operations": len(test_shots),
            "cached_successfully": len(cached_shots) if cached_shots else 0
        }
    
    return results


def main():
    """Run comprehensive type safety performance analysis."""
    print("=" * 60)
    print("Week 2 Type Safety Performance Analysis")
    print("=" * 60)
    
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "analysis_version": "1.0"
    }
    
    # 1. TypedDict overhead
    print("\n1. TypedDict Performance Overhead")
    print("-" * 40)
    typeddict_results = profile_typeddict_overhead()
    results["typeddict_analysis"] = typeddict_results
    
    print(f"   Creation overhead: {typeddict_results['creation_overhead_percent']:.2f}%")
    print(f"   Access overhead: {typeddict_results['access_overhead_percent']:.2f}%")
    print(f"   Memory overhead: {typeddict_results['memory_overhead_percent']:.2f}%")
    
    # 2. Cache architecture
    print("\n2. Modular Cache Architecture Performance")
    print("-" * 40)
    cache_results = profile_cache_architecture()
    results["cache_architecture"] = cache_results
    
    print(f"   Modular init time: {cache_results['modular_init_time']:.4f}s")
    print(f"   Cache operation time: {cache_results['cache_operation_time']:.4f}s")
    print(f"   Retrieval time: {cache_results['retrieval_time']:.4f}s")
    
    # 3. Thread safety overhead
    print("\n3. Thread Safety Overhead")
    print("-" * 40)
    thread_results = profile_thread_safety_overhead()
    results["thread_safety"] = thread_results
    
    print(f"   Thread safety overhead: {thread_results['thread_safety_overhead_percent']:.2f}%")
    print(f"   Single-thread ops/sec: {thread_results['operations_per_second_single']:.0f}")
    print(f"   Multi-thread ops/sec: {thread_results['operations_per_second_multi']:.0f}")
    
    # 4. Memory patterns
    print("\n4. Memory Usage Patterns")
    print("-" * 40)
    memory_results = profile_memory_patterns()
    results["memory_patterns"] = memory_results
    
    print(f"   Structure overhead: {memory_results['structure_overhead_percent']:.2f}%")
    print(f"   Complex structure: {memory_results['complex_structure_bytes'] / 1024:.1f}KB")
    print(f"   Simple structure: {memory_results['simple_structure_bytes'] / 1024:.1f}KB")
    
    # 5. Detailed profiling
    print("\n5. Detailed Cache Operations Profiling")
    print("-" * 40)
    detailed_results = profile_detailed_cache_operations()
    results["detailed_profiling"] = detailed_results
    
    if detailed_results["top_functions"]:
        print("   Top time-consuming functions:")
        for func in detailed_results["top_functions"][:3]:
            print(f"     {func['cumulative_time']:.6f}s - {func['function']}")
    
    # Summary and recommendations
    print("\n" + "=" * 60)
    print("Analysis Summary & Recommendations")
    print("=" * 60)
    
    # Calculate overall impact
    creation_impact = typeddict_results['creation_overhead_percent']
    memory_impact = memory_results['structure_overhead_percent']
    thread_impact = thread_results['thread_safety_overhead_percent']
    
    print("\nOverall Performance Impact:")
    print(f"  TypedDict creation overhead: {creation_impact:.1f}%")
    print(f"  Memory structure overhead: {memory_impact:.1f}%")
    print(f"  Thread safety overhead: {thread_impact:.1f}%")
    
    print("\nRecommendations:")
    
    if creation_impact > 5:
        print("  🔴 HIGH: TypedDict creation overhead is significant")
        print("      - Consider lazy typing validation")
        print("      - Use plain dicts in hot paths, convert at boundaries")
    elif creation_impact > 2:
        print("  🟡 MEDIUM: TypedDict overhead is noticeable but manageable")
    else:
        print("  🟢 LOW: TypedDict overhead is minimal")
    
    if memory_impact > 20:
        print("  🔴 HIGH: Memory overhead from complex structures")
        print("      - Consider flattening nested structures")
        print("      - Use __slots__ for frequently created objects")
    elif memory_impact > 10:
        print("  🟡 MEDIUM: Memory overhead is noticeable")
    else:
        print("  🟢 LOW: Memory overhead is acceptable")
        
    if thread_impact > 15:
        print("  🔴 HIGH: Thread safety causing performance degradation")
        print("      - Consider read-write locks for read-heavy workloads")
        print("      - Batch operations to reduce lock contention")
    elif thread_impact > 5:
        print("  🟡 MEDIUM: Thread safety overhead is noticeable")
    else:
        print("  🟢 LOW: Thread safety overhead is minimal")
    
    # Save results
    output_file = "type_safety_performance_analysis.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nDetailed results saved to: {output_file}")
    
    return results


if __name__ == "__main__":
    main()