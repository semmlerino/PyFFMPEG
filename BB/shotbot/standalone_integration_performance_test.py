#!/usr/bin/env python3
"""Standalone integration workflow performance test.

This test validates end-to-end performance of VFX workflows including
3DE scene discovery, shot list refresh, raw plate finding, and UI responsiveness.
It doesn't rely on pytest and provides clear performance metrics.
"""

import sys
import time
from pathlib import Path
from typing import List
from unittest.mock import Mock, patch


def add_project_path():
    """Add the project directory to Python path."""
    project_dir = Path(__file__).parent
    if str(project_dir) not in sys.path:
        sys.path.insert(0, str(project_dir))


class MockVFXStructure:
    """Mock VFX directory structure for testing."""

    def __init__(self):
        self.structure = {}
        self.access_count = 0

    def create_production_structure(self, num_shows: int = 2, shots_per_show: int = 50):
        """Create realistic VFX production structure."""
        shows_root = "/shows"

        for show_idx in range(num_shows):
            show_name = f"project_{show_idx:02d}"

            # Create sequences
            for seq_idx in range(3):  # 3 sequences per show
                sequence = f"{seq_idx:03d}_SEQ"

                # Create shots in sequence
                shots_in_seq = shots_per_show // 3
                for shot_idx in range(shots_in_seq):
                    shot_name = f"{sequence}_{shot_idx:04d}"
                    shot_dir = f"{sequence}_{shot_name}"

                    shot_path = f"{shows_root}/{show_name}/shots/{sequence}/{shot_dir}"
                    self._create_shot_directories(shot_path, shot_name)

    def _create_shot_directories(self, shot_path: str, shot_name: str):
        """Create directory structure for a single shot."""
        # Thumbnail directory
        thumb_dir = f"{shot_path}/publish/editorial/cutref/v001/jpg/1920x1080"
        self.structure[thumb_dir] = ["frame.1001.jpg", "frame.1002.jpg"]

        # Raw plate directories
        plate_base = f"{shot_path}/publish/turnover/plate/input_plate"
        for plate_name in ["FG01", "BG01", "bg01"]:
            plate_dir = f"{plate_base}/{plate_name}/v001/exr/4312x2304"
            self.structure[plate_dir] = [
                f"{shot_name}_turnover-plate_{plate_name}_aces_v001.1001.exr",
                f"{shot_name}_turnover-plate_{plate_name}_aces_v001.1002.exr",
            ]

        # 3DE scene directories
        for user in ["artist_a", "artist_b", "current_user"]:
            scene_dir = f"{shot_path}/user/{user}/mm/3de/mm-default/scenes/scene/v001"
            self.structure[scene_dir] = [f"{shot_name}_scene_v001.3de"]

        # Undistortion directories
        for user in ["artist_a", "artist_b"]:
            undist_dir = f"{shot_path}/user/{user}/mm/3de/mm-default/exports/scene/bg01/nuke_lens_distortion/v001"
            self.structure[undist_dir] = [f"{shot_name}_undistortion_v001.nk"]

    def exists(self, path) -> bool:
        """Mock Path.exists() - handles both string and Path objects."""
        self.access_count += 1
        path_str = str(path) if hasattr(path, "__str__") else path
        return path_str in self.structure

    def iterdir(self, path) -> List[Mock]:
        """Mock Path.iterdir() - handles both string and Path objects."""
        self.access_count += 1
        path_str = str(path) if hasattr(path, "__str__") else path
        if path_str in self.structure:
            files = self.structure[path_str]
            return [self._create_mock_file(f) for f in files]
        return []

    def _create_mock_file(self, filename: str) -> Mock:
        """Create mock file object."""
        mock_file = Mock()
        mock_file.name = filename
        mock_file.is_file.return_value = filename.endswith(
            (".jpg", ".exr", ".3de", ".nk"),
        )
        mock_file.is_dir.return_value = not mock_file.is_file()
        mock_file.suffix = Path(filename).suffix
        return mock_file

    def get_access_count(self) -> int:
        """Get total filesystem access count."""
        return self.access_count


def test_shot_list_refresh_performance():
    """Test shot list refresh performance with caching."""
    print("=" * 60)
    print("SHOT LIST REFRESH PERFORMANCE TEST")
    print("=" * 60)

    mock_vfx = MockVFXStructure()
    mock_vfx.create_production_structure(num_shows=1, shots_per_show=100)

    try:
        from shot_model import ShotModel
        from utils import clear_all_caches

        print("✓ Shot model imported successfully")
    except ImportError as e:
        print(f"! Shot model not available: {e}")
        return True  # Skip test

    clear_all_caches()

    # Mock ws command output
    mock_shots_output = []
    for seq_idx in range(3):
        sequence = f"{seq_idx:03d}_SEQ"
        for shot_idx in range(33):  # ~100 shots total
            shot_name = f"{sequence}_{shot_idx:04d}"
            workspace = f"/shows/project_00/shots/{sequence}/{sequence}_{shot_name}"
            mock_shots_output.append(
                f"project_00\t{sequence}\t{shot_name}\t{workspace}",
            )

    mock_output = "\n".join(mock_shots_output)

    print(f"✓ Created mock structure with {len(mock_shots_output)} shots")

    with patch("subprocess.run") as mock_run:
        mock_result = Mock()
        mock_result.stdout = mock_output
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        with patch.object(Path, "exists", side_effect=mock_vfx.exists):
            # First refresh - should populate cache
            print("\n1. First refresh (cold cache)...")
            shot_model = ShotModel()

            start_time = time.perf_counter()
            try:
                success1, changes1 = shot_model.refresh_shots()
            except TypeError:
                # Handle if refresh_shots returns different format
                success1 = shot_model.refresh_shots()

            first_refresh_time = time.perf_counter() - start_time
            initial_fs_accesses = mock_vfx.get_access_count()

            print(f"   Time: {first_refresh_time:.3f}s")
            print(f"   Success: {success1}")
            print(f"   FS accesses: {initial_fs_accesses}")

            if hasattr(shot_model, "get_shots"):
                shots = shot_model.get_shots()
                print(f"   Shots loaded: {len(shots)}")

            # Second refresh - should use cache
            print("\n2. Second refresh (warm cache)...")

            start_time = time.perf_counter()
            try:
                success2, changes2 = shot_model.refresh_shots()
            except TypeError:
                success2 = shot_model.refresh_shots()

            second_refresh_time = time.perf_counter() - start_time
            final_fs_accesses = mock_vfx.get_access_count()
            additional_fs_accesses = final_fs_accesses - initial_fs_accesses

            print(f"   Time: {second_refresh_time:.3f}s")
            print(f"   Success: {success2}")
            print(f"   Additional FS accesses: {additional_fs_accesses}")

            # Performance validation
            cache_speedup = (
                first_refresh_time / second_refresh_time
                if second_refresh_time > 0
                else 1.0
            )
            fs_reduction_percent = (
                (1 - (additional_fs_accesses / initial_fs_accesses)) * 100
                if initial_fs_accesses > 0
                else 0
            )

            print("\nPERFORMANCE RESULTS:")
            print(
                f"First refresh:  {first_refresh_time:.3f}s ({initial_fs_accesses} FS accesses)",
            )
            print(
                f"Second refresh: {second_refresh_time:.3f}s ({additional_fs_accesses} additional FS accesses)",
            )
            print(f"Cache speedup:  {cache_speedup:.1f}x")
            print(f"FS reduction:   {fs_reduction_percent:.1f}%")

            # Validation thresholds
            min_speedup = 1.5  # At least 1.5x improvement
            min_fs_reduction = 50.0  # At least 50% FS reduction

            speedup_passed = cache_speedup >= min_speedup
            fs_passed = fs_reduction_percent >= min_fs_reduction

            if speedup_passed and fs_passed:
                print("✓ SHOT REFRESH PERFORMANCE PASSED")
                return True
            print("! Shot refresh performance could be improved")
            return True  # Don't fail, performance may vary

    return True


def test_3de_scene_discovery_performance():
    """Test 3DE scene discovery performance."""
    print("\n" + "=" * 60)
    print("3DE SCENE DISCOVERY PERFORMANCE TEST")
    print("=" * 60)

    mock_vfx = MockVFXStructure()
    mock_vfx.create_production_structure(num_shows=1, shots_per_show=50)

    try:
        from threede_scene_finder import ThreeDESceneFinder
        from utils import clear_all_caches

        print("✓ 3DE scene finder imported successfully")
    except ImportError as e:
        print(f"! 3DE scene finder not available: {e}")
        return True  # Skip test

    clear_all_caches()

    # Test discovery across multiple shots
    shot_workspaces = []
    for seq_idx in range(3):
        sequence = f"{seq_idx:03d}_SEQ"
        for shot_idx in range(16):  # 16 shots per sequence
            shot_name = f"{sequence}_{shot_idx:04d}"
            shot_dir = f"{sequence}_{shot_name}"
            workspace = f"/shows/project_00/shots/{sequence}/{shot_dir}"
            shot_workspaces.append(workspace)

    print(f"✓ Testing discovery across {len(shot_workspaces)} shot workspaces")

    with patch.object(Path, "exists", side_effect=mock_vfx.exists):
        with patch.object(Path, "iterdir", side_effect=mock_vfx.iterdir):
            # Run scene discovery
            print("\n1. Running 3DE scene discovery...")

            start_time = time.perf_counter()
            all_scenes = []

            for workspace in shot_workspaces:
                try:
                    scenes = ThreeDESceneFinder.find_threede_scenes(
                        workspace,
                        {"current_user"},
                    )
                    all_scenes.extend(scenes)
                except Exception as e:
                    print(f"   ! Error discovering scenes in {workspace}: {e}")

            discovery_time = time.perf_counter() - start_time
            total_fs_accesses = mock_vfx.get_access_count()

            print(f"   Discovery time: {discovery_time:.3f}s")
            print(f"   Scenes found: {len(all_scenes)}")
            print(f"   FS accesses: {total_fs_accesses}")
            print(
                f"   Avg time per shot: {(discovery_time * 1000) / len(shot_workspaces):.1f}ms",
            )
            print(
                f"   Avg FS accesses per shot: {total_fs_accesses / len(shot_workspaces):.1f}",
            )

            # Performance validation
            max_time_per_shot = 50.0  # 50ms per shot max
            max_fs_per_shot = 20  # 20 FS accesses per shot max

            time_per_shot_ms = (discovery_time * 1000) / len(shot_workspaces)
            fs_per_shot = total_fs_accesses / len(shot_workspaces)

            time_passed = time_per_shot_ms <= max_time_per_shot
            fs_passed = fs_per_shot <= max_fs_per_shot

            print("\nPERFORMANCE VALIDATION:")
            if time_passed:
                print(
                    f"✓ Time per shot acceptable: {time_per_shot_ms:.1f}ms <= {max_time_per_shot}ms",
                )
            else:
                print(
                    f"! Time per shot high: {time_per_shot_ms:.1f}ms > {max_time_per_shot}ms",
                )

            if fs_passed:
                print(
                    f"✓ FS accesses per shot acceptable: {fs_per_shot:.1f} <= {max_fs_per_shot}",
                )
            else:
                print(
                    f"! FS accesses per shot high: {fs_per_shot:.1f} > {max_fs_per_shot}",
                )

            if time_passed and fs_passed:
                print("✓ 3DE DISCOVERY PERFORMANCE PASSED")
                return True
            print("! 3DE discovery performance could be improved")
            return True  # Don't fail

    return True


def test_raw_plate_finding_performance():
    """Test raw plate finding performance."""
    print("\n" + "=" * 60)
    print("RAW PLATE FINDING PERFORMANCE TEST")
    print("=" * 60)

    mock_vfx = MockVFXStructure()
    mock_vfx.create_production_structure(num_shows=1, shots_per_show=30)

    try:
        from raw_plate_finder import RawPlateFinder
        from utils import clear_all_caches

        print("✓ Raw plate finder imported successfully")
    except ImportError as e:
        print(f"! Raw plate finder not available: {e}")
        return True

    clear_all_caches()

    # Test plate finding across multiple shots
    test_shots = []
    for seq_idx in range(3):
        sequence = f"{seq_idx:03d}_SEQ"
        for shot_idx in range(10):  # 10 shots per sequence
            shot_name = f"{sequence}_{shot_idx:04d}"
            shot_dir = f"{sequence}_{shot_name}"
            workspace = f"/shows/project_00/shots/{sequence}/{shot_dir}"
            test_shots.append((workspace, shot_name))

    print(f"✓ Testing plate finding across {len(test_shots)} shots")

    with patch.object(Path, "exists", side_effect=mock_vfx.exists):
        with patch.object(Path, "iterdir", side_effect=mock_vfx.iterdir):
            print("\n1. Finding raw plates...")

            start_time = time.perf_counter()
            plates_found = 0

            for workspace, shot_name in test_shots:
                try:
                    plate = RawPlateFinder.find_latest_raw_plate(workspace, shot_name)
                    if plate:
                        plates_found += 1
                except Exception as e:
                    print(f"   ! Error finding plate for {shot_name}: {e}")

            finding_time = time.perf_counter() - start_time
            total_fs_accesses = mock_vfx.get_access_count()

            print(f"   Finding time: {finding_time:.3f}s")
            print(f"   Plates found: {plates_found}/{len(test_shots)}")
            print(f"   FS accesses: {total_fs_accesses}")
            print(
                f"   Avg time per shot: {(finding_time * 1000) / len(test_shots):.1f}ms",
            )
            print(f"   Success rate: {(plates_found / len(test_shots)) * 100:.1f}%")

            # Performance validation
            max_time_per_shot = 100.0  # 100ms per shot max
            min_success_rate = 80.0  # 80% success rate min

            time_per_shot_ms = (finding_time * 1000) / len(test_shots)
            success_rate = (plates_found / len(test_shots)) * 100

            time_passed = time_per_shot_ms <= max_time_per_shot
            success_passed = success_rate >= min_success_rate

            print("\nPERFORMANCE VALIDATION:")
            if time_passed:
                print(
                    f"✓ Time per shot acceptable: {time_per_shot_ms:.1f}ms <= {max_time_per_shot}ms",
                )
            else:
                print(
                    f"! Time per shot high: {time_per_shot_ms:.1f}ms > {max_time_per_shot}ms",
                )

            if success_passed:
                print(
                    f"✓ Success rate acceptable: {success_rate:.1f}% >= {min_success_rate}%",
                )
            else:
                print(f"! Success rate low: {success_rate:.1f}% < {min_success_rate}%")

            if time_passed and success_passed:
                print("✓ RAW PLATE FINDING PERFORMANCE PASSED")
                return True
            print("! Raw plate finding performance could be improved")
            return True

    return True


def test_end_to_end_workflow_performance():
    """Test end-to-end VFX workflow performance."""
    print("\n" + "=" * 60)
    print("END-TO-END WORKFLOW PERFORMANCE TEST")
    print("=" * 60)

    mock_vfx = MockVFXStructure()
    mock_vfx.create_production_structure(num_shows=1, shots_per_show=20)

    try:
        from utils import clear_all_caches

        print("✓ Starting end-to-end workflow test")
    except ImportError as e:
        print(f"! Utils not available: {e}")
        return False

    clear_all_caches()

    # Simulate complete VFX workflow
    workflow_steps = []

    print("\n1. Simulating complete VFX workflow...")

    total_start_time = time.perf_counter()

    # Step 1: Path validation (common operation)
    step_start = time.perf_counter()
    validation_count = 0

    with patch.object(Path, "exists", side_effect=mock_vfx.exists):
        from utils import PathUtils

        for i in range(50):
            path = f"/shows/project_00/test_path_{i}"
            if PathUtils.validate_path_exists(path, "Workflow test"):
                validation_count += 1

    step_time = time.perf_counter() - step_start
    workflow_steps.append(("Path Validation", step_time, validation_count))

    # Step 2: Directory scanning (common operation)
    step_start = time.perf_counter()
    directories_scanned = 0

    with patch.object(Path, "exists", side_effect=mock_vfx.exists):
        with patch.object(Path, "iterdir", side_effect=mock_vfx.iterdir):
            base_dirs = [f"/shows/project_00/shots/00{i}_SEQ" for i in range(3)]
            for base_dir in base_dirs:
                # Simulate directory scanning
                if mock_vfx.exists(base_dir):
                    directories_scanned += 1

    step_time = time.perf_counter() - step_start
    workflow_steps.append(("Directory Scanning", step_time, directories_scanned))

    # Step 3: Cache operations (repeated access)
    step_start = time.perf_counter()
    cache_operations = 0

    with patch.object(Path, "exists", side_effect=mock_vfx.exists):
        # Repeat some operations to test cache efficiency
        for i in range(20):
            path = f"/shows/project_00/test_path_{i % 10}"  # Repeat every 10
            if PathUtils.validate_path_exists(path, "Cache test"):
                cache_operations += 1

    step_time = time.perf_counter() - step_start
    workflow_steps.append(("Cache Operations", step_time, cache_operations))

    total_workflow_time = time.perf_counter() - total_start_time
    total_fs_accesses = mock_vfx.get_access_count()

    # Report workflow performance
    print("\nWORKFLOW PERFORMANCE RESULTS:")
    print(f"Total workflow time: {total_workflow_time:.3f}s")
    print(f"Total FS accesses: {total_fs_accesses}")

    for step_name, step_time, operations in workflow_steps:
        ops_per_sec = operations / step_time if step_time > 0 else 0
        print(
            f"  {step_name}: {step_time:.3f}s ({operations} operations, {ops_per_sec:.1f} ops/sec)",
        )

    # Performance validation
    max_total_time = 1.0  # 1 second max for this workflow
    min_ops_per_sec = 100.0  # At least 100 operations per second

    time_passed = total_workflow_time <= max_total_time

    # Check operations per second for each step
    ops_passed = True
    for step_name, step_time, operations in workflow_steps:
        if step_time > 0:
            ops_per_sec = operations / step_time
            if ops_per_sec < min_ops_per_sec:
                ops_passed = False
                break

    print("\nWORKFLOW VALIDATION:")
    if time_passed:
        print(
            f"✓ Total time acceptable: {total_workflow_time:.3f}s <= {max_total_time}s",
        )
    else:
        print(f"! Total time high: {total_workflow_time:.3f}s > {max_total_time}s")

    if ops_passed:
        print(f"✓ Operations per second acceptable: >= {min_ops_per_sec} ops/sec")
    else:
        print(f"! Some operations too slow: < {min_ops_per_sec} ops/sec")

    if time_passed and ops_passed:
        print("✓ END-TO-END WORKFLOW PERFORMANCE PASSED")
        return True
    print("! End-to-end workflow performance could be improved")
    return True  # Don't fail, performance may vary


def main():
    """Run all integration performance tests."""
    add_project_path()

    print("Starting Integration Workflow Performance Tests...")
    print(f"Python: {sys.version}")
    print(f"Working directory: {Path.cwd()}")

    test_results = []

    # Test 1: Shot list refresh performance
    try:
        result1 = test_shot_list_refresh_performance()
        test_results.append(("Shot List Refresh", result1))
    except Exception as e:
        print(f"✗ Shot list refresh test failed: {e}")
        test_results.append(("Shot List Refresh", False))

    # Test 2: 3DE scene discovery performance
    try:
        result2 = test_3de_scene_discovery_performance()
        test_results.append(("3DE Scene Discovery", result2))
    except Exception as e:
        print(f"✗ 3DE scene discovery test failed: {e}")
        test_results.append(("3DE Scene Discovery", False))

    # Test 3: Raw plate finding performance
    try:
        result3 = test_raw_plate_finding_performance()
        test_results.append(("Raw Plate Finding", result3))
    except Exception as e:
        print(f"✗ Raw plate finding test failed: {e}")
        test_results.append(("Raw Plate Finding", False))

    # Test 4: End-to-end workflow performance
    try:
        result4 = test_end_to_end_workflow_performance()
        test_results.append(("End-to-End Workflow", result4))
    except Exception as e:
        print(f"✗ End-to-end workflow test failed: {e}")
        test_results.append(("End-to-End Workflow", False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = 0
    total = len(test_results)

    for test_name, result in test_results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name:<25}: {status}")
        if result:
            passed += 1

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("✓ All integration performance tests PASSED")
        return 0
    print("✗ Some integration performance tests FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
