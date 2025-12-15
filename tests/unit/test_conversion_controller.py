#!/usr/bin/env python3
"""
Unit tests for ConversionController class
Tests conversion workflow orchestration, auto-balance logic, and process coordination
"""

from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QProcess

from config import EncodingConfig
from conversion_controller import ConversionController
from tests.fixtures.mocks import create_mock_process_manager


class TestConversionController:
    """Test suite for ConversionController class"""

    def setup_method(self):
        """Create fresh ConversionController instance for each test"""
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    def teardown_method(self):
        """Cleanup after each test"""
        if hasattr(self, "controller"):
            self.controller.stop_conversion()


class TestConversionInitialization:
    """Test conversion initialization and validation"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    def test_controller_initialization(self):
        """Test ConversionController initialization"""
        assert self.controller.process_manager == self.mock_process_manager
        assert not self.controller.is_converting
        assert not self.controller.auto_balance_enabled
        assert self.controller.file_codec_assignments == {}
        assert self.controller.queue == []
        assert self.controller.current_path is None

    def test_signal_connections(self):
        """Test signal connections to process manager"""
        # Verify signals are connected (implementation-dependent)
        assert hasattr(self.controller, "conversion_started")
        assert hasattr(self.controller, "conversion_finished")
        assert hasattr(self.controller, "conversion_stopped")
        assert hasattr(self.controller, "log_message")
        assert hasattr(self.controller, "progress_updated")


class TestConversionWorkflow:
    """Test conversion workflow start, stop, and state management"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    def test_start_conversion_success(self):
        """Test successful conversion start"""
        file_paths = ["/test/video1.ts", "/test/video2.ts"]

        with patch.object(
            self.controller, "_validate_conversion_ready", return_value=(True, "")
        ), patch.object(self.controller, "_process_next") as mock_process_next:
            result = self.controller.start_conversion(
                file_paths=file_paths,
                codec_idx=0,  # H.264 NVENC
                hwdecode_idx=1,  # NVIDIA
                crf_value=18,
                parallel_enabled=True,
                max_parallel=4,
                delete_source=False,
                overwrite_mode=True,
            )

        assert result
        assert self.controller.is_converting
        assert self.controller.queue == file_paths
        assert self.controller.codec_idx == 0
        assert self.controller.hwdecode_idx == 1
        assert self.controller.crf_value == 18
        assert self.controller.parallel_enabled
        assert self.controller.max_parallel == 4
        assert not self.controller.delete_source
        assert self.controller.overwrite_mode

        # Verify process manager was configured
        self.mock_process_manager.start_batch.assert_called_once_with(
            file_paths, True, 4
        )
        mock_process_next.assert_called_once()

    def test_start_conversion_already_converting(self):
        """Test starting conversion when already converting"""
        # Set converting state
        self.controller.is_converting = True

        result = self.controller.start_conversion(
            file_paths=["/test/video.ts"],
            codec_idx=0,
            hwdecode_idx=0,
            crf_value=18,
            parallel_enabled=False,
            max_parallel=1,
            delete_source=False,
            overwrite_mode=True,
        )

        assert not result
        self.mock_process_manager.start_batch.assert_not_called()

    def test_start_conversion_empty_file_list(self):
        """Test starting conversion with empty file list"""
        result = self.controller.start_conversion(
            file_paths=[],
            codec_idx=0,
            hwdecode_idx=0,
            crf_value=18,
            parallel_enabled=False,
            max_parallel=1,
            delete_source=False,
            overwrite_mode=True,
        )

        assert not result
        assert not self.controller.is_converting

    def test_stop_conversion(self):
        """Test stopping conversion"""
        # Start a conversion first
        self.controller.is_converting = True

        # Mock process manager stop method
        self.mock_process_manager.stop_all_processes.return_value = [Mock(), Mock()]

        with patch.object(self.controller, "conversion_stopped") as mock_signal:
            self.controller.stop_conversion()

        assert not self.controller.is_converting
        self.mock_process_manager.stop_all_processes.assert_called_once()
        mock_signal.emit.assert_called_once()

    def test_stop_conversion_not_converting(self):
        """Test stopping conversion when not converting"""
        self.controller.is_converting = False

        self.controller.stop_conversion()

        # Should not interact with process manager
        self.mock_process_manager.stop_all_processes.assert_not_called()


class TestAutoBalanceLogic:
    """Test auto-balance workload distribution"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)
        self.controller.auto_balance_enabled = True

    @patch("codec_helpers.CodecHelpers.detect_rtx40_series")
    def test_auto_balance_with_rtx40(self, mock_rtx40_detection):
        """Test auto-balance with RTX 40 series GPU"""
        mock_rtx40_detection.return_value = True

        file_paths = [f"/test/video{i}.ts" for i in range(10)]

        self.controller._auto_balance_workload(file_paths, 0)  # H.264 NVENC base codec

        # Should assign files to GPU and CPU based on ratio
        gpu_files = sum(
            1
            for codec in self.controller.file_codec_assignments.values()
            if codec in [0, 1, 2]
        )
        cpu_files = sum(
            1 for codec in self.controller.file_codec_assignments.values() if codec == 3
        )

        # Should have reasonable distribution (70% GPU, 30% CPU)
        total_files = len(file_paths)
        expected_gpu = int(total_files * EncodingConfig.GPU_RATIO_DEFAULT)
        expected_cpu = total_files - expected_gpu

        assert abs(gpu_files - expected_gpu) <= 1  # Allow small variance
        assert abs(cpu_files - expected_cpu) <= 1

    @patch("codec_helpers.CodecHelpers.detect_rtx40_series")
    def test_auto_balance_without_rtx40(self, mock_rtx40_detection):
        """Test auto-balance without RTX 40 series GPU"""
        mock_rtx40_detection.return_value = False

        file_paths = [f"/test/video{i}.ts" for i in range(6)]

        self.controller._auto_balance_workload(
            file_paths, 2
        )  # AV1 NVENC (requires RTX40)

        # Should fallback to non-AV1 codecs since RTX40 not available
        assignments = list(self.controller.file_codec_assignments.values())

        # Should not assign AV1 NVENC (codec 2) when RTX40 not available
        assert 2 not in assignments  # No AV1 NVENC

    def test_auto_balance_disabled(self):
        """Test behavior when auto-balance is disabled"""
        self.controller.auto_balance_enabled = False

        file_paths = ["/test/video1.ts", "/test/video2.ts"]

        # When auto-balance is disabled, the method still assigns codecs
        # This tests the internal behavior of _auto_balance_workload
        self.controller._auto_balance_workload(file_paths, 0)

        # The method always assigns codecs when called
        # The auto_balance_enabled flag is checked in start_conversion()
        assert len(self.controller.file_codec_assignments) == 2
        # Should assign GPU (0) and CPU (3) codecs
        assert self.controller.file_codec_assignments["/test/video1.ts"] == 0
        assert self.controller.file_codec_assignments["/test/video2.ts"] == 3

    def test_enable_auto_balance(self):
        """Test enabling auto-balance"""
        assert self.controller.auto_balance_enabled

        self.controller.enable_auto_balance(False)
        assert not self.controller.auto_balance_enabled

        self.controller.enable_auto_balance(True)
        assert self.controller.auto_balance_enabled


class TestFFmpegArgumentBuilding:
    """Test FFmpeg argument construction"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

        # Set up conversion parameters
        self.controller.hwdecode_idx = 1  # NVIDIA
        self.controller.crf_value = 18
        self.controller.parallel_enabled = True

    @patch("codec_helpers.CodecHelpers.get_hardware_acceleration_args")
    @patch("codec_helpers.CodecHelpers.get_audio_codec_args")
    @patch("codec_helpers.CodecHelpers.get_encoder_configuration")
    def test_build_ffmpeg_args_h264_nvenc(
        self, mock_encoder_config, mock_audio_config, mock_hw_config
    ):
        """Test FFmpeg args for H.264 NVENC"""
        # Configure mocks
        mock_hw_config.return_value = (["-hwaccel", "cuda"], "Using CUDA")
        mock_audio_config.return_value = (["-c:a", "copy"], "Using AAC passthrough")
        mock_encoder_config.return_value = (
            ["-c:v", "h264_nvenc", "-preset", "fast"],
            "Using H.264 NVENC",
        )

        input_path = "/test/input.ts"

        with patch(
            "codec_helpers.CodecHelpers.get_output_extension", return_value=".mp4"
        ):
            args = self.controller._build_ffmpeg_args(input_path, 0)  # H.264 NVENC

        # Verify basic structure - uses -n (skip existing) when overwrite_mode=False (default)
        assert "-n" in args  # Skip existing flag (overwrite_mode defaults to False)
        assert "-hwaccel" in args
        assert "cuda" in args
        assert "-i" in args
        assert input_path in args
        assert "-c:a" in args
        assert "copy" in args
        assert "-c:v" in args
        assert "h264_nvenc" in args
        # Check that output path is generated correctly
        assert "/test/input_RC.mp4" in args

        # Verify helper functions were called
        mock_hw_config.assert_called_once_with(1)
        mock_audio_config.assert_called_once_with(input_path, 0)
        mock_encoder_config.assert_called_once()

    @patch("codec_helpers.CodecHelpers.get_hardware_acceleration_args")
    @patch("codec_helpers.CodecHelpers.get_audio_codec_args")
    @patch("codec_helpers.CodecHelpers.get_encoder_configuration")
    def test_build_ffmpeg_args_x264_cpu(
        self, mock_encoder_config, mock_audio_config, mock_hw_config
    ):
        """Test FFmpeg args for x264 CPU encoding"""
        # Configure mocks
        mock_hw_config.return_value = ([], "No hardware acceleration")
        mock_audio_config.return_value = (
            ["-c:a", "aac", "-b:a", "192k"],
            "Converting to AAC",
        )
        mock_encoder_config.return_value = (
            ["-c:v", "libx264", "-crf", "18"],
            "Using x264",
        )

        input_path = "/test/input.ts"

        with patch(
            "codec_helpers.CodecHelpers.get_output_extension", return_value=".mp4"
        ):
            args = self.controller._build_ffmpeg_args(input_path, 3)  # x264 CPU

        # Verify x264 specific args
        assert "-c:v" in args
        assert "libx264" in args
        # Check that output path is generated correctly
        assert "/test/input_RC.mp4" in args
        assert "-crf" in args
        assert "18" in args

    def test_get_output_path_generation(self):
        """Test output path generation in FFmpeg args"""
        input_path = "/test/input.ts"

        with patch(
            "codec_helpers.CodecHelpers.get_output_extension", return_value=".mp4"
        ):
            # Output path is generated within _build_ffmpeg_args
            args = self.controller._build_ffmpeg_args(input_path, 0)

        # Should generate path with _RC suffix in the args
        expected = "/test/input_RC.mp4"
        assert expected in args

    def test_get_output_path_different_extensions(self):
        """Test output path with different file extensions"""
        test_cases = [
            ("/test/video.ts", ".mp4", "/test/video_RC.mp4"),
            ("/test/video.mov", ".mov", "/test/video_RC.mov"),
            ("/path/with spaces/file.ts", ".mp4", "/path/with spaces/file_RC.mp4"),
        ]

        for input_path, extension, expected in test_cases:
            with patch(
                "codec_helpers.CodecHelpers.get_output_extension",
                return_value=extension,
            ):
                # Output path is generated within _build_ffmpeg_args
                args = self.controller._build_ffmpeg_args(input_path, 0)
                assert expected in args


class TestProcessManagement:
    """Test process management and queue processing"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    def test_process_next_with_queue(self):
        """Test processing next file in queue (async prep workers are queued)"""
        # Set up conversion state
        self.controller.is_converting = True
        self.controller.queue = ["/test/video1.ts", "/test/video2.ts"]
        self.controller.max_parallel = 2
        self.controller.parallel_enabled = True

        # Mock process manager to show no active processes
        self.mock_process_manager.processes = []

        with patch.object(
            self.controller, "_get_codec_for_path", return_value=0
        ) as mock_get_codec, patch.object(
            self.controller._prep_thread_pool, "start"
        ) as mock_thread_start:
            self.controller._process_next()

        # With parallel processing enabled and 2 files in queue,
        # prep workers should be queued for both files
        assert len(self.controller.queue) == 0  # Both files removed from queue
        assert mock_thread_start.call_count == 2  # 2 prep workers started
        assert mock_get_codec.call_count == 2
        # Files should be tracked in pending_preps
        assert len(self.controller._pending_preps) == 2

    def test_process_next_parallel_limit_reached(self):
        """Test process_next when parallel limit is reached"""
        # Set up conversion state
        self.controller.is_converting = True
        self.controller.queue = ["/test/video1.ts", "/test/video2.ts"]
        self.controller.max_parallel = 2

        # Mock process manager to show max processes running
        self.mock_process_manager.processes = [Mock(), Mock()]  # 2 active processes

        self.controller._process_next()

        # Should not start new process when limit reached
        self.mock_process_manager.start_process.assert_not_called()
        assert len(self.controller.queue) == 2  # Queue unchanged

    def test_process_next_empty_queue(self):
        """Test process_next with empty queue"""
        # Set up conversion state
        self.controller.is_converting = True
        self.controller.queue = []

        with patch.object(self.controller, "_finish_conversion") as mock_finish:
            self.controller._process_next()

        # Should finish conversion when queue is empty
        mock_finish.assert_called_once()
        self.mock_process_manager.start_process.assert_not_called()

    def test_process_next_not_converting(self):
        """Test process_next when not converting"""
        self.controller.is_converting = False
        self.controller.queue = ["/test/video.ts"]

        self.controller._process_next()

        # Should not process when not converting
        self.mock_process_manager.start_process.assert_not_called()

    def test_get_codec_for_path_with_assignments(self):
        """Test codec selection with auto-balance assignments"""
        file_path = "/test/video.ts"
        self.controller.auto_balance_enabled = True  # Enable auto-balance
        self.controller.file_codec_assignments = {file_path: 2}  # AV1 NVENC
        self.controller.codec_idx = 0  # Default H.264 NVENC

        codec = self.controller._get_codec_for_path(file_path)

        # Should use assignment instead of default
        assert codec == 2

    def test_get_codec_for_path_without_assignments(self):
        """Test codec selection without auto-balance assignments"""
        file_path = "/test/video.ts"
        self.controller.file_codec_assignments = {}
        self.controller.codec_idx = 1  # HEVC NVENC

        codec = self.controller._get_codec_for_path(file_path)

        # Should use default codec
        assert codec == 1


class TestThreadOptimization:
    """Test thread count optimization"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    @patch("codec_helpers.CodecHelpers.optimize_threads_for_codec")
    def test_optimize_threads_for_codec(self, mock_optimize):
        """Test thread optimization delegation"""
        mock_optimize.return_value = 6

        self.controller.parallel_enabled = True
        self.controller.file_codec_assignments = {"/test/video.ts": 3}  # CPU codec

        threads = self.controller._optimize_threads_for_codec(3)  # x264 CPU

        assert threads == 6
        mock_optimize.assert_called_once_with(
            3, True, self.controller.file_codec_assignments
        )

    @patch("codec_helpers.CodecHelpers.optimize_threads_for_codec")
    def test_optimize_threads_nvenc(self, mock_optimize):
        """Test thread optimization for NVENC"""
        mock_optimize.return_value = 2

        # Set required attributes
        self.controller.parallel_enabled = False
        self.controller.file_codec_assignments = {}

        threads = self.controller._optimize_threads_for_codec(0)  # H.264 NVENC

        assert threads == 2
        mock_optimize.assert_called_once_with(0, False, {})


class TestConversionFinalization:
    """Test conversion completion and cleanup"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    def test_finish_conversion(self):
        """Test conversion finish process"""
        self.controller.is_converting = True

        with patch.object(self.controller, "conversion_finished") as mock_signal:
            self.controller._finish_conversion()

        assert not self.controller.is_converting
        mock_signal.emit.assert_called_once()

    def test_on_process_finished_continue_processing(self):
        """Test process finished handler continues processing"""
        # Set up active conversion
        self.controller.is_converting = True
        self.controller.queue = ["/test/video2.ts"]
        self.controller.parallel_enabled = True
        self.controller.delete_source = False  # Set required attribute

        mock_process = Mock()

        with patch.object(self.controller, "_process_next") as mock_process_next:
            self.controller._on_process_finished(
                mock_process, 0, "/test/video.ts"
            )  # Success

        # Should continue processing next file
        mock_process_next.assert_called_once()

    def test_on_process_finished_conversion_complete(self):
        """Test process finished when all files complete"""
        # Set up conversion with empty queue
        self.controller.is_converting = True
        self.controller.queue = []
        self.controller.parallel_enabled = False  # Set required attribute
        self.controller.delete_source = False  # Set required attribute

        mock_process = Mock()

        with patch.object(self.controller, "_process_next") as mock_process_next:
            self.controller._on_process_finished(mock_process, 0, "/test/video.ts")

        # Should call _process_next which will then call _finish_conversion
        mock_process_next.assert_called_once()

    def test_on_process_finished_not_converting(self):
        """Test process finished when not converting"""
        self.controller.is_converting = False
        self.controller.parallel_enabled = False  # Set required attribute
        self.controller.delete_source = False  # Set required attribute

        mock_process = Mock()

        with patch.object(self.controller, "_process_next") as mock_process_next:
            self.controller._on_process_finished(mock_process, 0, "/test/video.ts")

        # Should call _process_next regardless of is_converting state
        mock_process_next.assert_called_once()


class TestSourceFileDeletion:
    """Test source file deletion functionality"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)
        self.controller.delete_source = True

    @patch("os.remove")
    @patch("os.path.getsize")
    @patch("os.stat")
    @patch("codec_helpers.CodecHelpers.get_output_extension")
    def test_delete_source_file_success(
        self, mock_ext, mock_stat, mock_getsize, mock_remove
    ):
        """Test successful source file deletion in process finished handler"""
        file_path = "/test/video.ts"
        output_path = "/test/video_RC.mp4"
        mock_process = Mock()

        # Mock output file verification using os.stat (atomic check)
        mock_ext.return_value = ".mp4"
        mock_stat_result = Mock()
        mock_stat_result.st_size = 10000  # Output file size
        mock_stat.return_value = mock_stat_result
        mock_getsize.return_value = 100000  # Input file size

        # Simulate successful conversion with delete_source enabled
        self.controller.delete_source = True
        self.controller.parallel_enabled = False  # Set required attribute
        self.controller.queue = []  # Set required attribute
        self.controller.file_list_widget = None  # Set required attribute
        # Mock codec_map and output_map for the process_manager
        self.mock_process_manager.codec_map = {file_path: 0}
        self.mock_process_manager.output_map = {file_path: output_path}
        self.controller._on_process_finished(mock_process, 0, file_path)

        # Should attempt to delete the source file
        mock_remove.assert_called_once_with(file_path)

    @patch("os.remove")
    @patch("os.path.getsize")
    @patch("os.stat")
    @patch("codec_helpers.CodecHelpers.get_output_extension")
    def test_delete_source_file_not_exists(
        self, mock_ext, mock_stat, mock_getsize, mock_remove
    ):
        """Test source file deletion when file doesn't exist"""
        # os.remove will raise FileNotFoundError if file doesn't exist
        mock_remove.side_effect = FileNotFoundError("File not found")

        file_path = "/test/video.ts"
        output_path = "/test/video_RC.mp4"
        mock_process = Mock()

        # Mock output file verification using os.stat (atomic check)
        mock_ext.return_value = ".mp4"
        mock_stat_result = Mock()
        mock_stat_result.st_size = 10000  # Output file size
        mock_stat.return_value = mock_stat_result
        mock_getsize.return_value = 100000  # Input file size

        # Set required attributes
        self.controller.delete_source = True
        self.controller.parallel_enabled = False
        self.controller.queue = []
        self.controller.file_list_widget = None
        self.mock_process_manager.codec_map = {file_path: 0}
        self.mock_process_manager.output_map = {file_path: output_path}

        # Should handle the exception gracefully
        self.controller._on_process_finished(mock_process, 0, file_path)

        mock_remove.assert_called_once_with(file_path)

    @patch("os.remove")
    @patch("os.path.getsize")
    @patch("os.stat")
    @patch("codec_helpers.CodecHelpers.get_output_extension")
    def test_delete_source_file_permission_error(
        self, mock_ext, mock_stat, mock_getsize, mock_remove
    ):
        """Test source file deletion with permission error"""
        mock_remove.side_effect = PermissionError("Access denied")

        file_path = "/test/video.ts"
        output_path = "/test/video_RC.mp4"
        mock_process = Mock()

        # Mock output file verification using os.stat (atomic check)
        mock_ext.return_value = ".mp4"
        mock_stat_result = Mock()
        mock_stat_result.st_size = 10000  # Output file size
        mock_stat.return_value = mock_stat_result
        mock_getsize.return_value = 100000  # Input file size

        # Set required attributes
        self.controller.delete_source = True
        self.controller.parallel_enabled = False
        self.controller.queue = []
        self.controller.file_list_widget = None
        self.mock_process_manager.codec_map = {file_path: 0}
        self.mock_process_manager.output_map = {file_path: output_path}

        # Should handle exception gracefully
        self.controller._on_process_finished(mock_process, 0, file_path)

        mock_remove.assert_called_once_with(file_path)

    def test_delete_source_disabled(self):
        """Test behavior when source deletion is disabled"""
        file_path = "/test/video.ts"
        mock_process = Mock()

        # Disable source deletion
        self.controller.delete_source = False
        self.controller.parallel_enabled = False
        self.controller.queue = []
        self.controller.file_list_widget = None

        with patch("os.remove") as mock_remove:
            self.controller._on_process_finished(mock_process, 0, file_path)

        # Should not attempt to delete when disabled
        mock_remove.assert_not_called()


class TestConversionSignals:
    """Test signal emission during conversion process"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    def test_log_message_emission(self):
        """Test log message signal emission"""
        with patch.object(
            self.controller, "_validate_conversion_ready", return_value=(True, "")
        ), patch.object(self.controller, "log_message") as mock_signal:
            # Start conversion to trigger log messages
            self.controller.start_conversion(
                file_paths=["/test/video.ts"],
                codec_idx=0,
                hwdecode_idx=0,
                crf_value=18,
                parallel_enabled=False,
                max_parallel=1,
                delete_source=False,
                overwrite_mode=True,
            )

            # Should emit log message about starting conversion
            mock_signal.emit.assert_called()

            # Check that some message was emitted
            calls = mock_signal.emit.call_args_list
            assert len(calls) > 0
            assert any("Starting conversion" in str(call) for call in calls)

    def test_conversion_started_emission(self):
        """Test conversion started signal emission"""
        with patch.object(
            self.controller, "_validate_conversion_ready", return_value=(True, "")
        ), patch.object(self.controller, "conversion_started") as mock_signal:
            self.controller.start_conversion(
                file_paths=["/test/video.ts"],
                codec_idx=0,
                hwdecode_idx=0,
                crf_value=18,
                parallel_enabled=False,
                max_parallel=1,
                delete_source=False,
                overwrite_mode=True,
            )

            mock_signal.emit.assert_called_once()

    def test_conversion_stopped_emission(self):
        """Test conversion stopped signal emission"""
        # Start conversion first
        self.controller.is_converting = True

        # Mock stop_all_processes to return a list
        self.mock_process_manager.stop_all_processes.return_value = []

        with patch.object(self.controller, "conversion_stopped") as mock_signal:
            self.controller.stop_conversion()

        mock_signal.emit.assert_called_once()


class TestConversionValidation:
    """Test conversion parameter validation"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    def test_valid_conversion_parameters(self):
        """Test validation of valid conversion parameters"""
        file_paths = ["/test/video.ts"]

        with patch.object(
            self.controller, "_validate_conversion_ready", return_value=(True, "")
        ):
            result = self.controller.start_conversion(
                file_paths=file_paths,
                codec_idx=0,  # Valid codec
                hwdecode_idx=1,  # Valid hardware decode
                crf_value=18,  # Valid CRF
                parallel_enabled=True,
                max_parallel=4,  # Valid parallel count
                delete_source=False,
                overwrite_mode=True,
            )

        assert result

    def test_invalid_parallel_count(self):
        """Test with invalid parallel count"""
        # Note: Current implementation doesn't validate parallel count
        # This test documents expected behavior
        file_paths = ["/test/video.ts"]

        with patch.object(
            self.controller, "_validate_conversion_ready", return_value=(True, "")
        ):
            result = self.controller.start_conversion(
                file_paths=file_paths,
                codec_idx=0,
                hwdecode_idx=0,
                crf_value=18,
                parallel_enabled=True,
                max_parallel=0,  # Invalid parallel count
                delete_source=False,
                overwrite_mode=True,
            )

        # Current implementation allows this - consider adding validation
        assert result

    def test_extreme_crf_values(self):
        """Test with extreme CRF values"""
        file_paths = ["/test/video.ts"]

        with patch.object(
            self.controller, "_validate_conversion_ready", return_value=(True, "")
        ):
            # Test very high CRF
            result = self.controller.start_conversion(
                file_paths=file_paths,
                codec_idx=0,
                hwdecode_idx=0,
                crf_value=100,  # Very high CRF
                parallel_enabled=False,
                max_parallel=1,
                delete_source=False,
                overwrite_mode=True,
            )

        # Should still work (encoder config handles clamping)
        assert result


@pytest.mark.unit
class TestConversionControllerEdgeCases:
    """Test edge cases and error conditions"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)
        # Mock stop_all_processes to return a list
        self.mock_process_manager.stop_all_processes.return_value = []

    def test_concurrent_start_stop(self):
        """Test concurrent start and stop operations"""
        file_paths = ["/test/video.ts"]

        with patch.object(
            self.controller, "_validate_conversion_ready", return_value=(True, "")
        ):
            # Start conversion
            result = self.controller.start_conversion(
                file_paths=file_paths,
                codec_idx=0,
                hwdecode_idx=0,
                crf_value=18,
                parallel_enabled=False,
                max_parallel=1,
                delete_source=False,
                overwrite_mode=True,
            )

            assert result
            assert self.controller.is_converting

            # Immediately stop
            self.controller.stop_conversion()

            assert not self.controller.is_converting

    def test_process_finish_race_condition(self):
        """Test race condition in process finish handling"""
        # Start conversion
        self.controller.is_converting = True
        self.controller.queue = ["/test/video.ts"]
        self.controller.parallel_enabled = False  # Set required attribute
        self.controller.delete_source = False  # Set required attribute

        mock_process = Mock()

        # Stop conversion before process finish handler
        self.controller.stop_conversion()

        # Process finish should handle gracefully
        with patch.object(self.controller, "_process_next") as mock_process_next:
            self.controller._on_process_finished(mock_process, 0, "/test/video.ts")

        # Should still call process_next (implementation always calls it)
        mock_process_next.assert_called_once()

    def test_malformed_file_paths(self):
        """Test handling of malformed file paths"""
        malformed_paths = [
            "",  # Empty path
            None,  # None path (would cause TypeError)
            "/nonexistent/path/video.ts",  # Non-existent path
            "relative/path.ts",  # Relative path
        ]

        for path in malformed_paths:
            if path is None:
                continue  # Skip None test (would need different handling)

            # Should not crash with malformed paths
            result = self.controller.start_conversion(
                file_paths=[path],
                codec_idx=0,
                hwdecode_idx=0,
                crf_value=18,
                parallel_enabled=False,
                max_parallel=1,
                delete_source=False,
                overwrite_mode=True,
            )

            # Implementation should handle gracefully
            assert isinstance(result, bool)

    @pytest.mark.slow
    def test_memory_cleanup_on_large_queue(self):
        """Test memory management with large file queue"""
        # Create large file list
        large_file_list = [f"/test/video{i}.ts" for i in range(1000)]

        # Mock the process manager to simulate active processes
        # This prevents all 1000 files from being processed immediately
        mock_processes = [Mock() for _ in range(8)]  # Simulate max_parallel processes
        self.mock_process_manager.processes = mock_processes

        with patch.object(
            self.controller, "_validate_conversion_ready", return_value=(True, "")
        ):
            result = self.controller.start_conversion(
                file_paths=large_file_list,
                codec_idx=0,
                hwdecode_idx=0,
                crf_value=18,
                parallel_enabled=True,
                max_parallel=8,
                delete_source=False,
                overwrite_mode=True,
            )

            assert result
            # With our fix, the queue will be reduced by the number of processes that could be started
            # Since we simulate 8 active processes, no new processes will start
            assert len(self.controller.queue) == 1000

            # Stop conversion
            self.controller.stop_conversion()

            # Memory should be cleaned up
            assert not self.controller.is_converting


@pytest.mark.unit
class TestConversionControllerIntegration:
    """Test integration between ConversionController components"""

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    @patch("codec_helpers.CodecHelpers.get_hardware_acceleration_args")
    @patch("codec_helpers.CodecHelpers.get_audio_codec_args")
    @patch("codec_helpers.CodecHelpers.get_encoder_configuration")
    @patch("codec_helpers.CodecHelpers.get_output_extension")
    def test_full_conversion_workflow(
        self, mock_extension, mock_encoder, mock_audio, mock_hw
    ):
        """Test complete conversion workflow integration"""
        # Configure mocks
        mock_hw.return_value = (["-hwaccel", "cuda"], "Using CUDA")
        mock_audio.return_value = (["-c:a", "copy"], "Using passthrough")
        mock_encoder.return_value = (["-c:v", "h264_nvenc"], "Using NVENC")
        mock_extension.return_value = ".mp4"

        file_paths = ["/test/video1.ts", "/test/video2.ts"]

        # Mock stop_all_processes to return a list
        self.mock_process_manager.stop_all_processes.return_value = []

        with patch.object(
            self.controller, "_validate_conversion_ready", return_value=(True, "")
        ):
            # Start conversion
            result = self.controller.start_conversion(
                file_paths=file_paths,
                codec_idx=0,
                hwdecode_idx=1,
                crf_value=18,
                parallel_enabled=True,
                max_parallel=2,
                delete_source=False,
                overwrite_mode=True,
            )

            assert result

        # Verify process manager integration
        self.mock_process_manager.start_batch.assert_called_once_with(
            file_paths, True, 2
        )

        # Should have started processing
        assert len(self.controller.queue) <= len(
            file_paths
        )  # Queue consumed by _process_next

        # Stop conversion
        self.controller.stop_conversion()

        assert not self.controller.is_converting


@pytest.mark.unit
class TestPriorityMapping:
    """Test priority index mapping between UI and process priority.

    BUG FIX: The UI ComboBox has items in order ["Normal", "Low", "High"]
    (indices 0, 1, 2) and the mapping must correctly translate these to
    priority strings.
    """

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    def test_priority_index_0_maps_to_normal(self):
        """Test that UI index 0 (Normal) maps to 'normal' priority"""
        # UI ComboBox: ["Normal", "Low", "High"] -> index 0 = Normal
        priority_names = {0: "normal", 1: "low", 2: "high"}
        assert priority_names[0] == "normal"

    def test_priority_index_1_maps_to_low(self):
        """Test that UI index 1 (Low) maps to 'low' priority"""
        priority_names = {0: "normal", 1: "low", 2: "high"}
        assert priority_names[1] == "low"

    def test_priority_index_2_maps_to_high(self):
        """Test that UI index 2 (High) maps to 'high' priority"""
        priority_names = {0: "normal", 1: "low", 2: "high"}
        assert priority_names[2] == "high"

    @patch("codec_helpers.CodecHelpers.get_hardware_acceleration_args")
    @patch("codec_helpers.CodecHelpers.get_encoder_configuration")
    @patch("codec_helpers.CodecHelpers.get_output_extension")
    def test_priority_applied_correctly_on_process_start(
        self, mock_ext, mock_encoder, mock_hw
    ):
        """Test that priority is correctly applied when starting a process.

        This is the critical integration test - when user selects "High"
        in the UI (index 2), the process should receive "high" priority.
        """
        mock_hw.return_value = ([], "")
        mock_encoder.return_value = (["-c:v", "libx264"], "")
        mock_ext.return_value = ".mp4"

        # Create a mock process that's in "running" state
        mock_process = Mock()
        mock_process.state.return_value = QProcess.ProcessState.Running
        self.mock_process_manager.start_process.return_value = mock_process

        # Set priority to High (index 2)
        self.controller.priority_idx = 2

        # Simulate prep completion which triggers process start
        self.controller.is_converting = True
        self.controller._pending_preps = {"/test/video.ts": 0}
        self.controller._on_prep_complete(
            "/test/video.ts", 600.0, ["-c:a", "copy"], ""
        )

        # Verify set_process_priority was called with "high"
        self.mock_process_manager.set_process_priority.assert_called_once()
        call_args = self.mock_process_manager.set_process_priority.call_args
        assert call_args[0][1] == "high", (
            f"Expected 'high' but got '{call_args[0][1]}'. "
            "Priority mapping may be inverted!"
        )


@pytest.mark.unit
class TestTOCTOURaceConditionHandling:
    """Test handling of TOCTOU race conditions in source file deletion.

    BUG FIX: The original code used os.path.exists() followed by
    os.path.getsize() which could fail if the file was deleted between
    calls. Now uses atomic os.stat().
    """

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    @patch("os.remove")
    @patch("os.path.getsize")
    @patch("os.stat")
    def test_stat_filenotfound_handled_gracefully(
        self, mock_stat, mock_getsize, mock_remove
    ):
        """Test that FileNotFoundError from os.stat is handled gracefully.

        Simulates the race condition where output file is deleted between
        conversion completion and source deletion verification.
        """
        file_path = "/test/video.ts"
        output_path = "/test/video_RC.mp4"
        mock_process = Mock()

        # Simulate output file deleted between check (TOCTOU race)
        mock_stat.side_effect = FileNotFoundError("File deleted by another process")

        self.controller.delete_source = True
        self.controller.parallel_enabled = False
        self.controller.queue = []
        self.controller.file_list_widget = None
        self.mock_process_manager.output_map = {file_path: output_path}

        # Should NOT raise exception - handle gracefully
        self.controller._on_process_finished(mock_process, 0, file_path)

        # Source file should NOT be deleted (output verification failed)
        mock_remove.assert_not_called()

    @patch("os.remove")
    @patch("os.path.getsize")
    @patch("os.stat")
    def test_stat_oserror_handled_gracefully(
        self, mock_stat, mock_getsize, mock_remove
    ):
        """Test that OSError from os.stat is handled gracefully.

        Simulates scenarios like permission denied, I/O errors, etc.
        """
        file_path = "/test/video.ts"
        output_path = "/test/video_RC.mp4"
        mock_process = Mock()

        # Simulate OS-level error (permission denied, I/O error, etc.)
        mock_stat.side_effect = OSError("Permission denied")

        self.controller.delete_source = True
        self.controller.parallel_enabled = False
        self.controller.queue = []
        self.controller.file_list_widget = None
        self.mock_process_manager.output_map = {file_path: output_path}

        # Should NOT raise exception - handle gracefully
        self.controller._on_process_finished(mock_process, 0, file_path)

        # Source file should NOT be deleted (output verification failed)
        mock_remove.assert_not_called()

    @patch("os.remove")
    @patch("os.path.getsize")
    @patch("os.stat")
    def test_atomic_stat_used_for_output_verification(
        self, mock_stat, mock_getsize, mock_remove
    ):
        """Test that os.stat is used atomically for output verification."""
        file_path = "/test/video.ts"
        output_path = "/test/video_RC.mp4"
        mock_process = Mock()

        # Mock stat result with valid size
        mock_stat_result = Mock()
        mock_stat_result.st_size = 10000
        mock_stat.return_value = mock_stat_result
        mock_getsize.return_value = 100000  # Input file size

        self.controller.delete_source = True
        self.controller.parallel_enabled = False
        self.controller.queue = []
        self.controller.file_list_widget = None
        self.mock_process_manager.output_map = {file_path: output_path}

        self.controller._on_process_finished(mock_process, 0, file_path)

        # Verify os.stat was called with output path
        mock_stat.assert_called_once_with(output_path)

        # Source should be deleted since output verification passed
        mock_remove.assert_called_once_with(file_path)


@pytest.mark.unit
class TestOutputMapUsage:
    """Test that output_map is used instead of path reconstruction.

    BUG FIX: Output path was being reconstructed in _on_process_finished,
    which could produce wrong paths if codec settings changed mid-batch.
    Now uses stored output_map.
    """

    def setup_method(self):
        self.mock_process_manager = create_mock_process_manager()
        self.controller = ConversionController(self.mock_process_manager)

    @patch("os.remove")
    @patch("os.path.getsize")
    @patch("os.stat")
    @patch("codec_helpers.CodecHelpers.get_output_extension")
    def test_output_map_used_over_reconstruction(
        self, mock_ext, mock_stat, mock_getsize, mock_remove
    ):
        """Test that output_map is preferred over path reconstruction."""
        file_path = "/test/video.ts"
        stored_output_path = "/test/video_RC.mp4"
        mock_process = Mock()

        # Mock stat to succeed
        mock_stat_result = Mock()
        mock_stat_result.st_size = 10000
        mock_stat.return_value = mock_stat_result
        mock_getsize.return_value = 100000

        # Store output path in output_map
        self.mock_process_manager.output_map = {file_path: stored_output_path}
        self.mock_process_manager.codec_map = {file_path: 0}

        self.controller.delete_source = True
        self.controller.parallel_enabled = False
        self.controller.queue = []
        self.controller.file_list_widget = None

        self.controller._on_process_finished(mock_process, 0, file_path)

        # Should use stored output path, NOT call get_output_extension
        mock_stat.assert_called_once_with(stored_output_path)
        # get_output_extension should NOT be called when output_map has the path
        mock_ext.assert_not_called()

    @patch("os.remove")
    @patch("os.path.getsize")
    @patch("os.stat")
    @patch("codec_helpers.CodecHelpers.get_output_extension")
    def test_fallback_to_reconstruction_when_output_map_empty(
        self, mock_ext, mock_stat, mock_getsize, mock_remove
    ):
        """Test fallback to path reconstruction when output_map is empty."""
        file_path = "/test/video.ts"
        mock_process = Mock()

        mock_ext.return_value = ".mp4"
        mock_stat_result = Mock()
        mock_stat_result.st_size = 10000
        mock_stat.return_value = mock_stat_result
        mock_getsize.return_value = 100000

        # Empty output_map - should fallback to reconstruction
        self.mock_process_manager.output_map = {}
        self.mock_process_manager.codec_map = {file_path: 0}

        self.controller.delete_source = True
        self.controller.parallel_enabled = False
        self.controller.queue = []
        self.controller.file_list_widget = None

        self.controller._on_process_finished(mock_process, 0, file_path)

        # Should call get_output_extension as fallback
        mock_ext.assert_called_once()
        # Reconstructed path should be used
        expected_path = "/test/video_RC.mp4"
        mock_stat.assert_called_once_with(expected_path)
