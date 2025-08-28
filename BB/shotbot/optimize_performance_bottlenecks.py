#!/usr/bin/env python3
"""Optimize identified performance bottlenecks from Week 2 type safety analysis.

This script implements and tests optimizations for:
1. Thread safety overhead (883% degradation)
2. Memory structure overhead (325% increase)  
3. Cache initialization bottlenecks
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

# Set minimal environment
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_LOGGING_RULES"] = "*.debug=false"

from type_definitions import ShotDict

# ============================================================================
# Optimization 1: Lightweight data structures with __slots__
# ============================================================================

@dataclass(slots=True)
class ShotSlots:
    """Memory-optimized shot representation using __slots__."""
    show: str
    sequence: str
    shot: str
    workspace_path: str


@dataclass(slots=True)  
class CacheMetricsSlots:
    """Memory-optimized cache metrics using __slots__."""
    total_size_bytes: int
    item_count: int
    hit_rate: float = 0.0
    miss_rate: float = 0.0
    eviction_count: int = 0
    last_cleanup: float = field(default_factory=time.time)


# ============================================================================
# Optimization 2: Read-Write Lock for reduced contention
# ============================================================================

class ReadWriteLock:
    """Read-write lock to reduce contention in read-heavy workloads."""
    
    def __init__(self):
        self._read_ready = threading.Condition(threading.RLock())
        self._readers = 0
    
    def acquire_read(self):
        """Acquire read lock."""
        with self._read_ready:
            self._readers += 1
    
    def release_read(self):
        """Release read lock.""" 
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notifyAll()
    
    def acquire_write(self):
        """Acquire write lock."""
        self._read_ready.acquire()
        while self._readers > 0:
            self._read_ready.wait()
    
    def release_write(self):
        """Release write lock."""
        self._read_ready.release()


class OptimizedMemoryManager:
    """Memory manager optimized for read-heavy workloads."""
    
    def __init__(self, max_memory_mb: int = 100):
        self._rwlock = ReadWriteLock()
        self._memory_usage_bytes = 0
        self._cached_items: dict[str, int] = {}
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
    
    def track_item(self, path: str, size_bytes: int) -> bool:
        """Track item with write lock."""
        self._rwlock.acquire_write()
        try:
            old_size = self._cached_items.get(path, 0)
            self._cached_items[path] = size_bytes
            self._memory_usage_bytes += size_bytes - old_size
            return True
        finally:
            self._rwlock.release_write()
    
    def is_item_tracked(self, path: str) -> bool:
        """Check if item is tracked with read lock."""
        self._rwlock.acquire_read()
        try:
            return path in self._cached_items
        finally:
            self._rwlock.release_read()
    
    def get_usage_bytes(self) -> int:
        """Get usage with read lock."""
        self._rwlock.acquire_read()
        try:
            return self._memory_usage_bytes
        finally:
            self._rwlock.release_read()


# ============================================================================
# Optimization 3: Batched operations to reduce lock contention
# ============================================================================

class BatchedCacheManager:
    """Cache manager that batches operations to reduce lock contention."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._shots: list[ShotSlots] = []
        self._pending_batch: list[ShotSlots] = []
        self._batch_size = 50
        
    def add_shot(self, shot: ShotSlots) -> None:
        """Add shot to pending batch."""
        self._pending_batch.append(shot)
        
        if len(self._pending_batch) >= self._batch_size:
            self._flush_batch()
    
    def _flush_batch(self) -> None:
        """Flush pending batch with single lock acquisition."""
        if not self._pending_batch:
            return
            
        with self._lock:
            self._shots.extend(self._pending_batch)
            self._pending_batch.clear()
    
    def get_shots(self) -> list[ShotSlots]:
        """Get all shots, flushing pending batch first."""
        self._flush_batch()
        with self._lock:
            return self._shots.copy()


# ============================================================================
# Performance Testing Functions
# ============================================================================

def test_slots_memory_optimization():
    """Test memory savings from __slots__."""
    print("Testing __slots__ memory optimization...")
    
    import tracemalloc
    
    # Test TypedDict approach
    tracemalloc.start()
    typed_shots = []
    for i in range(10000):
        shot: ShotDict = {
            "show": f"SHOW_{i}",
            "sequence": f"seq{i:02d}",
            "shot": f"{i:04d}",
            "workspace_path": f"/shows/SHOW_{i}/seq{i:02d}/{i:04d}"
        }
        typed_shots.append(shot)
    typed_memory = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    # Test slots approach
    tracemalloc.start()
    slots_shots = []
    for i in range(10000):
        shot = ShotSlots(
            show=f"SHOW_{i}",
            sequence=f"seq{i:02d}",
            shot=f"{i:04d}",
            workspace_path=f"/shows/SHOW_{i}/seq{i:02d}/{i:04d}"
        )
        slots_shots.append(shot)
    slots_memory = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    savings_percent = ((typed_memory - slots_memory) / typed_memory) * 100
    
    return {
        "typed_memory_bytes": typed_memory,
        "slots_memory_bytes": slots_memory,
        "memory_savings_percent": savings_percent,
        "memory_savings_bytes": typed_memory - slots_memory
    }


def test_rwlock_performance():
    """Test read-write lock performance vs regular lock."""
    print("Testing read-write lock performance...")
    
    iterations = 50000
    num_readers = 8
    num_writers = 2
    
    # Test regular lock (baseline from original analysis)
    from cache.memory_manager import MemoryManager
    
    regular_mgr = MemoryManager()
    
    def read_worker_regular(count: int):
        for _ in range(count):
            regular_mgr.is_item_tracked(Path("/test/path"))
    
    def write_worker_regular(count: int):
        for i in range(count):
            regular_mgr.track_item(Path(f"/test/path_{i}"), 1024)
    
    # Benchmark regular lock
    start = time.perf_counter()
    threads = []
    
    # Start reader threads
    reads_per_thread = iterations // num_readers
    for i in range(num_readers):
        thread = threading.Thread(target=read_worker_regular, args=(reads_per_thread,))
        threads.append(thread)
        thread.start()
    
    # Start writer threads  
    writes_per_thread = 100  # Fewer writes
    for i in range(num_writers):
        thread = threading.Thread(target=write_worker_regular, args=(writes_per_thread,))
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    regular_time = time.perf_counter() - start
    
    # Test optimized read-write lock
    optimized_mgr = OptimizedMemoryManager()
    
    def read_worker_optimized(count: int):
        for _ in range(count):
            optimized_mgr.is_item_tracked("/test/path")
    
    def write_worker_optimized(count: int):
        for i in range(count):
            optimized_mgr.track_item(f"/test/path_{i}", 1024)
    
    # Benchmark read-write lock
    start = time.perf_counter()
    threads = []
    
    # Start reader threads
    for i in range(num_readers):
        thread = threading.Thread(target=read_worker_optimized, args=(reads_per_thread,))
        threads.append(thread)
        thread.start()
    
    # Start writer threads
    for i in range(num_writers):
        thread = threading.Thread(target=write_worker_optimized, args=(writes_per_thread,))
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    optimized_time = time.perf_counter() - start
    
    improvement_percent = ((regular_time - optimized_time) / regular_time) * 100
    
    return {
        "regular_lock_time": regular_time,
        "rwlock_time": optimized_time,
        "improvement_percent": improvement_percent,
        "total_operations": iterations + (num_writers * writes_per_thread),
        "ops_per_second_regular": (iterations + (num_writers * writes_per_thread)) / regular_time,
        "ops_per_second_optimized": (iterations + (num_writers * writes_per_thread)) / optimized_time
    }


def test_batched_operations():
    """Test batched operations performance."""
    print("Testing batched operations performance...")
    
    iterations = 10000
    
    # Test individual operations (simulating original approach)
    individual_mgr = BatchedCacheManager()
    individual_mgr._batch_size = 1  # Force immediate flush
    
    start = time.perf_counter()
    for i in range(iterations):
        shot = ShotSlots(
            show=f"SHOW_{i}",
            sequence=f"seq{i:02d}",
            shot=f"{i:04d}",
            workspace_path=f"/path/{i}"
        )
        individual_mgr.add_shot(shot)
    individual_time = time.perf_counter() - start
    
    # Test batched operations
    batched_mgr = BatchedCacheManager()  # Default batch size = 50
    
    start = time.perf_counter()
    for i in range(iterations):
        shot = ShotSlots(
            show=f"SHOW_{i}",
            sequence=f"seq{i:02d}",  
            shot=f"{i:04d}",
            workspace_path=f"/path/{i}"
        )
        batched_mgr.add_shot(shot)
    
    # Flush any remaining
    batched_mgr._flush_batch()
    batched_time = time.perf_counter() - start
    
    improvement_percent = ((individual_time - batched_time) / individual_time) * 100
    
    return {
        "individual_operations_time": individual_time,
        "batched_operations_time": batched_time,
        "improvement_percent": improvement_percent,
        "operations": iterations,
        "ops_per_second_individual": iterations / individual_time,
        "ops_per_second_batched": iterations / batched_time
    }


def test_startup_optimization():
    """Test optimized startup performance."""
    print("Testing startup optimization...")
    
    from cache_manager import CacheManager
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir)
        
        # Baseline: Original cache manager
        start = time.perf_counter()
        original_cache = CacheManager(cache_dir=cache_dir)
        original_init_time = time.perf_counter() - start
        
        # Test with pre-warmed data (optimization strategy)
        start = time.perf_counter()
        
        # Simulate pre-warming by creating cache files
        shots_file = cache_dir / "shots.json"
        shots_file.parent.mkdir(parents=True, exist_ok=True)
        
        prewarmed_shots = [
            {
                "show": f"CACHED_{i}",
                "sequence": f"seq{i:02d}",
                "shot": f"{i:04d}",
                "workspace_path": f"/cached/path_{i}"
            }
            for i in range(10)
        ]
        
        # Write cache data
        cache_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "count": len(prewarmed_shots),
            "data": prewarmed_shots
        }
        
        with open(shots_file, "w") as f:
            json.dump(cache_data, f)
        
        # Now create cache manager (should be faster with existing data)
        optimized_cache = CacheManager(cache_dir=cache_dir)
        optimized_init_time = time.perf_counter() - start
        
        improvement_percent = ((original_init_time - optimized_init_time) / original_init_time) * 100
        
        return {
            "original_init_time": original_init_time,
            "optimized_init_time": optimized_init_time,
            "improvement_percent": improvement_percent,
            "prewarmed_shots": len(prewarmed_shots)
        }


def main():
    """Run performance optimization tests."""
    print("=" * 60)
    print("Performance Optimization Testing")
    print("=" * 60)
    
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "optimization_version": "1.0"
    }
    
    # Test 1: __slots__ memory optimization
    print("\n1. __slots__ Memory Optimization")
    print("-" * 40)
    slots_results = test_slots_memory_optimization()
    results["slots_optimization"] = slots_results
    
    print(f"   Memory savings: {slots_results['memory_savings_percent']:.1f}%")
    print(f"   Bytes saved: {slots_results['memory_savings_bytes']:,}")
    
    # Test 2: Read-write lock optimization
    print("\n2. Read-Write Lock Optimization")
    print("-" * 40)
    rwlock_results = test_rwlock_performance()
    results["rwlock_optimization"] = rwlock_results
    
    print(f"   Performance improvement: {rwlock_results['improvement_percent']:.1f}%")
    print(f"   Ops/sec improvement: {rwlock_results['ops_per_second_optimized'] - rwlock_results['ops_per_second_regular']:,.0f}")
    
    # Test 3: Batched operations
    print("\n3. Batched Operations Optimization")
    print("-" * 40)
    batch_results = test_batched_operations()
    results["batch_optimization"] = batch_results
    
    print(f"   Performance improvement: {batch_results['improvement_percent']:.1f}%")
    print(f"   Ops/sec improvement: {batch_results['ops_per_second_batched'] - batch_results['ops_per_second_individual']:,.0f}")
    
    # Test 4: Startup optimization
    print("\n4. Startup Time Optimization")
    print("-" * 40)
    startup_results = test_startup_optimization()
    results["startup_optimization"] = startup_results
    
    print(f"   Startup improvement: {startup_results['improvement_percent']:.1f}%")
    print(f"   Time saved: {(startup_results['original_init_time'] - startup_results['optimized_init_time']) * 1000:.1f}ms")
    
    # Combined impact analysis
    print("\n" + "=" * 60)
    print("Combined Optimization Impact")
    print("=" * 60)
    
    memory_savings = slots_results['memory_savings_percent']
    thread_improvement = rwlock_results['improvement_percent']
    batch_improvement = batch_results['improvement_percent']
    startup_improvement = startup_results['improvement_percent']
    
    print("\nOptimization Results:")
    print(f"  Memory usage: -{memory_savings:.1f}% ({slots_results['memory_savings_bytes']:,} bytes saved)")
    print(f"  Thread contention: +{thread_improvement:.1f}% performance gain")
    print(f"  Batch operations: +{batch_improvement:.1f}% performance gain")  
    print(f"  Startup time: +{startup_improvement:.1f}% faster initialization")
    
    # Overall recommendations
    print("\nImplementation Priority:")
    
    if memory_savings > 20:
        print("  🔥 HIGH: Implement __slots__ for data classes (major memory savings)")
    if thread_improvement > 50:
        print("  🔥 HIGH: Implement read-write locks (major performance gain)")
    if batch_improvement > 30:
        print("  🟡 MEDIUM: Implement batched operations (good performance gain)")
    if startup_improvement > 10:
        print("  🟡 MEDIUM: Implement cache pre-warming (faster startup)")
    
    expected_overall_improvement = (thread_improvement + batch_improvement) / 2
    print(f"\nExpected overall performance improvement: +{expected_overall_improvement:.1f}%")
    print(f"Expected memory reduction: -{memory_savings:.1f}%")
    
    # Save results
    output_file = "performance_optimizations.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nDetailed results saved to: {output_file}")
    
    return results


if __name__ == "__main__":
    main()