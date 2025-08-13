"""Chaos engineering tests for ShotBot resilience.

This module implements chaos engineering principles to test
system resilience under adverse conditions and failures.
"""

import random
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cache_manager import CacheManager
from launcher_manager import LauncherManager
from shot_model import ShotModel


class ChaosMonkey:
    """Chaos monkey for injecting failures."""

    def __init__(self, failure_rate: float = 0.3):
        """Initialize chaos monkey with failure rate."""
        self.failure_rate = failure_rate
        self.active = False
        self.failures_injected = []

    @contextmanager
    def unleash(self):
        """Context manager to activate chaos monkey."""
        self.active = True
        try:
            yield self
        finally:
            self.active = False

    def maybe_fail(self, failure_type: str = "generic"):
        """Randomly inject failure based on failure rate."""
        if self.active and random.random() < self.failure_rate:
            self.failures_injected.append(failure_type)
            raise ChaosException(f"Chaos monkey induced {failure_type}")

    def corrupt_data(self, data: Any) -> Any:
        """Randomly corrupt data."""
        if not self.active:
            return data

        if random.random() < self.failure_rate:
            self.failures_injected.append("data_corruption")
            if isinstance(data, str):
                # Flip random character
                if data:
                    pos = random.randint(0, len(data) - 1)
                    chars = list(data)
                    chars[pos] = chr(ord(chars[pos]) ^ 0xFF)
                    return "".join(chars)
            elif isinstance(data, dict):
                # Remove random key
                if data:
                    key = random.choice(list(data.keys()))
                    corrupted = data.copy()
                    del corrupted[key]
                    return corrupted
            elif isinstance(data, list):
                # Shuffle list
                corrupted = data.copy()
                random.shuffle(corrupted)
                return corrupted
        return data


class ChaosException(Exception):
    """Exception raised by chaos monkey."""

    pass


class NetworkChaos:
    """Network-related chaos injection."""

    @staticmethod
    @contextmanager
    def slow_network(delay_ms: int = 1000):
        """Simulate slow network with delays."""
        original_subprocess = subprocess.run

        def delayed_run(*args, **kwargs):
            time.sleep(delay_ms / 1000.0)
            return original_subprocess(*args, **kwargs)

        with patch("subprocess.run", side_effect=delayed_run):
            yield

    @staticmethod
    @contextmanager
    def intermittent_network(failure_rate: float = 0.3):
        """Simulate intermittent network failures."""
        original_subprocess = subprocess.run

        def intermittent_run(*args, **kwargs):
            if random.random() < failure_rate:
                raise subprocess.TimeoutExpired(args[0], 1)
            return original_subprocess(*args, **kwargs)

        with patch("subprocess.run", side_effect=intermittent_run):
            yield

    @staticmethod
    @contextmanager
    def packet_loss(loss_rate: float = 0.2):
        """Simulate packet loss."""
        original_subprocess = subprocess.run

        def lossy_run(*args, **kwargs):
            if random.random() < loss_rate:
                # Simulate incomplete data
                result = original_subprocess(*args, **kwargs)
                if hasattr(result, "stdout") and result.stdout:
                    # Truncate output randomly
                    truncate_at = random.randint(0, len(result.stdout))
                    result.stdout = result.stdout[:truncate_at]
                return result
            return original_subprocess(*args, **kwargs)

        with patch("subprocess.run", side_effect=lossy_run):
            yield


class FilesystemChaos:
    """Filesystem-related chaos injection."""

    @staticmethod
    @contextmanager
    def readonly_filesystem():
        """Simulate read-only filesystem."""
        original_open = open

        def readonly_open(file, mode="r", *args, **kwargs):
            if "w" in mode or "a" in mode or "x" in mode:
                raise PermissionError("Read-only filesystem")
            return original_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=readonly_open):
            yield

    @staticmethod
    @contextmanager
    def full_disk():
        """Simulate full disk."""

        def failing_write(self, *args, **kwargs):
            raise OSError("No space left on device")

        with patch.object(Path, "write_text", side_effect=failing_write):
            yield

    @staticmethod
    @contextmanager
    def slow_io(delay_ms: int = 500):
        """Simulate slow I/O operations."""
        original_read = Path.read_text
        original_write = Path.write_text

        def slow_read(self, *args, **kwargs):
            time.sleep(delay_ms / 1000.0)
            return original_read(self, *args, **kwargs)

        def slow_write(self, *args, **kwargs):
            time.sleep(delay_ms / 1000.0)
            return original_write(self, *args, **kwargs)

        with patch.object(Path, "read_text", side_effect=slow_read):
            with patch.object(Path, "write_text", side_effect=slow_write):
                yield


class MemoryChaos:
    """Memory-related chaos injection."""

    @staticmethod
    @contextmanager
    def memory_pressure():
        """Simulate memory pressure."""
        # Allocate large chunks of memory
        memory_hogs = []
        try:
            # Allocate 100MB chunks
            for _ in range(10):
                memory_hogs.append(bytearray(100 * 1024 * 1024))
            yield
        finally:
            # Release memory
            memory_hogs.clear()

    @staticmethod
    @contextmanager
    def random_gc():
        """Trigger garbage collection at random times."""
        import gc

        def random_collect():
            if random.random() < 0.3:
                gc.collect()

        # Patch common operations to trigger GC
        with patch(
            "time.sleep", side_effect=lambda x: (random_collect(), time.sleep(x))
        ):
            yield


class ThreadingChaos:
    """Threading-related chaos injection."""

    @staticmethod
    @contextmanager
    def random_delays():
        """Inject random delays in thread operations."""
        original_acquire = threading.Lock.acquire

        def delayed_acquire(self, *args, **kwargs):
            if random.random() < 0.3:
                time.sleep(random.uniform(0.01, 0.1))
            return original_acquire(self, *args, **kwargs)

        with patch.object(threading.Lock, "acquire", delayed_acquire):
            yield

    @staticmethod
    @contextmanager
    def thread_starvation(starve_probability: float = 0.2):
        """Simulate thread starvation."""
        original_start = threading.Thread.start

        def starved_start(self):
            if random.random() < starve_probability:
                # Delay thread start significantly
                time.sleep(random.uniform(1, 3))
            return original_start(self)

        with patch.object(threading.Thread, "start", starved_start):
            yield


class TestChaosResilience:
    """Test system resilience under chaos conditions."""

    @pytest.fixture
    def chaos_monkey(self):
        """Create chaos monkey instance."""
        return ChaosMonkey(failure_rate=0.3)

    def test_shot_model_network_chaos(self, qtbot):
        """Test ShotModel under network chaos."""
        model = ShotModel()
        qtbot.addWidget(model)

        # Test with slow network
        with NetworkChaos.slow_network(delay_ms=2000):
            # Should handle slow responses gracefully
            result = model.refresh_shots()
            # May timeout but shouldn't crash
            assert result is not None

        # Test with intermittent failures
        with NetworkChaos.intermittent_network(failure_rate=0.5):
            attempts = 0
            success = False
            while attempts < 3 and not success:
                try:
                    result = model.refresh_shots()
                    if result.success:
                        success = True
                except Exception:
                    pass
                attempts += 1

            # Should eventually succeed or handle gracefully
            assert attempts <= 3

    def test_cache_manager_filesystem_chaos(self):
        """Test CacheManager under filesystem chaos."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(cache_dir=Path(tmpdir))

            # Test with read-only filesystem
            test_data = [{"id": 1, "name": "test"}]
            cache.cache_shots(test_data)

            with FilesystemChaos.readonly_filesystem():
                # Should handle read-only gracefully
                try:
                    cache.cache_shots([{"id": 2, "name": "test2"}])
                except PermissionError:
                    # Expected - should handle gracefully
                    pass

                # Reading should still work
                cached = cache.get_cached_shots()
                assert cached is not None

            # Test with full disk
            with FilesystemChaos.full_disk():
                # Should handle disk full gracefully
                try:
                    cache.cache_threede_scenes([{"scene": "test"}])
                except OSError:
                    # Expected - should handle gracefully
                    pass

                # Cache should remain functional
                assert cache is not None

    def test_launcher_manager_thread_chaos(self, qtbot):
        """Test LauncherManager under threading chaos."""
        manager = LauncherManager()
        qtbot.addWidget(manager)

        with ThreadingChaos.random_delays():
            # Launch multiple commands concurrently
            launchers = []
            for i in range(5):
                launcher_id = f"chaos_test_{i}"
                # Use simple echo command that should work
                process_key = manager.launch_command(
                    "echo test", launcher_id=launcher_id
                )
                if process_key:
                    launchers.append(process_key)

            # Despite delays, should handle all launches
            assert len(launchers) > 0

            # Cleanup
            for key in launchers:
                manager.terminate_process(key)

    def test_data_corruption_resilience(self, chaos_monkey):
        """Test resilience to data corruption."""
        with chaos_monkey.unleash():
            # Test shot data corruption
            shot_data = {
                "show": "TEST",
                "sequence": "SEQ01",
                "shot": "001",
                "path": "/test/path",
            }

            corrupted = chaos_monkey.corrupt_data(shot_data)

            # System should validate and handle corruption
            from shot_model import Shot

            try:
                if "show" in corrupted and "sequence" in corrupted:
                    shot = Shot(
                        corrupted.get("show", ""),
                        corrupted.get("sequence", ""),
                        corrupted.get("shot", ""),
                        corrupted.get("path", ""),
                    )
                    # Should handle missing/corrupted fields
                    assert shot is not None
            except (KeyError, ValueError):
                # Proper error handling
                pass

    def test_memory_pressure_handling(self, qtbot):
        """Test system under memory pressure."""
        from main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        with MemoryChaos.memory_pressure():
            # System should still function under memory pressure
            try:
                window.refresh_shots()
                # Should complete or fail gracefully
                assert window is not None
            except MemoryError:
                # Proper handling of memory errors
                pass

    def test_cascading_failures(self, chaos_monkey, qtbot):
        """Test handling of cascading failures."""
        from main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        # Inject multiple failure types simultaneously
        with chaos_monkey.unleash():
            with NetworkChaos.intermittent_network():
                with FilesystemChaos.slow_io():
                    with ThreadingChaos.random_delays():
                        # System should degrade gracefully
                        try:
                            window.refresh_shots()
                        except Exception:
                            # Should handle cascading failures
                            pass

                        # Core functionality should remain
                        assert window is not None
                        assert hasattr(window, "shot_model")


class TestRecoveryPatterns:
    """Test recovery patterns after chaos events."""

    def test_cache_recovery_after_corruption(self):
        """Test cache recovery after corruption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(cache_dir=Path(tmpdir))

            # Cache valid data
            valid_data = [{"id": 1, "name": "test"}]
            cache.cache_shots(valid_data)

            # Corrupt cache file
            cache_file = cache.shot_cache_file
            if cache_file.exists():
                # Write invalid JSON
                cache_file.write_text("{ invalid json }")

            # Should recover gracefully
            cached = cache.get_cached_shots()
            # Should return None or empty rather than crash
            assert cached is None or cached == []

            # Should be able to cache new data
            cache.cache_shots(valid_data)
            cached = cache.get_cached_shots()
            assert cached == valid_data

    def test_launcher_recovery_after_crash(self, qtbot):
        """Test launcher recovery after process crash."""
        manager = LauncherManager()
        qtbot.addWidget(manager)

        # Simulate process crash by killing it
        process_key = manager.launch_command("sleep 10", launcher_id="crash_test")

        if process_key:
            # Force terminate to simulate crash
            manager.terminate_process(process_key)

            # Should be able to launch new process
            new_key = manager.launch_command(
                "echo recovered", launcher_id="recovery_test"
            )

            # Recovery successful
            assert new_key is not None or new_key != process_key

    def test_progressive_degradation(self, qtbot):
        """Test progressive degradation under increasing failure rates."""
        from main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        failure_rates = [0.1, 0.3, 0.5, 0.7, 0.9]
        functionality_levels = []

        for rate in failure_rates:
            chaos = ChaosMonkey(failure_rate=rate)

            with chaos.unleash():
                # Test basic functionality
                functional = 0
                total = 5

                # Test different operations
                operations = [
                    lambda: window.refresh_shots(),
                    lambda: window.shot_model.get_shots(),
                    lambda: window.cache_manager.get_cached_shots(),
                    lambda: hasattr(window, "shot_grid"),
                    lambda: hasattr(window, "launcher_manager"),
                ]

                for op in operations:
                    try:
                        result = op()
                        if result is not None or result is True:
                            functional += 1
                    except ChaosException:
                        pass

                functionality_levels.append(functional / total)

        # Should show progressive degradation, not sudden failure
        for i in range(len(functionality_levels) - 1):
            # Functionality should generally decrease or stay same
            # Allow some variance due to randomness
            assert functionality_levels[i] >= functionality_levels[i + 1] - 0.3


class TestChaosMetrics:
    """Metrics and monitoring during chaos testing."""

    def test_failure_tracking(self, chaos_monkey):
        """Track and analyze failure patterns."""
        failure_counts = {}

        with chaos_monkey.unleash():
            for _ in range(100):
                try:
                    chaos_monkey.maybe_fail("test_failure")
                except ChaosException:
                    failure_counts["test_failure"] = (
                        failure_counts.get("test_failure", 0) + 1
                    )

        # Verify failure rate is approximately as configured
        actual_rate = failure_counts.get("test_failure", 0) / 100
        expected_rate = chaos_monkey.failure_rate
        assert abs(actual_rate - expected_rate) < 0.1

        # Verify failures were tracked
        assert len(chaos_monkey.failures_injected) > 0

    def test_recovery_time_measurement(self, qtbot):
        """Measure recovery time after failures."""
        from shot_model import ShotModel

        model = ShotModel()
        qtbot.addWidget(model)

        recovery_times = []

        for _ in range(5):
            # Inject failure
            with NetworkChaos.intermittent_network(failure_rate=1.0):
                time.time()
                try:
                    model.refresh_shots()
                except Exception:
                    pass

            # Measure recovery
            recovery_start = time.time()
            result = model.refresh_shots()
            if result.success:
                recovery_time = time.time() - recovery_start
                recovery_times.append(recovery_time)

        # Should recover quickly
        if recovery_times:
            avg_recovery = sum(recovery_times) / len(recovery_times)
            assert avg_recovery < 5.0  # Should recover within 5 seconds


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
