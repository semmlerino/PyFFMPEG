#!/usr/bin/env python3
"""
Comprehensive profiling script for ThreeDESceneFinder optimization.

This script identifies specific bottlenecks and tests optimization strategies.
"""

import concurrent.futures
import cProfile
import io
import os
import pstats
import subprocess

# Add current directory to path for imports
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, ".")

from threede_scene_finder import ThreeDESceneFinder


class SceneFinderProfiler:
    """Comprehensive profiler for ThreeDESceneFinder optimization."""

    def __init__(self):
        self.results = {}
        self.test_structure = None

    def create_realistic_test_structure(
        self, base_path: Path, scale: str = "medium"
    ) -> Dict[str, int]:
        """Create realistic VFX directory structure for testing.

        Args:
            base_path: Base directory for test structure
            scale: Size of test structure (small/medium/large)

        Returns:
            Dictionary with statistics about created structure
        """
        shows_root = base_path / "shows"

        if scale == "small":
            sequences = 2
            shots_per_seq = 3
            users_per_shot = 3
            files_per_user = 2
        elif scale == "medium":
            sequences = 4
            shots_per_seq = 5
            users_per_shot = 4
            files_per_user = 3
        else:  # large
            sequences = 8
            shots_per_seq = 10
            users_per_shot = 6
            files_per_user = 4

        stats = {"shots": 0, "users": 0, "files": 0, "directories": 0}

        for seq_num in range(1, sequences + 1):
            seq_name = f"seq{seq_num:02d}"

            for shot_num in range(10, 10 + (shots_per_seq * 10), 10):
                shot_dir = (
                    shows_root
                    / "test_show"
                    / "shots"
                    / seq_name
                    / f"{seq_name}_{shot_num:04d}"
                )
                stats["shots"] += 1

                # Create user directories
                user_dir = shot_dir / "user"

                for user_num in range(1, users_per_shot + 1):
                    user_name = f"artist{user_num}"
                    user_path = user_dir / user_name
                    user_path.mkdir(parents=True, exist_ok=True)
                    stats["users"] += 1
                    stats["directories"] += 1

                    # Create different directory patterns
                    patterns = [
                        ["mm", "3de", "mm-default", "scenes", "scene", "BG01"],
                        ["mm", "3de", "mm-default", "scenes", "scene", "FG01"],
                        ["3de", "scenes", "bg01"],
                        ["matchmove", "3de", "FG01"],
                    ]

                    for i, pattern in enumerate(patterns[:files_per_user]):
                        threede_dir = user_path
                        for segment in pattern:
                            threede_dir = threede_dir / segment
                        threede_dir.mkdir(parents=True, exist_ok=True)
                        stats["directories"] += len(pattern)

                        # Create .3de file
                        plate_name = pattern[-1].lower()
                        threede_file = threede_dir / f"scene_{plate_name}_v001.3de"
                        threede_file.write_text(
                            f"# 3DE Scene\nuser: {user_name}\nplate: {plate_name}"
                        )
                        stats["files"] += 1

                # Create published files occasionally
                if shot_num % 30 == 0:
                    pub_dir = shot_dir / "publish" / "mm" / "default"
                    pub_dir.mkdir(parents=True, exist_ok=True)
                    pub_file = pub_dir / "published_scene.3de"
                    pub_file.write_text("# Published 3DE Scene")
                    stats["files"] += 1
                    stats["directories"] += 3

        self.test_structure = shows_root
        return stats

    def profile_method(self, method_name: str, func, *args, **kwargs) -> Dict[str, Any]:
        """Profile a method and return comprehensive results."""

        # Memory tracking
        try:
            import psutil

            process = psutil.Process()
            memory_before = process.memory_info().rss / 1024 / 1024  # MB
        except ImportError:
            memory_before = 0

        # Profile execution
        profiler = cProfile.Profile()
        profiler.enable()
        start_time = time.perf_counter()

        try:
            result = func(*args, **kwargs)
            success = True
            error = None
        except Exception as e:
            result = []
            success = False
            error = str(e)
        finally:
            profiler.disable()

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Memory after
        try:
            memory_after = process.memory_info().rss / 1024 / 1024  # MB
            memory_used = memory_after - memory_before
        except Exception:
            memory_used = 0

        # Profile statistics
        stats_stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stats_stream)
        stats.sort_stats("cumulative")
        stats.print_stats(15)

        result_data = {
            "method_name": method_name,
            "execution_time": execution_time,
            "memory_used_mb": memory_used,
            "result_count": len(result) if isinstance(result, list) else 0,
            "success": success,
            "error": error,
            "profile_stats": stats_stream.getvalue(),
            "result": result,
        }

        self.results[method_name] = result_data
        return result_data

    def test_current_implementation(self, shot_path: str):
        """Test current ThreeDESceneFinder implementation."""

        def current_find_scenes():
            return ThreeDESceneFinder.find_scenes_for_shot(
                shot_workspace_path=shot_path,
                show="test_show",
                sequence="seq01",
                shot="seq01_0010",
                excluded_users={"excluded_user"},
            )

        return self.profile_method("current_implementation", current_find_scenes)

    def test_python_only_approach(self, shot_path: str):
        """Test pure Python approach without subprocess."""

        def python_only_find():
            """Alternative implementation using only Python pathlib."""
            scenes = []
            shot_path_obj = Path(shot_path)
            user_dir = shot_path_obj / "user"

            if not user_dir.exists():
                return scenes

            # Use os.scandir for better performance than iterdir
            try:
                with os.scandir(user_dir) as entries:
                    for entry in entries:
                        if entry.is_dir():
                            user_name = entry.name
                            if user_name == "excluded_user":
                                continue

                            user_path = Path(entry.path)

                            # Use rglob to find all .3de files
                            for threede_file in user_path.rglob("*.3de"):
                                if threede_file.is_file():
                                    # Quick plate extraction
                                    plate = threede_file.parent.name
                                    scenes.append(
                                        {
                                            "user": user_name,
                                            "plate": plate,
                                            "path": threede_file,
                                        }
                                    )
            except OSError:
                pass

            return scenes

        return self.profile_method("python_only_approach", python_only_find)

    def test_optimized_find_command(self, shot_path: str):
        """Test optimized find command approach."""

        def optimized_find():
            """Use single find command instead of multiple calls."""
            scenes = []
            shot_path_obj = Path(shot_path)
            user_dir = shot_path_obj / "user"

            if not user_dir.exists():
                return scenes

            try:
                # Single find command to get all .3de files
                result = subprocess.run(
                    [
                        "find",
                        str(user_dir),
                        "-name",
                        "*.3de",
                        "-type",
                        "f",
                        "-not",
                        "-path",
                        "*/excluded_user/*",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0 and result.stdout:
                    for file_path_str in result.stdout.strip().split("\n"):
                        if file_path_str:
                            file_path = Path(file_path_str)
                            # Extract user from path
                            parts = file_path.relative_to(user_dir).parts
                            if parts:
                                user_name = parts[0]
                                plate = file_path.parent.name
                                scenes.append(
                                    {
                                        "user": user_name,
                                        "plate": plate,
                                        "path": file_path,
                                    }
                                )
            except (
                subprocess.TimeoutExpired,
                subprocess.SubprocessError,
                FileNotFoundError,
            ):
                # Fallback to Python approach
                pass

            return scenes

        return self.profile_method("optimized_find_command", optimized_find)

    def test_concurrent_approach(self, shot_path: str):
        """Test concurrent directory processing."""

        def concurrent_find():
            """Process user directories concurrently."""
            scenes = []
            shot_path_obj = Path(shot_path)
            user_dir = shot_path_obj / "user"

            if not user_dir.exists():
                return scenes

            def process_user_dir(user_path: Path):
                """Process single user directory."""
                user_scenes = []
                user_name = user_path.name
                if user_name == "excluded_user":
                    return user_scenes

                try:
                    for threede_file in user_path.rglob("*.3de"):
                        if threede_file.is_file():
                            plate = threede_file.parent.name
                            user_scenes.append(
                                {
                                    "user": user_name,
                                    "plate": plate,
                                    "path": threede_file,
                                }
                            )
                except OSError:
                    pass

                return user_scenes

            # Get user directories
            user_dirs = [p for p in user_dir.iterdir() if p.is_dir()]

            # Process concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_user = {
                    executor.submit(process_user_dir, user_path): user_path
                    for user_path in user_dirs
                }

                for future in concurrent.futures.as_completed(future_to_user):
                    try:
                        user_scenes = future.result()
                        scenes.extend(user_scenes)
                    except Exception:
                        pass

            return scenes

        return self.profile_method("concurrent_approach", concurrent_find)

    def test_cached_approach(self, shot_path: str):
        """Test approach with directory listing caching."""

        def cached_find():
            """Use cached directory listings."""
            scenes = []
            shot_path_obj = Path(shot_path)
            user_dir = shot_path_obj / "user"

            if not user_dir.exists():
                return scenes

            # Cache for directory listings (in real implementation, this would be persistent)
            dir_cache = {}

            def get_cached_listing(path: Path):
                """Get cached directory listing."""
                path_str = str(path)
                if path_str not in dir_cache:
                    try:
                        # Use os.scandir for better performance
                        entries = []
                        with os.scandir(path) as dir_entries:
                            for entry in dir_entries:
                                entries.append(
                                    (entry.name, entry.is_dir(), entry.is_file())
                                )
                        dir_cache[path_str] = entries
                    except OSError:
                        dir_cache[path_str] = []

                return dir_cache[path_str]

            # Get user directories from cache
            user_entries = get_cached_listing(user_dir)

            for entry_name, is_dir, is_file in user_entries:
                if is_dir and entry_name != "excluded_user":
                    user_path = user_dir / entry_name

                    # Recursively find .3de files using cached listings
                    def find_3de_files_cached(search_path: Path):
                        found_files = []
                        entries = get_cached_listing(search_path)

                        for name, is_dir, is_file in entries:
                            full_path = search_path / name
                            if is_file and name.endswith(".3de"):
                                found_files.append(full_path)
                            elif is_dir:
                                found_files.extend(find_3de_files_cached(full_path))

                        return found_files

                    threede_files = find_3de_files_cached(user_path)

                    for threede_file in threede_files:
                        plate = threede_file.parent.name
                        scenes.append(
                            {"user": entry_name, "plate": plate, "path": threede_file}
                        )

            return scenes

        return self.profile_method("cached_approach", cached_find)

    def run_comprehensive_benchmark(self, scale: str = "medium"):
        """Run comprehensive benchmark comparing all approaches."""

        print(f"Creating {scale} test structure...")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            stats = self.create_realistic_test_structure(tmp_path, scale)

            print(f"Created structure with {stats}")

            # Get test shot path
            test_shot = str(
                tmp_path / "shows" / "test_show" / "shots" / "seq01" / "seq01_0010"
            )

            print("\nRunning benchmarks...")

            # Test all approaches
            approaches = [
                ("current_implementation", self.test_current_implementation),
                ("python_only_approach", self.test_python_only_approach),
                ("optimized_find_command", self.test_optimized_find_command),
                ("concurrent_approach", self.test_concurrent_approach),
                ("cached_approach", self.test_cached_approach),
            ]

            for name, test_func in approaches:
                print(f"  Testing {name}...")
                try:
                    test_func(test_shot)
                except Exception as e:
                    print(f"    ERROR: {e}")

            # Generate report
            self.print_comparison_report()

    def print_comparison_report(self):
        """Print comprehensive comparison report."""

        print("\n" + "=" * 80)
        print("THREEDE SCENE FINDER PERFORMANCE COMPARISON")
        print("=" * 80)

        if not self.results:
            print("No results to compare!")
            return

        # Summary table
        print("\nPERFORMANCE SUMMARY:")
        print("-" * 80)
        print(
            f"{'Method':<25} {'Time (s)':<10} {'Memory (MB)':<12} {'Results':<10} {'Status':<10}"
        )
        print("-" * 80)

        for method_name, data in self.results.items():
            status = "SUCCESS" if data["success"] else "ERROR"
            print(
                f"{method_name:<25} {data['execution_time']:<10.4f} {data['memory_used_mb']:<12.1f} {data['result_count']:<10} {status:<10}"
            )

        # Find best performer
        successful_results = {k: v for k, v in self.results.items() if v["success"]}
        if successful_results:
            fastest = min(
                successful_results.items(), key=lambda x: x[1]["execution_time"]
            )
            most_memory_efficient = min(
                successful_results.items(), key=lambda x: x[1]["memory_used_mb"]
            )

            print(
                f"\nFASTEST METHOD: {fastest[0]} ({fastest[1]['execution_time']:.4f}s)"
            )
            print(
                f"MOST MEMORY EFFICIENT: {most_memory_efficient[0]} ({most_memory_efficient[1]['memory_used_mb']:.1f}MB)"
            )

            # Compare against current implementation
            if "current_implementation" in successful_results:
                current_time = successful_results["current_implementation"][
                    "execution_time"
                ]
                print("\nSPEEDUP COMPARISON (vs current implementation):")
                for method_name, data in successful_results.items():
                    if method_name != "current_implementation":
                        speedup = current_time / data["execution_time"]
                        print(
                            f"  {method_name}: {speedup:.2f}x {'faster' if speedup > 1 else 'slower'}"
                        )

        # Detailed profiles for top methods
        print("\nDETAILED PROFILES:")
        print("-" * 50)

        for method_name, data in self.results.items():
            if data["success"]:
                print(f"\n{method_name.upper()}:")
                print(
                    f"Time: {data['execution_time']:.4f}s | Memory: {data['memory_used_mb']:.1f}MB | Results: {data['result_count']}"
                )

                # Show top function calls
                profile_lines = data["profile_stats"].split("\n")
                if len(profile_lines) > 10:
                    print("Top function calls:")
                    for line in profile_lines[6:12]:  # Skip header, show top 6
                        if line.strip():
                            print(f"  {line}")


if __name__ == "__main__":
    profiler = SceneFinderProfiler()

    # Run benchmark
    scale = "medium" if len(sys.argv) < 2 else sys.argv[1]
    profiler.run_comprehensive_benchmark(scale)
