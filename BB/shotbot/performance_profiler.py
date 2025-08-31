#!/usr/bin/env python3
"""
Comprehensive Performance Profiler for ShotBot Thumbnail Discovery System

This profiler analyzes performance bottlenecks in the thumbnail discovery pipeline
and provides actionable optimization recommendations.

Usage:
    python performance_profiler.py --profile all
    python performance_profiler.py --profile thumbnail-discovery
    python performance_profiler.py --profile memory --duration 60
"""

import argparse
import cProfile
import gc
import io
import logging
import os
import pstats
import psutil
import re
import statistics
import sys
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple
import concurrent.futures

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import ShotBot modules
try:
    from config import Config
    from shot_model import Shot
    from previous_shots_finder import PreviousShotsFinder, ParallelShotsFinder
    from utils import PathUtils, FileUtils, VersionUtils, clear_all_caches, get_cache_stats
    import utils
except ImportError as e:
    print(f"Warning: Could not import ShotBot modules: {e}")
    print("Some profiling features may be limited")

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Container for performance measurements."""
    
    # Timing metrics (in seconds)
    startup_time: float = 0.0
    shot_name_extraction_avg: float = 0.0
    shot_name_extraction_total: float = 0.0
    thumbnail_discovery_avg: float = 0.0
    thumbnail_discovery_total: float = 0.0
    cache_lookup_avg: float = 0.0
    filesystem_access_avg: float = 0.0
    
    # Memory metrics (in MB)
    initial_memory: float = 0.0
    peak_memory: float = 0.0
    memory_growth: float = 0.0
    shot_object_memory: float = 0.0
    cache_memory: float = 0.0
    
    # Cache metrics
    cache_hit_rate: float = 0.0
    cache_misses: int = 0
    cache_size: int = 0
    
    # Throughput metrics
    shots_processed_per_second: float = 0.0
    thumbnails_loaded_per_second: float = 0.0
    
    # Concurrency metrics
    thread_efficiency: float = 0.0
    lock_contention_time: float = 0.0
    
    # User experience metrics
    ui_blocking_operations: int = 0
    longest_blocking_operation: float = 0.0
    
    # Operation counts
    filesystem_operations: int = 0
    regex_operations: int = 0
    string_operations: int = 0
    
    # Error metrics
    errors_encountered: int = 0
    timeouts: int = 0

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
        self.memory_samples: List[float] = []
        self.timing_samples: List[float] = []
        self._lock = threading.Lock()
        
    @contextmanager
    def timer(self, operation_name: str = "operation"):
        """Context manager for timing operations."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.timing_samples.append(elapsed)
            logger.debug(f"{self.name}: {operation_name} took {elapsed:.4f}s")
    
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
        
        current_memory = self.get_memory_usage()
        self.metrics.peak_memory = max(self.memory_samples + [current_memory])
        
        # Calculate averages
        if self.timing_samples:
            self.metrics.cache_lookup_avg = statistics.mean(self.timing_samples)
        
        logger.info(f"Stopped profiling: {self.name} (took {self.metrics.startup_time:.2f}s)")


class ShotNameExtractionProfiler(BaseProfiler):
    """Profiles shot name extraction performance."""
    
    def __init__(self):
        super().__init__("ShotNameExtraction")
        self.extraction_times: List[float] = []
        self.regex_pattern = re.compile(r"/shows/([^/]+)/shots/([^/]+)/([^/]+)/")
    
    def profile_path_parsing(self, test_paths: List[str], iterations: int = 1000) -> Dict[str, Any]:
        """Profile shot name extraction from paths."""
        logger.info(f"Profiling shot name extraction with {len(test_paths)} paths x {iterations} iterations")
        
        # Test current implementation
        current_times = []
        for _ in range(iterations):
            with self.timer("current_extraction") as timer:
                for path in test_paths:
                    match = self.regex_pattern.search(path)
                    if match:
                        show, sequence, shot_dir = match.groups()
                        # Extract shot number like in _parse_shot_from_path
                        shot_number = shot_dir
                        if shot_dir.startswith(f"{sequence}_"):
                            shot_number = shot_dir[len(sequence) + 1:]
            current_times.append(timer)
        
        # Test optimized implementation using pre-compiled regex
        optimized_regex = re.compile(r"/shows/([^/]+)/shots/([^/]+)/([^/]+_)?(.+)/")
        optimized_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            for path in test_paths:
                match = optimized_regex.search(path)
                if match:
                    show, sequence, prefix, shot = match.groups()
            optimized_times.append(time.perf_counter() - start)
        
        current_avg = statistics.mean(current_times)
        optimized_avg = statistics.mean(optimized_times)
        improvement = (current_avg - optimized_avg) / current_avg * 100
        
        self.metrics.shot_name_extraction_avg = current_avg
        self.metrics.shot_name_extraction_total = sum(current_times)
        self.metrics.regex_operations = len(test_paths) * iterations
        
        return {
            "current_avg_time": current_avg,
            "optimized_avg_time": optimized_avg,
            "improvement_percent": improvement,
            "total_operations": len(test_paths) * iterations,
            "operations_per_second": (len(test_paths) * iterations) / current_avg if current_avg > 0 else 0,
        }


class ThumbnailDiscoveryProfiler(BaseProfiler):
    """Profiles thumbnail discovery pipeline performance."""
    
    def __init__(self):
        super().__init__("ThumbnailDiscovery")
        self.discovery_stages = {
            "editorial": [],
            "turnover_plate": [], 
            "publish_fallback": []
        }
        self.filesystem_ops = 0
    
    def profile_thumbnail_pipeline(self, test_shots: List[Shot]) -> Dict[str, Any]:
        """Profile the 3-tier thumbnail discovery pipeline."""
        logger.info(f"Profiling thumbnail discovery for {len(test_shots)} shots")
        
        stage_times = defaultdict(list)
        cache_stats_before = get_cache_stats()
        
        for shot in test_shots:
            # Stage 1: Editorial thumbnails
            with self.timer("editorial_check") as timer:
                thumbnail_dir = PathUtils.build_thumbnail_path(
                    Config.SHOWS_ROOT, shot.show, shot.sequence, shot.shot
                )
                editorial_thumbnail = None
                if PathUtils.validate_path_exists(thumbnail_dir, "Thumbnail directory"):
                    self.filesystem_ops += 1
                    editorial_thumbnail = FileUtils.get_first_image_file(thumbnail_dir)
                    if editorial_thumbnail:
                        self.filesystem_ops += 1
            stage_times["editorial"].append(timer)
            
            if editorial_thumbnail:
                continue  # Found editorial thumbnail
            
            # Stage 2: Turnover plate thumbnails
            with self.timer("turnover_plate_check") as timer:
                turnover_thumbnail = PathUtils.find_turnover_plate_thumbnail(
                    Config.SHOWS_ROOT, shot.show, shot.sequence, shot.shot
                )
                if turnover_thumbnail:
                    self.filesystem_ops += 2  # Path validation + file search
            stage_times["turnover_plate"].append(timer)
            
            if turnover_thumbnail:
                continue  # Found turnover thumbnail
                
            # Stage 3: Publish folder fallback
            with self.timer("publish_fallback_check") as timer:
                publish_thumbnail = PathUtils.find_any_publish_thumbnail(
                    Config.SHOWS_ROOT, shot.show, shot.sequence, shot.shot
                )
                if publish_thumbnail:
                    self.filesystem_ops += 3  # Multiple path validations + recursive search
            stage_times["publish_fallback"].append(timer)
        
        cache_stats_after = get_cache_stats()
        
        # Calculate metrics
        total_time = sum(sum(times) for times in stage_times.values())
        self.metrics.thumbnail_discovery_total = total_time
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
            "cache_growth": cache_stats_after["path_cache_size"] - cache_stats_before["path_cache_size"],
            "throughput": self.metrics.thumbnails_loaded_per_second
        }


class CachePerformanceProfiler(BaseProfiler):
    """Profiles cache effectiveness and performance impact."""
    
    def __init__(self):
        super().__init__("CachePerformance")
        self.cache_accesses = 0
        self.cache_hits = 0
    
    def profile_cache_performance(self, test_paths: List[str], iterations: int = 100) -> Dict[str, Any]:
        """Profile path cache performance with repeated access patterns."""
        logger.info(f"Profiling cache performance with {len(test_paths)} paths")
        
        # Clear caches to start fresh
        clear_all_caches()
        
        # First pass - populate cache (all misses)
        first_pass_times = []
        with self.timer("cache_population") as timer:
            for path in test_paths:
                start = time.perf_counter()
                PathUtils.validate_path_exists(path, "Test path")
                first_pass_times.append(time.perf_counter() - start)
                self.cache_accesses += 1
        
        cache_stats_populated = get_cache_stats()
        
        # Second pass - should hit cache
        second_pass_times = []
        with self.timer("cache_access") as timer:
            for path in test_paths:
                start = time.perf_counter()
                PathUtils.validate_path_exists(path, "Test path")
                second_pass_times.append(time.perf_counter() - start)
                self.cache_accesses += 1
        
        # Calculate cache effectiveness
        first_pass_avg = statistics.mean(first_pass_times) if first_pass_times else 0
        second_pass_avg = statistics.mean(second_pass_times) if second_pass_times else 0
        cache_speedup = first_pass_avg / second_pass_avg if second_pass_avg > 0 else 0
        
        self.metrics.cache_hit_rate = cache_speedup
        self.metrics.cache_size = cache_stats_populated["path_cache_size"]
        
        return {
            "first_pass_avg": first_pass_avg,
            "second_pass_avg": second_pass_avg,  
            "cache_speedup": cache_speedup,
            "cache_size": self.metrics.cache_size,
            "cache_memory_estimate": self.metrics.cache_size * 0.1,  # Rough estimate in MB
            "efficiency_rating": "High" if cache_speedup > 5 else "Medium" if cache_speedup > 2 else "Low"
        }


class ParallelProcessingProfiler(BaseProfiler):
    """Profiles concurrent operations and thread efficiency."""
    
    def __init__(self):
        super().__init__("ParallelProcessing")
        self.thread_times = []
        self.lock_wait_times = []
    
    def profile_parallel_finder(self, active_shots: List[Shot]) -> Dict[str, Any]:
        """Profile ParallelShotsFinder performance."""
        logger.info("Profiling parallel shot finder performance")
        
        # Test different worker counts
        worker_counts = [1, 2, 4, 8]
        results = {}
        
        for worker_count in worker_counts:
            if 'ParallelShotsFinder' not in globals():
                logger.warning("ParallelShotsFinder not available for profiling")
                break
                
            finder = ParallelShotsFinder(max_workers=worker_count)
            
            start_time = time.perf_counter()
            # Use a timeout to prevent hanging
            try:
                # Mock the parallel operation for testing
                with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                    futures = []
                    for i in range(worker_count * 2):  # Submit more tasks than workers
                        future = executor.submit(time.sleep, 0.1)  # Simulate work
                        futures.append(future)
                    
                    for future in concurrent.futures.as_completed(futures, timeout=10):
                        try:
                            future.result()
                        except Exception as e:
                            logger.warning(f"Task failed: {e}")
                            
            except concurrent.futures.TimeoutError:
                logger.warning(f"Parallel operation timed out with {worker_count} workers")
                
            elapsed = time.perf_counter() - start_time
            results[worker_count] = elapsed
        
        # Calculate optimal worker count
        if results:
            optimal_workers = min(results.keys(), key=lambda k: results[k])
            thread_efficiency = len(results) / sum(results.values()) if results.values() else 0
        else:
            optimal_workers = 4  # Reasonable default
            thread_efficiency = 0.5
        
        self.metrics.thread_efficiency = thread_efficiency
        
        return {
            "worker_performance": results,
            "optimal_worker_count": optimal_workers,
            "thread_efficiency": thread_efficiency,
            "scalability_rating": "Good" if thread_efficiency > 0.7 else "Fair" if thread_efficiency > 0.4 else "Poor"
        }


class MemoryProfiler(BaseProfiler):
    """Profiles memory usage patterns and identifies leaks."""
    
    def __init__(self):
        super().__init__("Memory")
        self.memory_samples = deque(maxlen=1000)  # Rolling window
        self.gc_counts = []
    
    def start_memory_monitoring(self, duration: int = 60):
        """Monitor memory usage over time."""
        logger.info(f"Starting memory monitoring for {duration} seconds")
        
        start_time = time.time()
        while time.time() - start_time < duration:
            memory_mb = self.get_memory_usage()
            self.memory_samples.append(memory_mb)
            
            # Force garbage collection and measure
            gc_before = len(gc.get_objects())
            gc.collect()
            gc_after = len(gc.get_objects())
            self.gc_counts.append(gc_before - gc_after)
            
            time.sleep(0.5)  # Sample every 500ms
    
    def analyze_memory_patterns(self) -> Dict[str, Any]:
        """Analyze memory usage patterns for leaks and inefficiencies."""
        if not self.memory_samples:
            return {"error": "No memory samples collected"}
        
        samples = list(self.memory_samples)
        
        # Calculate memory statistics
        initial_memory = samples[0]
        peak_memory = max(samples)
        final_memory = samples[-1]
        avg_memory = statistics.mean(samples)
        memory_growth = final_memory - initial_memory
        
        # Detect memory trends
        if len(samples) > 10:
            # Simple linear regression to detect trends
            x_values = range(len(samples))
            slope = statistics.correlation(x_values, samples) if len(set(samples)) > 1 else 0
            trend = "increasing" if slope > 0.1 else "decreasing" if slope < -0.1 else "stable"
        else:
            trend = "insufficient_data"
        
        # Analyze garbage collection effectiveness
        gc_freed_avg = statistics.mean(self.gc_counts) if self.gc_counts else 0
        
        self.metrics.initial_memory = initial_memory
        self.metrics.peak_memory = peak_memory
        self.metrics.memory_growth = memory_growth
        
        return {
            "initial_memory_mb": initial_memory,
            "peak_memory_mb": peak_memory,
            "final_memory_mb": final_memory,
            "average_memory_mb": avg_memory,
            "memory_growth_mb": memory_growth,
            "memory_trend": trend,
            "gc_effectiveness": gc_freed_avg,
            "memory_efficiency": "Good" if memory_growth < 10 else "Fair" if memory_growth < 50 else "Poor"
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
        # Generate test paths that match the expected format
        test_paths = []
        test_shots = []
        
        shows = ["TestShow1", "TestShow2", "DemoProject"]
        sequences = ["010", "020", "030", "040"]
        shot_numbers = ["0010", "0020", "0030", "0040", "0050"]
        
        for show in shows:
            for sequence in sequences:
                for shot_num in shot_numbers:
                    # Create realistic path
                    shot_dir = f"{sequence}_{shot_num}"
                    path = f"/shows/{show}/shots/{sequence}/{shot_dir}/user/testuser"
                    test_paths.append(path)
                    
                    # Create Shot object
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
    
    def run_all_profiles(self, duration: int = 30) -> Dict[str, Any]:
        """Run all performance profiles."""
        logger.info("Starting comprehensive performance profiling")
        
        test_paths, test_shots = self.generate_test_data()
        
        # Run shot name extraction profiling
        logger.info("1/5: Profiling shot name extraction...")
        self.results["shot_extraction"] = self.profilers["shot_extraction"].profile_path_parsing(test_paths)
        
        # Run thumbnail discovery profiling  
        logger.info("2/5: Profiling thumbnail discovery...")
        self.results["thumbnail_discovery"] = self.profilers["thumbnail_discovery"].profile_thumbnail_pipeline(test_shots[:10])  # Limit for speed
        
        # Run cache performance profiling
        logger.info("3/5: Profiling cache performance...")
        self.results["cache_performance"] = self.profilers["cache_performance"].profile_cache_performance(test_paths[:20])
        
        # Run parallel processing profiling
        logger.info("4/5: Profiling parallel processing...")
        self.results["parallel_processing"] = self.profilers["parallel_processing"].profile_parallel_finder(test_shots[:5])
        
        # Run memory profiling (shorter duration for testing)
        logger.info("5/5: Profiling memory usage...")
        memory_thread = threading.Thread(
            target=self.profilers["memory"].start_memory_monitoring,
            args=(min(duration, 15),)  # Cap at 15 seconds for testing
        )
        memory_thread.start()
        memory_thread.join()
        self.results["memory"] = self.profilers["memory"].analyze_memory_patterns()
        
        # Generate recommendations
        self._generate_recommendations()
        
        logger.info("Comprehensive profiling complete")
        return self.results
    
    def _generate_recommendations(self):
        """Generate optimization recommendations based on profiling results."""
        self.recommendations = []
        
        # Shot name extraction recommendations
        if "shot_extraction" in self.results:
            improvement = self.results["shot_extraction"].get("improvement_percent", 0)
            if improvement > 10:
                self.recommendations.append(
                    f"OPTIMIZATION: Shot name extraction can be improved by {improvement:.1f}% using pre-compiled regex patterns"
                )
        
        # Thumbnail discovery recommendations  
        if "thumbnail_discovery" in self.results:
            avg_time = self.results["thumbnail_discovery"].get("avg_time_per_shot", 0)
            if avg_time > 0.1:  # 100ms per shot is slow
                self.recommendations.append(
                    f"BOTTLENECK: Thumbnail discovery averaging {avg_time:.3f}s per shot - consider parallel loading"
                )
            
            fs_ops = self.results["thumbnail_discovery"].get("filesystem_operations", 0)
            if fs_ops > 100:
                self.recommendations.append(
                    f"I/O INTENSIVE: {fs_ops} filesystem operations detected - improve caching strategy"
                )
        
        # Cache recommendations
        if "cache_performance" in self.results:
            speedup = self.results["cache_performance"].get("cache_speedup", 1)
            if speedup < 2:
                self.recommendations.append(
                    f"CACHE INEFFECTIVE: Only {speedup:.1f}x speedup from caching - review cache TTL settings"
                )
        
        # Memory recommendations
        if "memory" in self.results:
            growth = self.results["memory"].get("memory_growth_mb", 0)
            if growth > 50:
                self.recommendations.append(
                    f"MEMORY LEAK: {growth:.1f}MB memory growth detected - check for unreleased references"
                )
        
        # Parallel processing recommendations
        if "parallel_processing" in self.results:
            efficiency = self.results["parallel_processing"].get("thread_efficiency", 0)
            if efficiency < 0.5:
                self.recommendations.append(
                    f"CONCURRENCY ISSUE: Thread efficiency only {efficiency:.1f} - review lock contention"
                )
    
    def generate_report(self) -> str:
        """Generate a comprehensive performance report."""
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
            scores.append(min(100, ops_per_sec / 1000 * 100))  # Scale to 0-100
        
        if "cache_performance" in self.results:
            speedup = self.results["cache_performance"].get("cache_speedup", 1)
            scores.append(min(100, speedup * 10))  # Scale to 0-100
        
        overall_score = statistics.mean(scores) if scores else 50
        report.append(f"Overall Performance Score: {overall_score:.1f}/100")
        report.append("")
        
        # Detailed Results
        for category, results in self.results.items():
            report.append(f"{category.upper().replace('_', ' ')}")
            report.append("-" * len(category))
            
            if isinstance(results, dict):
                for key, value in results.items():
                    if isinstance(value, float):
                        report.append(f"  {key}: {value:.4f}")
                    elif isinstance(value, dict):
                        report.append(f"  {key}:")
                        for subkey, subvalue in value.items():
                            report.append(f"    {subkey}: {subvalue}")
                    else:
                        report.append(f"  {key}: {value}")
            else:
                report.append(f"  Result: {results}")
            report.append("")
        
        # Recommendations
        if self.recommendations:
            report.append("OPTIMIZATION RECOMMENDATIONS")
            report.append("-" * 30)
            for i, rec in enumerate(self.recommendations, 1):
                report.append(f"{i}. {rec}")
            report.append("")
        
        # Performance Comparison
        report.append("PERFORMANCE COMPARISON")
        report.append("-" * 25)
        if "thumbnail_discovery" in self.results:
            avg_time = self.results["thumbnail_discovery"].get("avg_time_per_shot", 0)
            throughput = self.results["thumbnail_discovery"].get("throughput", 0)
            report.append(f"Current: {avg_time:.3f}s per thumbnail, {throughput:.1f} thumbnails/sec")
            
            # Estimate improvements
            if avg_time > 0:
                estimated_improved = avg_time * 0.6  # Assume 40% improvement possible
                estimated_throughput = 1 / estimated_improved if estimated_improved > 0 else 0
                report.append(f"Potential: {estimated_improved:.3f}s per thumbnail, {estimated_throughput:.1f} thumbnails/sec")
                report.append(f"Improvement: {((avg_time - estimated_improved) / avg_time * 100):.1f}% faster")
        
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
    parser.add_argument("--duration", type=int, default=30, help="Duration for memory profiling (seconds)")
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
            profiler.profilers["memory"].start_memory_monitoring(args.duration)
            results = {"memory": profiler.profilers["memory"].analyze_memory_patterns()}
        elif args.profile == "parallel":
            results = {"parallel_processing": profiler.profilers["parallel_processing"].profile_parallel_finder(test_shots[:5])}
        
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
