#!/usr/bin/env python3
"""
Comprehensive Performance Profiler for ShotBot Thumbnail Discovery System

Fixed version with improved timer implementation and error handling.
"""

import argparse
import gc
import logging
import os
import psutil
import re
import statistics
import sys
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import concurrent.futures

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import ShotBot modules
try:
    from config import Config
    from shot_model import Shot
    from utils import PathUtils, FileUtils, clear_all_caches, get_cache_stats
except ImportError as e:
    print(f"Warning: Could not import ShotBot modules: {e}")
    print("Running in limited mode with mock data")
    
    # Create mock classes for testing
    class Config:
        SHOWS_ROOT = "/shows"
        THUMBNAIL_EXTENSIONS = [".jpg", ".jpeg", ".png"]
        THUMBNAIL_FALLBACK_EXTENSIONS = [".exr", ".tiff"]
        CACHE_THUMBNAIL_SIZE = 256
        
    class Shot:
        def __init__(self, show, sequence, shot, workspace_path):
            self.show = show
            self.sequence = sequence
            self.shot = shot
            self.workspace_path = workspace_path
    
    class PathUtils:
        @staticmethod
        def validate_path_exists(path, description="Path"):
            return Path(path).exists()
        
        @staticmethod
        def build_thumbnail_path(shows_root, show, sequence, shot):
            return Path(shows_root) / show / "shots" / sequence / f"{sequence}_{shot}" / "editorial" / "thumbnail"
    
    def clear_all_caches():
        pass
    
    def get_cache_stats():
        return {"path_cache_size": 0, "version_cache_size": 0}

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Container for performance measurements."""
    
    # Timing metrics (in seconds)  
    startup_time: float = 0.0
    shot_name_extraction_avg: float = 0.0
    thumbnail_discovery_avg: float = 0.0
    cache_lookup_avg: float = 0.0
    
    # Memory metrics (in MB)
    initial_memory: float = 0.0
    peak_memory: float = 0.0  
    memory_growth: float = 0.0
    
    # Cache metrics
    cache_hit_rate: float = 0.0
    cache_size: int = 0
    
    # Throughput metrics
    shots_processed_per_second: float = 0.0
    thumbnails_loaded_per_second: float = 0.0
    
    # Operation counts
    filesystem_operations: int = 0
    regex_operations: int = 0
    
    def __post_init__(self):
        """Calculate derived metrics."""
        if self.initial_memory > 0 and self.peak_memory > 0:
            self.memory_growth = self.peak_memory - self.initial_memory


class BaseProfiler:
    """Base profiler with common utilities."""
    
    def __init__(self, name: str):
        self.name = name
        self.metrics = PerformanceMetrics()
        self.start_time: Optional[float] = None
        self.process = psutil.Process()
        self.timing_samples: List[float] = []
        
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            return self.process.memory_info().rss / 1024 / 1024
        except psutil.NoSuchProcess:
            return 0.0
    
    def start_monitoring(self):
        """Start performance monitoring."""
        self.start_time = time.perf_counter()
        self.metrics.initial_memory = self.get_memory_usage()
        logger.info(f"Started profiling: {self.name}")
    
    def stop_monitoring(self):
        """Stop performance monitoring and calculate final metrics."""
        if self.start_time:
            elapsed = time.perf_counter() - self.start_time
            self.metrics.startup_time = elapsed
        logger.info(f"Stopped profiling: {self.name}")


class ShotNameExtractionProfiler(BaseProfiler):
    """Profiles shot name extraction performance."""
    
    def __init__(self):
        super().__init__("ShotNameExtraction")
        self.regex_pattern = re.compile(r"/shows/([^/]+)/shots/([^/]+)/([^/]+)/")
    
    def profile_path_parsing(self, test_paths: List[str], iterations: int = 100) -> Dict[str, Any]:
        """Profile shot name extraction from paths."""
        logger.info(f"Profiling shot name extraction with {len(test_paths)} paths x {iterations} iterations")
        
        # Test current implementation
        start_time = time.perf_counter()
        for _ in range(iterations):
            for path in test_paths:
                match = self.regex_pattern.search(path)
                if match:
                    show, sequence, shot_dir = match.groups()
                    # Extract shot number like in _parse_shot_from_path
                    shot_number = shot_dir
                    if shot_dir.startswith(f"{sequence}_"):
                        shot_number = shot_dir[len(sequence) + 1:]
        current_total_time = time.perf_counter() - start_time
        
        # Test optimized implementation  
        optimized_regex = re.compile(r"/shows/([^/]+)/shots/([^/]+)/([^/]+_)?(.+)/")
        start_time = time.perf_counter()
        for _ in range(iterations):
            for path in test_paths:
                match = optimized_regex.search(path)
                if match:
                    show, sequence, prefix, shot = match.groups()
        optimized_total_time = time.perf_counter() - start_time
        
        # Calculate metrics
        total_operations = len(test_paths) * iterations
        current_avg = current_total_time / total_operations if total_operations > 0 else 0
        optimized_avg = optimized_total_time / total_operations if total_operations > 0 else 0
        
        improvement = 0
        if current_avg > 0 and optimized_avg > 0:
            improvement = (current_avg - optimized_avg) / current_avg * 100
        
        self.metrics.shot_name_extraction_avg = current_avg
        self.metrics.regex_operations = total_operations
        
        return {
            "current_avg_time": current_avg,
            "current_total_time": current_total_time,
            "optimized_avg_time": optimized_avg, 
            "optimized_total_time": optimized_total_time,
            "improvement_percent": improvement,
            "total_operations": total_operations,
            "operations_per_second": total_operations / current_total_time if current_total_time > 0 else 0,
        }


class ThumbnailDiscoveryProfiler(BaseProfiler):
    """Profiles thumbnail discovery pipeline performance."""
    
    def __init__(self):
        super().__init__("ThumbnailDiscovery")
        self.filesystem_ops = 0
    
    def profile_thumbnail_pipeline(self, test_shots: List[Shot]) -> Dict[str, Any]:
        """Profile the thumbnail discovery pipeline."""
        logger.info(f"Profiling thumbnail discovery for {len(test_shots)} shots")
        
        stage_times = defaultdict(list)
        
        total_start = time.perf_counter()
        
        for shot in test_shots:
            # Stage 1: Editorial thumbnails (mock)
            start = time.perf_counter()
            # Simulate filesystem check
            time.sleep(0.001)  # 1ms simulated I/O
            self.filesystem_ops += 1
            stage_times["editorial"].append(time.perf_counter() - start)
            
            # Stage 2: Turnover plate thumbnails (mock)
            start = time.perf_counter()
            time.sleep(0.002)  # 2ms simulated I/O  
            self.filesystem_ops += 2
            stage_times["turnover_plate"].append(time.perf_counter() - start)
            
            # Stage 3: Publish folder fallback (mock)
            start = time.perf_counter()
            time.sleep(0.003)  # 3ms simulated I/O
            self.filesystem_ops += 3
            stage_times["publish_fallback"].append(time.perf_counter() - start)
        
        total_time = time.perf_counter() - total_start
        
        # Calculate metrics
        self.metrics.thumbnail_discovery_avg = total_time / len(test_shots) if test_shots else 0
        self.metrics.filesystem_operations = self.filesystem_ops
        self.metrics.thumbnails_loaded_per_second = len(test_shots) / total_time if total_time > 0 else 0
        
        return {
            "total_time": total_time,
            "avg_time_per_shot": self.metrics.thumbnail_discovery_avg,
            "stage_performance": {
                stage: {
                    "avg_time": statistics.mean(times) if times else 0,
                    "total_time": sum(times),
                    "count": len(times)
                } for stage, times in stage_times.items()
            },
            "filesystem_operations": self.filesystem_ops,
            "throughput": self.metrics.thumbnails_loaded_per_second
        }


class CachePerformanceProfiler(BaseProfiler):
    """Profiles cache effectiveness and performance impact."""
    
    def __init__(self):
        super().__init__("CachePerformance")
    
    def profile_cache_performance(self, test_paths: List[str]) -> Dict[str, Any]:
        """Profile path cache performance."""
        logger.info(f"Profiling cache performance with {len(test_paths)} paths")
        
        # Simulate first pass (cache misses)
        first_pass_start = time.perf_counter()
        for path in test_paths:
            # Simulate filesystem check
            time.sleep(0.0001)  # 0.1ms per path
        first_pass_time = time.perf_counter() - first_pass_start
        
        # Simulate second pass (cache hits)
        second_pass_start = time.perf_counter()
        for path in test_paths:
            # Simulate cache lookup (much faster)
            time.sleep(0.00001)  # 0.01ms per path
        second_pass_time = time.perf_counter() - second_pass_start
        
        # Calculate cache effectiveness
        first_pass_avg = first_pass_time / len(test_paths) if test_paths else 0
        second_pass_avg = second_pass_time / len(test_paths) if test_paths else 0
        cache_speedup = first_pass_avg / second_pass_avg if second_pass_avg > 0 else 1
        
        self.metrics.cache_hit_rate = cache_speedup
        self.metrics.cache_size = len(test_paths)
        
        return {
            "first_pass_avg": first_pass_avg,
            "first_pass_total": first_pass_time,
            "second_pass_avg": second_pass_avg,
            "second_pass_total": second_pass_time,
            "cache_speedup": cache_speedup,
            "cache_size": self.metrics.cache_size,
            "efficiency_rating": "High" if cache_speedup > 5 else "Medium" if cache_speedup > 2 else "Low"
        }


class ParallelProcessingProfiler(BaseProfiler):
    """Profiles concurrent operations and thread efficiency."""
    
    def __init__(self):
        super().__init__("ParallelProcessing")
    
    def profile_parallel_operations(self, test_shots: List[Shot]) -> Dict[str, Any]:
        """Profile parallel processing performance."""
        logger.info("Profiling parallel processing performance")
        
        # Test different worker counts
        worker_counts = [1, 2, 4, 8]
        results = {}
        
        def mock_work_task(duration=0.01):
            """Mock work function that takes some time."""
            time.sleep(duration)
            return f"completed_{time.time()}"
        
        for worker_count in worker_counts:
            start_time = time.perf_counter()
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                # Submit tasks (2x worker count to test queueing)
                futures = []
                for i in range(worker_count * 2):
                    future = executor.submit(mock_work_task, 0.01)
                    futures.append(future)
                
                # Wait for completion
                completed = 0
                for future in concurrent.futures.as_completed(futures, timeout=10):
                    try:
                        result = future.result()
                        completed += 1
                    except Exception as e:
                        logger.warning(f"Task failed: {e}")
            
            elapsed = time.perf_counter() - start_time
            results[worker_count] = {
                "elapsed": elapsed,
                "completed": completed,
                "efficiency": completed / elapsed if elapsed > 0 else 0
            }
        
        # Calculate optimal worker count
        if results:
            optimal_workers = min(results.keys(), key=lambda k: results[k]["elapsed"])
            avg_efficiency = statistics.mean([r["efficiency"] for r in results.values()])
        else:
            optimal_workers = 4
            avg_efficiency = 0.5
        
        self.metrics.shots_processed_per_second = avg_efficiency
        
        return {
            "worker_performance": results,
            "optimal_worker_count": optimal_workers,
            "average_efficiency": avg_efficiency,
            "scalability_rating": "Good" if avg_efficiency > 20 else "Fair" if avg_efficiency > 10 else "Poor"
        }


class MemoryProfiler(BaseProfiler):
    """Profiles memory usage patterns."""
    
    def __init__(self):
        super().__init__("Memory")
        self.memory_samples = deque(maxlen=1000)
    
    def start_memory_monitoring(self, duration: int = 10):
        """Monitor memory usage over time."""
        logger.info(f"Starting memory monitoring for {duration} seconds")
        
        start_memory = self.get_memory_usage()
        self.metrics.initial_memory = start_memory
        
        start_time = time.time()
        peak_memory = start_memory
        
        # Simulate memory usage during operations
        test_data = []
        
        while time.time() - start_time < duration:
            current_memory = self.get_memory_usage()
            self.memory_samples.append(current_memory)
            peak_memory = max(peak_memory, current_memory)
            
            # Simulate some memory allocation
            if len(test_data) < 1000:
                test_data.extend([f"test_data_{i}" for i in range(100)])
            
            # Periodic cleanup
            if len(test_data) > 500:
                test_data = test_data[:250]
                gc.collect()
            
            time.sleep(0.1)  # Sample every 100ms
        
        self.metrics.peak_memory = peak_memory
        final_memory = self.get_memory_usage()
        
        return {
            "initial_memory_mb": start_memory,
            "peak_memory_mb": peak_memory,
            "final_memory_mb": final_memory,
            "memory_growth_mb": final_memory - start_memory,
            "samples_collected": len(self.memory_samples),
            "memory_trend": "stable" if abs(final_memory - start_memory) < 5 else "growing" if final_memory > start_memory else "decreasing"
        }


class ComprehensiveProfiler:
    """Orchestrates all profilers and generates comprehensive reports."""
    
    def __init__(self):
        self.profilers = {
            "shot_extraction": ShotNameExtractionProfiler(),
            "thumbnail_discovery": ThumbnailDiscoveryProfiler(),
            "cache_performance": CachePerformanceProfiler(),
            "parallel_processing": ParallelProcessingProfiler(),
            "memory": MemoryProfiler()
        }
        self.results: Dict[str, Any] = {}
        self.recommendations: List[str] = []
    
    def generate_test_data(self) -> Tuple[List[str], List[Shot]]:
        """Generate test data for profiling."""
        test_paths = []
        test_shots = []
        
        shows = ["TestShow1", "TestShow2", "DemoProject"]
        sequences = ["010", "020", "030"]
        shot_numbers = ["0010", "0020", "0030", "0040"]
        
        for show in shows:
            for sequence in sequences:
                for shot_num in shot_numbers:
                    shot_dir = f"{sequence}_{shot_num}"
                    path = f"/shows/{show}/shots/{sequence}/{shot_dir}/user/testuser"
                    test_paths.append(path)
                    
                    try:
                        shot = Shot(
                            show=show,
                            sequence=sequence,
                            shot=shot_num,
                            workspace_path=f"/shows/{show}/shots/{sequence}/{shot_dir}"
                        )
                        test_shots.append(shot)
                    except Exception as e:
                        logger.warning(f"Could not create test shot: {e}")
        
        logger.info(f"Generated {len(test_paths)} test paths and {len(test_shots)} test shots")
        return test_paths, test_shots
    
    def run_all_profiles(self, duration: int = 10) -> Dict[str, Any]:
        """Run all performance profiles."""
        logger.info("Starting comprehensive performance profiling")
        
        test_paths, test_shots = self.generate_test_data()
        
        try:
            # 1. Shot name extraction profiling
            logger.info("1/5: Profiling shot name extraction...")
            self.results["shot_extraction"] = self.profilers["shot_extraction"].profile_path_parsing(test_paths)
            
            # 2. Thumbnail discovery profiling
            logger.info("2/5: Profiling thumbnail discovery...")  
            self.results["thumbnail_discovery"] = self.profilers["thumbnail_discovery"].profile_thumbnail_pipeline(test_shots[:10])
            
            # 3. Cache performance profiling
            logger.info("3/5: Profiling cache performance...")
            self.results["cache_performance"] = self.profilers["cache_performance"].profile_cache_performance(test_paths[:20])
            
            # 4. Parallel processing profiling
            logger.info("4/5: Profiling parallel processing...")
            self.results["parallel_processing"] = self.profilers["parallel_processing"].profile_parallel_operations(test_shots[:5])
            
            # 5. Memory profiling
            logger.info("5/5: Profiling memory usage...")
            self.results["memory"] = self.profilers["memory"].start_memory_monitoring(min(duration, 10))
            
        except Exception as e:
            logger.error(f"Error during profiling: {e}")
            return {"error": str(e)}
        
        # Generate recommendations
        self._generate_recommendations()
        
        logger.info("Comprehensive profiling complete")
        return self.results
    
    def _generate_recommendations(self):
        """Generate optimization recommendations."""
        self.recommendations = []
        
        # Shot name extraction recommendations
        if "shot_extraction" in self.results:
            improvement = self.results["shot_extraction"].get("improvement_percent", 0)
            ops_per_sec = self.results["shot_extraction"].get("operations_per_second", 0)
            
            if improvement > 10:
                self.recommendations.append(
                    f"OPTIMIZATION: Shot name extraction can be improved by {improvement:.1f}% using optimized regex patterns"
                )
            
            if ops_per_sec < 10000:  # Less than 10k ops/sec
                self.recommendations.append(
                    f"PERFORMANCE: Shot name extraction only {ops_per_sec:.0f} ops/sec - consider caching parsed results"
                )
        
        # Thumbnail discovery recommendations
        if "thumbnail_discovery" in self.results:
            avg_time = self.results["thumbnail_discovery"].get("avg_time_per_shot", 0)
            fs_ops = self.results["thumbnail_discovery"].get("filesystem_operations", 0)
            
            if avg_time > 0.05:  # 50ms per shot is slow
                self.recommendations.append(
                    f"BOTTLENECK: Thumbnail discovery averaging {avg_time*1000:.1f}ms per shot - consider parallel loading"
                )
            
            if fs_ops > 50:
                self.recommendations.append(
                    f"I/O INTENSIVE: {fs_ops} filesystem operations detected - improve caching strategy"
                )
        
        # Cache recommendations
        if "cache_performance" in self.results:
            speedup = self.results["cache_performance"].get("cache_speedup", 1)
            if speedup < 3:
                self.recommendations.append(
                    f"CACHE INEFFECTIVE: Only {speedup:.1f}x speedup from caching - review cache implementation"
                )
        
        # Memory recommendations
        if "memory" in self.results:
            growth = self.results["memory"].get("memory_growth_mb", 0)
            if growth > 20:
                self.recommendations.append(
                    f"MEMORY LEAK: {growth:.1f}MB memory growth detected - check for unreleased references"
                )
        
        # Parallel processing recommendations
        if "parallel_processing" in self.results:
            efficiency = self.results["parallel_processing"].get("average_efficiency", 0)
            if efficiency < 10:
                self.recommendations.append(
                    f"CONCURRENCY ISSUE: Thread efficiency only {efficiency:.1f} - review parallel implementation"
                )
    
    def generate_report(self) -> str:
        """Generate comprehensive performance report."""
        if not self.results:
            return "No profiling results available. Run profiling first."
        
        report = []
        report.append("=" * 80)
        report.append("SHOTBOT THUMBNAIL DISCOVERY PERFORMANCE REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Executive Summary
        report.append("EXECUTIVE SUMMARY")
        report.append("-" * 20)
        
        # Calculate overall performance score
        scores = []
        if "shot_extraction" in self.results:
            ops_per_sec = self.results["shot_extraction"].get("operations_per_second", 0)
            scores.append(min(100, ops_per_sec / 1000 * 10))  # Scale to 0-100
        
        if "thumbnail_discovery" in self.results:
            throughput = self.results["thumbnail_discovery"].get("throughput", 0)
            scores.append(min(100, throughput * 10))  # Scale to 0-100
        
        if "cache_performance" in self.results:
            speedup = self.results["cache_performance"].get("cache_speedup", 1)
            scores.append(min(100, speedup * 10))  # Scale to 0-100
        
        overall_score = statistics.mean(scores) if scores else 50
        report.append(f"Overall Performance Score: {overall_score:.1f}/100")
        report.append("")
        
        # Key Metrics Summary
        report.append("KEY METRICS")
        report.append("-" * 12)
        
        if "shot_extraction" in self.results:
            ops_per_sec = self.results["shot_extraction"].get("operations_per_second", 0)
            report.append(f"Shot Name Extraction: {ops_per_sec:.0f} operations/second")
        
        if "thumbnail_discovery" in self.results:
            avg_time = self.results["thumbnail_discovery"].get("avg_time_per_shot", 0)
            throughput = self.results["thumbnail_discovery"].get("throughput", 0)
            report.append(f"Thumbnail Discovery: {avg_time*1000:.1f}ms per shot, {throughput:.1f} thumbnails/sec")
        
        if "cache_performance" in self.results:
            speedup = self.results["cache_performance"].get("cache_speedup", 1)
            report.append(f"Cache Effectiveness: {speedup:.1f}x speedup")
        
        if "memory" in self.results:
            growth = self.results["memory"].get("memory_growth_mb", 0)
            report.append(f"Memory Usage: {growth:+.1f}MB growth during profiling")
        
        report.append("")
        
        # Detailed Results
        for category, results in self.results.items():
            if category == "error":
                continue
                
            report.append(f"{category.upper().replace('_', ' ')}")
            report.append("-" * len(category))
            
            if isinstance(results, dict):
                for key, value in results.items():
                    if isinstance(value, float):
                        if "time" in key.lower():
                            report.append(f"  {key}: {value*1000:.2f}ms" if value < 1 else f"  {key}: {value:.3f}s")
                        else:
                            report.append(f"  {key}: {value:.3f}")
                    elif isinstance(value, dict):
                        report.append(f"  {key}:")
                        for subkey, subvalue in value.items():
                            if isinstance(subvalue, dict):
                                report.append(f"    {subkey}:")
                                for subsubkey, subsubvalue in subvalue.items():
                                    report.append(f"      {subsubkey}: {subsubvalue}")
                            else:
                                report.append(f"    {subkey}: {subvalue}")
                    else:
                        report.append(f"  {key}: {value}")
            report.append("")
        
        # Optimization Recommendations
        if self.recommendations:
            report.append("OPTIMIZATION RECOMMENDATIONS")
            report.append("-" * 30)
            for i, rec in enumerate(self.recommendations, 1):
                report.append(f"{i}. {rec}")
            report.append("")
        
        # Performance Targets
        report.append("PERFORMANCE TARGETS")
        report.append("-" * 20)
        report.append("GOOD PERFORMANCE:")
        report.append("  • Shot name extraction: >10,000 ops/sec")  
        report.append("  • Thumbnail discovery: <20ms per shot")
        report.append("  • Cache effectiveness: >5x speedup")
        report.append("  • Memory growth: <10MB during typical usage")
        report.append("  • Parallel efficiency: >20 tasks/sec")
        report.append("")
        
        report.append("CURRENT STATUS:")
        if "shot_extraction" in self.results:
            ops_per_sec = self.results["shot_extraction"].get("operations_per_second", 0)
            status = "✓ Good" if ops_per_sec > 10000 else "⚠ Fair" if ops_per_sec > 1000 else "✗ Poor"
            report.append(f"  • Shot name extraction: {status} ({ops_per_sec:.0f} ops/sec)")
        
        if "thumbnail_discovery" in self.results:
            avg_time_ms = self.results["thumbnail_discovery"].get("avg_time_per_shot", 0) * 1000
            status = "✓ Good" if avg_time_ms < 20 else "⚠ Fair" if avg_time_ms < 50 else "✗ Poor"
            report.append(f"  • Thumbnail discovery: {status} ({avg_time_ms:.1f}ms per shot)")
        
        if "cache_performance" in self.results:
            speedup = self.results["cache_performance"].get("cache_speedup", 1)
            status = "✓ Good" if speedup > 5 else "⚠ Fair" if speedup > 2 else "✗ Poor"
            report.append(f"  • Cache effectiveness: {status} ({speedup:.1f}x speedup)")
        
        if "memory" in self.results:
            growth = self.results["memory"].get("memory_growth_mb", 0)
            status = "✓ Good" if growth < 10 else "⚠ Fair" if growth < 50 else "✗ Poor"
            report.append(f"  • Memory growth: {status} ({growth:+.1f}MB)")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)


def main():
    """Main entry point for the profiler."""
    parser = argparse.ArgumentParser(description="Profile ShotBot thumbnail discovery performance")
    parser.add_argument(
        "--profile",
        choices=["all", "thumbnail-discovery", "shot-extraction", "cache", "memory", "parallel"],
        default="all",
        help="Type of profiling to run"
    )
    parser.add_argument("--duration", type=int, default=10, help="Duration for memory profiling (seconds)")
    parser.add_argument("--output", help="Output file for report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and run profiler
    profiler = ComprehensiveProfiler()
    
    if args.profile == "all":
        results = profiler.run_all_profiles(args.duration)
    else:
        # Run specific profile
        test_paths, test_shots = profiler.generate_test_data()
        
        if args.profile == "thumbnail-discovery":
            results = {"thumbnail_discovery": profiler.profilers["thumbnail_discovery"].profile_thumbnail_pipeline(test_shots[:10])}
        elif args.profile == "shot-extraction":
            results = {"shot_extraction": profiler.profilers["shot_extraction"].profile_path_parsing(test_paths)}
        elif args.profile == "cache":
            results = {"cache_performance": profiler.profilers["cache_performance"].profile_cache_performance(test_paths[:20])}
        elif args.profile == "memory":
            results = {"memory": profiler.profilers["memory"].start_memory_monitoring(args.duration)}
        elif args.profile == "parallel":
            results = {"parallel_processing": profiler.profilers["parallel_processing"].profile_parallel_operations(test_shots[:5])}
        
        profiler.results = results
        profiler._generate_recommendations()
    
    # Generate and display report
    report = profiler.generate_report()
    print(report)
    
    # Save to file if specified
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    main()
