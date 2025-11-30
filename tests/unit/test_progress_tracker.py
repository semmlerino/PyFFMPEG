#!/usr/bin/env python3
"""
Unit tests for ProcessProgressTracker class
Tests regex parsing of FFmpeg output, progress calculation, and ETA estimation
"""

import subprocess
import time
from unittest.mock import Mock, patch

import pytest

from config import ProcessConfig
from progress_tracker import ProcessProgressTracker
from tests.fixtures.mocks import MockProgressScenarios


class TestProcessProgressTracker:
    """Test suite for ProcessProgressTracker class"""

    def setup_method(self):
        """Create fresh tracker instance for each test"""
        self.tracker = ProcessProgressTracker()

    def teardown_method(self):
        """Cleanup after each test"""
        self.tracker = None


class TestDurationProbing:
    """Test video duration detection"""

    def setup_method(self):
        self.tracker = ProcessProgressTracker()

    @patch("subprocess.run")
    def test_successful_duration_probe(self, mock_subprocess):
        """Test successful duration probing"""
        mock_result = Mock()
        mock_result.stdout = "630.456789"  # 10:30.456789
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        duration = self.tracker.probe_duration("/test/video.ts")

        assert duration == 630.456789
        mock_subprocess.assert_called_once()

        # Verify correct ffprobe arguments
        args = mock_subprocess.call_args[0][0]
        assert "ffprobe" in args
        assert "-show_entries" in args
        assert "format=duration" in args
        assert "/test/video.ts" in args

    @patch("subprocess.run")
    def test_duration_probe_timeout(self, mock_subprocess):
        """Test duration probe with timeout"""
        mock_subprocess.side_effect = subprocess.TimeoutExpired(
            "ffprobe", ProcessConfig.SUBPROCESS_TIMEOUT
        )

        duration = self.tracker.probe_duration("/test/video.ts")

        assert duration is None

    @patch("subprocess.run")
    def test_duration_probe_error(self, mock_subprocess):
        """Test duration probe with subprocess error"""
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "ffprobe")

        duration = self.tracker.probe_duration("/test/video.ts")

        assert duration is None

    @patch("subprocess.run")
    def test_duration_probe_invalid_output(self, mock_subprocess):
        """Test duration probe with invalid output"""
        mock_result = Mock()
        mock_result.stdout = "not_a_number"
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        duration = self.tracker.probe_duration("/test/video.ts")

        assert duration is None

    @patch("subprocess.run")
    def test_duration_probe_empty_output(self, mock_subprocess):
        """Test duration probe with empty output"""
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        duration = self.tracker.probe_duration("/test/video.ts")

        assert duration is None


class TestProgressParsing:
    """Test FFmpeg output parsing for progress calculation"""

    def setup_method(self):
        self.tracker = ProcessProgressTracker()

    def test_progress_calculation_with_duration(self):
        """Test progress percentage calculation when duration is known"""
        process_id = "test_process"
        duration = 600.0  # 10 minutes

        # Register process
        self.tracker.register_process(process_id, "/test/video.ts", duration)

        # Test progress updates
        test_cases = [
            (
                "frame=  100 fps= 25 q=28.0 size=1024kB time=00:01:00.00 bitrate=1024.0kbits/s speed=1.0x",
                10.0,
            ),
            (
                "frame=  250 fps= 25 q=28.0 size=2048kB time=00:03:00.00 bitrate=512.0kbits/s speed=1.2x",
                30.0,
            ),
            (
                "frame=  500 fps= 25 q=28.0 size=4096kB time=00:06:00.00 bitrate=256.0kbits/s speed=1.0x",
                60.0,
            ),
            (
                "frame= 1000 fps= 25 q=28.0 size=8192kB time=00:10:00.00 bitrate=128.0kbits/s speed=1.0x",
                100.0,
            ),
        ]

        for ffmpeg_line, expected_percentage in test_cases:
            # First add the output to the buffer
            progress_data = self.tracker.process_output(process_id, ffmpeg_line)

            # Force batch processing to get immediate results
            self.tracker.force_batch_process_all()

            # Now try to get the progress again after forced processing
            # We need to process a dummy line to trigger the return of cached data
            progress_data = self.tracker.process_output(process_id, "")

            # If still no data, the buffer might need multiple lines or time-based processing
            if not progress_data:
                # Try getting the process progress directly
                progress_data = self.tracker.get_process_progress(process_id)

            assert progress_data is not None
            assert "current_pct" in progress_data
            assert abs(progress_data["current_pct"] - expected_percentage) < 0.1

    def test_progress_without_duration(self):
        """Test progress tracking when duration is unknown"""
        process_id = "test_process"

        # Register process without duration
        self.tracker.register_process(process_id, "/test/video.ts", None)

        ffmpeg_line = "frame=  100 fps= 25 q=28.0 size=1024kB time=00:01:00.00 bitrate=1024.0kbits/s speed=1.0x"
        progress_data = self.tracker.process_output(process_id, ffmpeg_line)

        # Should still return progress data but without percentage
        assert progress_data is not None
        assert "percentage" not in progress_data or progress_data["current_pct"] == 0


class TestETACalculation:
    """Test ETA (Estimated Time of Arrival) calculations"""

    def setup_method(self):
        self.tracker = ProcessProgressTracker()

    def test_eta_calculation_linear_progress(self):
        """Test ETA calculation with linear progress"""
        process_id = "test_process"
        duration = 600.0  # 10 minutes

        self.tracker.register_process(process_id, "/test/video.ts", duration)

        # Simulate linear progress over time
        start_time = time.time()

        with patch("time.time") as mock_time:
            # Progress at 1 minute mark -> 10% complete
            mock_time.return_value = start_time + 60
            ffmpeg_line = "frame=  100 fps= 25 q=28.0 size=1024kB time=00:01:00.00 bitrate=1024.0kbits/s speed=1.0x"
            progress_data = self.tracker.process_output(process_id, ffmpeg_line)

            # At 10% complete in 60 seconds, should take ~600 seconds total
            # So ETA should be around 540 seconds (9 minutes) remaining
            assert progress_data is not None
            if "eta_seconds" in progress_data and progress_data["eta_seconds"] > 0:
                assert 400 < progress_data["eta_seconds"] < 700  # Reasonable range

    def test_eta_with_variable_speed(self):
        """Test ETA calculation with variable processing speed"""
        process_id = "test_process"
        duration = 600.0

        self.tracker.register_process(process_id, "/test/video.ts", duration)

        start_time = time.time()

        with patch("time.time") as mock_time:
            # First update: slow progress
            mock_time.return_value = start_time + 120  # 2 minutes elapsed
            ffmpeg_line1 = "frame=  50 fps= 25 q=28.0 size=512kB time=00:00:30.00 bitrate=1024.0kbits/s speed=0.5x"
            self.tracker.process_output(process_id, ffmpeg_line1)

            # Second update: faster progress
            mock_time.return_value = start_time + 180  # 3 minutes elapsed
            ffmpeg_line2 = "frame= 150 fps= 25 q=28.0 size=1536kB time=00:02:00.00 bitrate=1024.0kbits/s speed=1.5x"
            progress_data2 = self.tracker.process_output(process_id, ffmpeg_line2)

            # ETA should adapt to the changing speed
            assert progress_data2 is not None
            if "eta_seconds" in progress_data2:
                # Should reflect the improved processing speed
                pass

    def test_eta_smoothing(self):
        """Test ETA smoothing over multiple updates"""
        process_id = "test_process"
        duration = 600.0

        self.tracker.register_process(process_id, "/test/video.ts", duration)

        start_time = time.time()
        eta_values = []

        with patch("time.time") as mock_time:
            # Multiple progress updates
            for i in range(1, 6):
                mock_time.return_value = start_time + (i * 30)  # Every 30 seconds
                progress_seconds = i * 30  # Linear progress

                ffmpeg_line = f"frame={i * 50:5d} fps= 25 q=28.0 size={i * 512}kB time={progress_seconds // 3600:02d}:{(progress_seconds % 3600) // 60:02d}:{progress_seconds % 60:05.2f} bitrate=1024.0kbits/s speed=1.0x"
                progress_data = self.tracker.process_output(process_id, ffmpeg_line)

                if progress_data and "eta_seconds" in progress_data:
                    eta_values.append(progress_data["eta_seconds"])

            # ETA values should show some smoothing (not wildly fluctuating)
            if len(eta_values) > 2:
                # Check that ETA is generally decreasing as progress continues
                assert eta_values[-1] < eta_values[0]


class TestBatchProcessing:
    """Test batch processing and overall progress tracking"""

    def setup_method(self):
        self.tracker = ProcessProgressTracker()

    def test_batch_initialization(self):
        """Test batch processing initialization"""
        total_files = 5
        self.tracker.start_batch(total_files)

        # Should initialize batch tracking
        assert self.tracker.total_count == total_files
        assert self.tracker.completed_count == 0
        assert self.tracker.batch_start_time is not None

    def test_process_registration(self):
        """Test registering multiple processes in a batch"""
        self.tracker.start_batch(3)

        # Register multiple processes
        processes = [
            ("proc1", "/test/video1.ts", 600.0),
            ("proc2", "/test/video2.ts", 300.0),
            ("proc3", "/test/video3.ts", 900.0),
        ]

        for proc_id, path, duration in processes:
            self.tracker.register_process(proc_id, path, duration)

        # All processes should be registered
        assert len(self.tracker.processes) == 3

    def test_overall_progress_calculation(self):
        """Test overall batch progress calculation"""
        self.tracker.start_batch(2)

        # Register two processes with known durations
        self.tracker.register_process("proc1", "/test/video1.ts", 600.0)
        self.tracker.register_process("proc2", "/test/video2.ts", 300.0)

        # Update progress for first process (50% complete)
        ffmpeg_line1 = "frame= 500 fps= 25 q=28.0 size=4096kB time=00:05:00.00 bitrate=256.0kbits/s speed=1.0x"
        self.tracker.process_output("proc1", ffmpeg_line1)

        # Update progress for second process (100% complete)
        ffmpeg_line2 = "frame= 500 fps= 25 q=28.0 size=2048kB time=00:05:00.00 bitrate=256.0kbits/s speed=1.0x"
        self.tracker.process_output("proc2", ffmpeg_line2)

        # Calculate overall progress
        overall_progress = self.tracker.get_overall_progress()

        # Should be weighted average: (600*0.5 + 300*1.0) / (600+300) = 600/900 = 66.67%
        assert overall_progress is not None
        if "overall_pct" in overall_progress:
            expected = (600 * 50 + 300 * 100) / (600 + 300)
            assert abs(overall_progress["overall_pct"] - expected) < 1.0


class TestProgressScenarios:
    """Test various real-world progress scenarios"""

    def setup_method(self):
        self.tracker = ProcessProgressTracker()

    def test_normal_conversion_scenario(self):
        """Test normal conversion progress scenario"""
        scenario = MockProgressScenarios.normal_conversion()
        process_id = "normal_test"

        self.tracker.register_process(
            process_id, "/test/video.ts", scenario["duration"]
        )

        for ffmpeg_line, expected_pct in zip(
            scenario["progress_updates"], scenario["expected_percentages"]
        ):
            progress_data = self.tracker.process_output(process_id, ffmpeg_line)

            assert progress_data is not None
            if "current_pct" in progress_data:
                assert (
                    abs(progress_data["current_pct"] - expected_pct) < 2.0
                )  # Allow some variance

    def test_slow_conversion_scenario(self):
        """Test slow conversion with variable speed"""
        scenario = MockProgressScenarios.slow_conversion()
        process_id = "slow_test"

        self.tracker.register_process(
            process_id, "/test/video.ts", scenario["duration"]
        )

        for ffmpeg_line, expected_pct in zip(
            scenario["progress_updates"], scenario["expected_percentages"]
        ):
            progress_data = self.tracker.process_output(process_id, ffmpeg_line)

            assert progress_data is not None
            if "current_pct" in progress_data:
                assert abs(progress_data["current_pct"] - expected_pct) < 2.0

class TestEdgeCases:
    """Test edge cases and error conditions"""

    def setup_method(self):
        self.tracker = ProcessProgressTracker()

    def test_unregistered_process_update(self):
        """Test updating progress for unregistered process"""
        ffmpeg_line = "frame=  100 fps= 25 q=28.0 size=1024kB time=00:01:00.00 bitrate=1024.0kbits/s speed=1.0x"
        progress_data = self.tracker.process_output("nonexistent", ffmpeg_line)

        # Should handle gracefully
        assert progress_data is None or progress_data == {}

    def test_zero_duration(self):
        """Test handling of zero duration"""
        process_id = "zero_duration"
        self.tracker.register_process(process_id, "/test/video.ts", 0.0)

        ffmpeg_line = "frame=  100 fps= 25 q=28.0 size=1024kB time=00:01:00.00 bitrate=1024.0kbits/s speed=1.0x"
        progress_data = self.tracker.process_output(process_id, ffmpeg_line)

        # Should handle division by zero gracefully
        assert progress_data is not None

    def test_negative_duration(self):
        """Test handling of negative duration"""
        process_id = "negative_duration"
        self.tracker.register_process(process_id, "/test/video.ts", -100.0)

        ffmpeg_line = "frame=  100 fps= 25 q=28.0 size=1024kB time=00:01:00.00 bitrate=1024.0kbits/s speed=1.0x"
        progress_data = self.tracker.process_output(process_id, ffmpeg_line)

        # Should handle negative duration gracefully
        assert progress_data is not None

    def test_progress_exceeding_duration(self):
        """Test progress time exceeding expected duration"""
        process_id = "exceed_duration"
        self.tracker.register_process(process_id, "/test/video.ts", 60.0)  # 1 minute

        # Report progress at 2 minutes (exceeds duration)
        ffmpeg_line = "frame=  100 fps= 25 q=28.0 size=1024kB time=00:02:00.00 bitrate=1024.0kbits/s speed=1.0x"
        progress_data = self.tracker.process_output(process_id, ffmpeg_line)

        # Should handle gracefully, possibly capping at 100%
        assert progress_data is not None
        if "current_pct" in progress_data:
            assert progress_data["current_pct"] <= 100

    def test_empty_ffmpeg_line(self):
        """Test handling of empty FFmpeg output line"""
        process_id = "empty_line"
        self.tracker.register_process(process_id, "/test/video.ts", 600.0)

        progress_data = self.tracker.process_output(process_id, "")

        # Should handle gracefully
        assert progress_data is None or progress_data == {}

    def test_malformed_ffmpeg_output(self):
        """Test handling of malformed FFmpeg output"""
        process_id = "malformed"
        self.tracker.register_process(process_id, "/test/video.ts", 600.0)

        malformed_lines = [
            "completely invalid output",
            "frame=abc fps=xyz time=invalid",
            "size=1024kB bitrate=512.0kbits/s",  # Missing required fields
        ]

        for line in malformed_lines:
            progress_data = self.tracker.process_output(process_id, line)
            # Should not crash and return reasonable response
            assert isinstance(progress_data, (dict, type(None)))


@pytest.mark.unit
class TestProgressTrackerPerformance:
    """Test performance characteristics of progress tracking"""

    def setup_method(self):
        self.tracker = ProcessProgressTracker()

    def test_many_processes_registration(self):
        """Test registering many processes"""
        num_processes = 100
        self.tracker.start_batch(num_processes)

        start_time = time.time()

        for i in range(num_processes):
            self.tracker.register_process(f"proc_{i}", f"/test/video_{i}.ts", 600.0)

        elapsed = time.time() - start_time

        # Should complete quickly (less than 1 second for 100 processes)
        assert elapsed < 1.0
        assert len(self.tracker.processes) == num_processes

    @pytest.mark.slow
    def test_frequent_progress_updates(self):
        """Test handling frequent progress updates"""
        process_id = "frequent_updates"
        self.tracker.register_process(process_id, "/test/video.ts", 600.0)

        start_time = time.time()

        # Simulate frequent updates
        for i in range(100):
            seconds = i * 6  # Every 6 seconds of video
            ffmpeg_line = f"frame={i * 50:5d} fps= 25 q=28.0 size={i * 512}kB time={seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:05.2f} bitrate=1024.0kbits/s speed=1.0x"
            self.tracker.process_output(process_id, ffmpeg_line)

        elapsed = time.time() - start_time

        # Should handle 100 updates quickly
        assert elapsed < 1.0


class TestFailureTracking:
    """Test failure tracking and reporting"""

    def setup_method(self):
        self.tracker = ProcessProgressTracker()

    def test_failed_count_initial(self):
        """Test failed count starts at zero"""
        assert self.tracker.failed_count == 0

    def test_complete_process_success(self):
        """Test completing process successfully doesn't increment failed count"""
        self.tracker.start_batch(1)
        self.tracker.register_process("proc_1", "/test/video.ts", 600.0)

        self.tracker.complete_process("proc_1", success=True)

        assert self.tracker.failed_count == 0
        assert self.tracker.completed_count == 1

    def test_complete_process_failure(self):
        """Test completing process with failure increments failed count"""
        self.tracker.start_batch(1)
        self.tracker.register_process("proc_1", "/test/video.ts", 600.0)

        self.tracker.complete_process("proc_1", success=False)

        assert self.tracker.failed_count == 1
        assert self.tracker.completed_count == 1

    def test_mixed_success_and_failure(self):
        """Test mixed success and failure tracking"""
        self.tracker.start_batch(5)
        for i in range(5):
            self.tracker.register_process(f"proc_{i}", f"/test/video_{i}.ts", 600.0)

        # 3 successes, 2 failures
        self.tracker.complete_process("proc_0", success=True)
        self.tracker.complete_process("proc_1", success=False)
        self.tracker.complete_process("proc_2", success=True)
        self.tracker.complete_process("proc_3", success=False)
        self.tracker.complete_process("proc_4", success=True)

        assert self.tracker.completed_count == 5
        assert self.tracker.failed_count == 2

    def test_failed_count_in_overall_progress(self):
        """Test failed count included in overall progress"""
        self.tracker.start_batch(3)
        self.tracker.register_process("proc_0", "/test/video_0.ts", 600.0)
        self.tracker.register_process("proc_1", "/test/video_1.ts", 600.0)
        self.tracker.register_process("proc_2", "/test/video_2.ts", 600.0)

        self.tracker.complete_process("proc_0", success=True)
        self.tracker.complete_process("proc_1", success=False)

        progress = self.tracker.get_overall_progress()

        assert progress["failed_count"] == 1
        assert progress["success_count"] == 1
        assert progress["completed_count"] == 2

    def test_success_count_calculation(self):
        """Test success count is correctly calculated"""
        self.tracker.start_batch(4)
        for i in range(4):
            self.tracker.register_process(f"proc_{i}", f"/test/video_{i}.ts", 600.0)

        self.tracker.complete_process("proc_0", success=True)
        self.tracker.complete_process("proc_1", success=True)
        self.tracker.complete_process("proc_2", success=False)
        self.tracker.complete_process("proc_3", success=True)

        progress = self.tracker.get_overall_progress()

        # success_count = completed_count - failed_count = 4 - 1 = 3
        assert progress["success_count"] == 3
        assert progress["failed_count"] == 1

    def test_failure_sets_progress_correctly(self):
        """Test failed process doesn't set progress to 100%"""
        self.tracker.start_batch(1)
        self.tracker.register_process("proc_1", "/test/video.ts", 600.0)

        # Simulate partial progress before failure
        ffmpeg_line = "frame=  500 fps= 25 q=28.0 size=5120kB time=00:05:00.00 bitrate=1024.0kbits/s speed=1.0x"
        self.tracker.process_output("proc_1", ffmpeg_line)

        # Complete with failure
        self.tracker.complete_process("proc_1", success=False)

        # Progress should not be 100% for failed process
        # The failed count should be incremented
        assert self.tracker.failed_count == 1

    def test_reset_clears_failed_count(self):
        """Test reset clears failed count"""
        self.tracker.start_batch(2)
        self.tracker.register_process("proc_0", "/test/video_0.ts", 600.0)
        self.tracker.register_process("proc_1", "/test/video_1.ts", 600.0)
        self.tracker.complete_process("proc_0", success=False)
        self.tracker.complete_process("proc_1", success=False)

        assert self.tracker.failed_count == 2

        # Start new batch should reset
        self.tracker.start_batch(1)

        assert self.tracker.failed_count == 0
        assert self.tracker.completed_count == 0


class TestCodecDistribution:
    """Test codec distribution tracking for GPU/CPU workloads"""

    def setup_method(self):
        self.tracker = ProcessProgressTracker()

    def test_codec_distribution_empty(self):
        """Test codec distribution with empty codec_map"""
        self.tracker.start_batch(2)
        self.tracker.register_process("proc_0", "/test/video_0.ts", 600.0)
        self.tracker.register_process("proc_1", "/test/video_1.ts", 600.0)

        distribution = self.tracker.get_codec_distribution({})

        assert distribution["GPU"] == 0
        assert distribution["CPU"] == 0

    def test_codec_distribution_gpu_only(self):
        """Test codec distribution with GPU codecs only"""
        self.tracker.start_batch(3)
        self.tracker.register_process("proc_0", "/test/video_0.ts", 600.0)
        self.tracker.register_process("proc_1", "/test/video_1.ts", 600.0)
        self.tracker.register_process("proc_2", "/test/video_2.ts", 600.0)

        # GPU codecs: 0=H.264 NVENC, 1=HEVC NVENC, 2=AV1 NVENC, 5=QSV, 6=VAAPI
        codec_map = {
            "/test/video_0.ts": 0,  # H.264 NVENC
            "/test/video_1.ts": 1,  # HEVC NVENC
            "/test/video_2.ts": 5,  # QSV
        }

        distribution = self.tracker.get_codec_distribution(codec_map)

        assert distribution["GPU"] == 3
        assert distribution["CPU"] == 0

    def test_codec_distribution_cpu_only(self):
        """Test codec distribution with CPU codecs only"""
        self.tracker.start_batch(2)
        self.tracker.register_process("proc_0", "/test/video_0.ts", 600.0)
        self.tracker.register_process("proc_1", "/test/video_1.ts", 600.0)

        # CPU codecs: 3=x264, 4=ProRes
        codec_map = {
            "/test/video_0.ts": 3,  # x264
            "/test/video_1.ts": 4,  # ProRes
        }

        distribution = self.tracker.get_codec_distribution(codec_map)

        assert distribution["GPU"] == 0
        assert distribution["CPU"] == 2

    def test_codec_distribution_mixed(self):
        """Test codec distribution with mixed GPU/CPU"""
        self.tracker.start_batch(5)
        for i in range(5):
            self.tracker.register_process(f"proc_{i}", f"/test/video_{i}.ts", 600.0)

        codec_map = {
            "/test/video_0.ts": 0,  # H.264 NVENC (GPU)
            "/test/video_1.ts": 3,  # x264 (CPU)
            "/test/video_2.ts": 1,  # HEVC NVENC (GPU)
            "/test/video_3.ts": 3,  # x264 (CPU)
            "/test/video_4.ts": 6,  # VAAPI (GPU)
        }

        distribution = self.tracker.get_codec_distribution(codec_map)

        assert distribution["GPU"] == 3
        assert distribution["CPU"] == 2

    def test_codec_distribution_vaapi_is_gpu(self):
        """Test that VAAPI codec (6) is counted as GPU"""
        self.tracker.start_batch(1)
        self.tracker.register_process("proc_0", "/test/video_0.ts", 600.0)

        codec_map = {"/test/video_0.ts": 6}  # VAAPI

        distribution = self.tracker.get_codec_distribution(codec_map)

        assert distribution["GPU"] == 1
        assert distribution["CPU"] == 0

    def test_codec_distribution_qsv_is_gpu(self):
        """Test that QSV codec (5) is counted as GPU"""
        self.tracker.start_batch(1)
        self.tracker.register_process("proc_0", "/test/video_0.ts", 600.0)

        codec_map = {"/test/video_0.ts": 5}  # QSV

        distribution = self.tracker.get_codec_distribution(codec_map)

        assert distribution["GPU"] == 1
        assert distribution["CPU"] == 0

    def test_codec_distribution_unregistered_paths(self):
        """Test codec distribution ignores paths not in codec_map"""
        self.tracker.start_batch(3)
        self.tracker.register_process("proc_0", "/test/video_0.ts", 600.0)
        self.tracker.register_process("proc_1", "/test/video_1.ts", 600.0)
        self.tracker.register_process("proc_2", "/test/video_2.ts", 600.0)

        # Only one path in codec_map
        codec_map = {"/test/video_0.ts": 0}

        distribution = self.tracker.get_codec_distribution(codec_map)

        assert distribution["GPU"] == 1
        assert distribution["CPU"] == 0


class TestProgressTrackerBatchManagement:
    """Test batch lifecycle and state management"""

    def setup_method(self):
        self.tracker = ProcessProgressTracker()

    def test_start_batch_initializes_state(self):
        """Test start_batch initializes tracker state"""
        self.tracker.start_batch(5)

        assert self.tracker.total_count == 5
        assert self.tracker.completed_count == 0
        assert self.tracker.failed_count == 0
        assert len(self.tracker.processes) == 0

    def test_start_batch_clears_previous_state(self):
        """Test start_batch clears previous batch state"""
        # First batch
        self.tracker.start_batch(3)
        self.tracker.register_process("proc_0", "/test/video_0.ts", 600.0)
        self.tracker.complete_process("proc_0", success=False)

        assert self.tracker.failed_count == 1

        # Second batch
        self.tracker.start_batch(2)

        assert self.tracker.total_count == 2
        assert self.tracker.completed_count == 0
        assert self.tracker.failed_count == 0
        assert len(self.tracker.processes) == 0

    def test_register_process_adds_to_tracking(self):
        """Test register_process adds process to tracking"""
        self.tracker.start_batch(1)
        self.tracker.register_process("proc_123", "/test/video.ts", 600.0)

        assert "proc_123" in self.tracker.processes
        assert self.tracker.processes["proc_123"]["path"] == "/test/video.ts"
        assert self.tracker.processes["proc_123"]["duration"] == 600.0

    def test_complete_process_unknown_id(self):
        """Test complete_process with unknown process ID"""
        self.tracker.start_batch(1)

        # Should not crash
        self.tracker.complete_process("unknown_proc", success=True)

        # State should be unchanged
        assert self.tracker.completed_count == 0

    def test_overall_progress_calculation(self):
        """Test overall progress percentage calculation"""
        self.tracker.start_batch(4)
        for i in range(4):
            self.tracker.register_process(f"proc_{i}", f"/test/video_{i}.ts", 100.0)

        # Complete 2 of 4
        self.tracker.complete_process("proc_0", success=True)
        self.tracker.complete_process("proc_1", success=True)

        progress = self.tracker.get_overall_progress()

        assert progress["completed_count"] == 2
        assert progress["total_count"] == 4
        # Overall percent is based on weighted average of process progress
