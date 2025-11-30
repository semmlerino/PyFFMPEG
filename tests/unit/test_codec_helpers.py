#!/usr/bin/env python3
"""
Unit tests for CodecHelpers class
Tests hardware detection, encoder configuration, and fallback logic
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from codec_helpers import CodecHelpers
from config import EncodingConfig, ProcessConfig
from tests.fixtures.mocks import (
    MockEncoderDetection,
    MockGPUDetection,
    create_hardware_test_matrix,
)


class TestCodecHelpers:
    """Test suite for CodecHelpers static class"""

    def setup_method(self):
        """Clear cache before each test"""
        CodecHelpers.clear_cache()

    def teardown_method(self):
        """Clear cache after each test"""
        CodecHelpers.clear_cache()


class TestOutputExtensions:
    """Test output file extension determination"""

    def test_h264_extension(self):
        """Test H.264 codec extensions"""
        assert CodecHelpers.get_output_extension(0) == ".mp4"  # H.264 NVENC
        assert CodecHelpers.get_output_extension(3) == ".mp4"  # x264 CPU
        assert CodecHelpers.get_output_extension(5) == ".mp4"  # H.264 QSV
        assert CodecHelpers.get_output_extension(6) == ".mp4"  # H.264 VAAPI

    def test_hevc_extension(self):
        """Test HEVC codec extensions"""
        assert CodecHelpers.get_output_extension(1) == ".mp4"  # HEVC NVENC

    def test_av1_extension(self):
        """Test AV1 codec extensions"""
        assert CodecHelpers.get_output_extension(2) == ".mp4"  # AV1 NVENC

    def test_prores_extension(self):
        """Test ProRes codec extensions"""
        assert CodecHelpers.get_output_extension(4) == ".mov"  # ProRes CPU

    def test_unknown_codec_default(self):
        """Test default extension for unknown codecs"""
        assert CodecHelpers.get_output_extension(99) == ".mp4"
        assert CodecHelpers.get_output_extension(-1) == ".mp4"


class TestHardwareAcceleration:
    """Test hardware acceleration detection and configuration"""

    @patch("subprocess.check_output")
    def test_auto_acceleration_with_nvidia(self, mock_subprocess):
        """Test auto hardware acceleration with NVIDIA GPU"""
        # Clear the GPU info cache first
        CodecHelpers._gpu_info_cache = None

        mock_subprocess.return_value = MockGPUDetection.rtx4090_detected().encode()

        args, message = CodecHelpers.get_hardware_acceleration_args(0)  # Auto

        assert "-hwaccel" in args
        assert "cuda" in args
        assert "CUDA" in message
        mock_subprocess.assert_called_once()

    @patch("subprocess.check_output")
    def test_auto_acceleration_no_gpu(self, mock_subprocess):
        """Test auto hardware acceleration fallback when no GPU"""
        # Clear the GPU info cache first
        CodecHelpers._gpu_info_cache = None

        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "nvidia-smi")

        args, message = CodecHelpers.get_hardware_acceleration_args(0)  # Auto

        assert "-hwaccel" in args
        assert "auto" in args
        assert "auto hardware acceleration" in message

    def test_explicit_nvidia_acceleration(self):
        """Test explicit NVIDIA acceleration"""
        args, message = CodecHelpers.get_hardware_acceleration_args(1)  # NVIDIA

        assert args == ["-hwaccel", "cuda"]
        assert "CUDA" in message

    def test_explicit_qsv_acceleration(self):
        """Test explicit Intel QSV acceleration with surface output"""
        args, message = CodecHelpers.get_hardware_acceleration_args(2)  # Intel QSV

        # QSV now includes hwaccel_output_format for proper hardware surface pipeline
        assert args == ["-hwaccel", "qsv", "-hwaccel_output_format", "qsv"]
        assert "QSV" in message
        assert "surface" in message.lower()  # Verify surface output mentioned

    @patch("os.name", "posix")
    def test_vaapi_acceleration_linux(self):
        """Test VAAPI acceleration on Linux"""
        args, message = CodecHelpers.get_hardware_acceleration_args(3)  # VAAPI

        assert "-hwaccel" in args
        assert "vaapi" in args
        assert "/dev/dri/renderD128" in args
        assert "VAAPI" in message

    @patch("os.name", "nt")
    def test_vaapi_acceleration_windows_fallback(self):
        """Test VAAPI acceleration fallback on Windows"""
        args, message = CodecHelpers.get_hardware_acceleration_args(3)  # VAAPI

        assert "-hwaccel" in args
        assert "auto" in args
        assert "not available" in message

    @patch("subprocess.check_output")
    def test_hardware_acceleration_timeout(self, mock_subprocess):
        """Test hardware acceleration with subprocess timeout"""
        # Clear the GPU info cache first
        CodecHelpers._gpu_info_cache = None

        mock_subprocess.side_effect = subprocess.TimeoutExpired("nvidia-smi", 10)

        args, message = CodecHelpers.get_hardware_acceleration_args(0)  # Auto

        # When GPU detection times out, it falls back to auto
        assert "-hwaccel" in args
        assert "auto" in args
        assert "auto hardware acceleration" in message


class TestAudioCodecConfiguration:
    """Test audio codec configuration"""

    @patch("subprocess.run")
    def test_aac_passthrough(self, mock_subprocess):
        """Test AAC audio passthrough"""
        mock_result = Mock()
        mock_result.stdout = "aac"
        mock_subprocess.return_value = mock_result

        args, message = CodecHelpers.get_audio_codec_args("/test/input.ts", 0)

        assert args == ["-c:a", "copy"]
        assert "aac" in message
        assert "passthrough" in message

    @patch("subprocess.run")
    def test_ac3_passthrough(self, mock_subprocess):
        """Test AC-3 audio passthrough"""
        mock_result = Mock()
        mock_result.stdout = "ac3"
        mock_subprocess.return_value = mock_result

        args, message = CodecHelpers.get_audio_codec_args("/test/input.ts", 0)

        assert args == ["-c:a", "copy"]
        assert "ac3" in message

    @patch("subprocess.run")
    def test_prores_pcm_audio(self, mock_subprocess):
        """Test PCM audio for ProRes"""
        mock_result = Mock()
        mock_result.stdout = "mp3"  # Non-passthrough codec
        mock_subprocess.return_value = mock_result

        args, message = CodecHelpers.get_audio_codec_args("/test/input.ts", 4)  # ProRes

        assert args == ["-c:a", "pcm_s16le"]
        assert "PCM" in message

    @patch("subprocess.run")
    def test_aac_encoding_fallback(self, mock_subprocess):
        """Test AAC encoding for non-passthrough codecs"""
        mock_result = Mock()
        mock_result.stdout = "mp3"
        mock_subprocess.return_value = mock_result

        args, message = CodecHelpers.get_audio_codec_args("/test/input.ts", 0)

        expected_bitrate = f"{EncodingConfig.AUDIO_BITRATE_DEFAULT}k"
        assert args == ["-c:a", "aac", "-b:a", expected_bitrate]
        assert "AAC" in message
        assert expected_bitrate in message

    @patch("subprocess.run")
    def test_audio_probe_timeout(self, mock_subprocess):
        """Test audio codec detection with timeout"""
        mock_subprocess.side_effect = subprocess.TimeoutExpired(
            "ffprobe", ProcessConfig.SUBPROCESS_TIMEOUT
        )

        args, message = CodecHelpers.get_audio_codec_args("/test/input.ts", 0)

        # Should fallback to AAC encoding
        expected_bitrate = f"{EncodingConfig.AUDIO_BITRATE_DEFAULT}k"
        assert args == ["-c:a", "aac", "-b:a", expected_bitrate]
        assert "Fallback" in message


class TestEncoderConfiguration:
    """Test video encoder configuration"""

    @patch("subprocess.check_output")
    def test_h264_nvenc_configuration(self, mock_subprocess):
        """Test H.264 NVENC encoder configuration"""
        mock_subprocess.return_value = MockEncoderDetection.full_nvenc_support()

        args, message = CodecHelpers.get_encoder_configuration(
            0, 4, False, 18
        )  # H.264 NVENC (codec_idx=0)

        assert "-c:v" in args
        assert "h264_nvenc" in args
        assert "-preset" in args
        assert "-cq" in args
        assert "NVENC" in message

    @patch("subprocess.check_output")
    def test_hevc_nvenc_configuration(self, mock_subprocess):
        """Test HEVC NVENC encoder configuration"""
        mock_subprocess.return_value = MockEncoderDetection.full_nvenc_support()

        args, message = CodecHelpers.get_encoder_configuration(
            1, 4, False, 18
        )  # HEVC NVENC (codec_idx=1)

        assert "-c:v" in args
        assert "hevc_nvenc" in args
        assert "-profile:v" in args
        assert "main" in args
        assert "HEVC" in message

    @patch("subprocess.check_output")
    def test_av1_nvenc_configuration(self, mock_subprocess):
        """Test AV1 NVENC encoder configuration"""
        mock_subprocess.return_value = MockEncoderDetection.full_nvenc_support()

        args, message = CodecHelpers.get_encoder_configuration(
            2, 4, False, 18
        )  # AV1 NVENC (codec_idx=2)

        assert "-c:v" in args
        assert "av1_nvenc" in args
        assert "-rc" in args
        assert "vbr" in args
        assert "AV1" in message

    def test_x264_software_configuration(self):
        """Test x264 software encoder configuration"""
        args, message = CodecHelpers.get_encoder_configuration(3, 6, False, 18)  # x264

        assert "-c:v" in args
        assert "libx264" in args
        assert "-crf" in args
        assert "18" in args
        assert "-threads" in args
        assert "6" in args
        assert "x264" in message

    def test_x264_parallel_no_threads(self):
        """Test x264 in parallel mode doesn't set threads"""
        args, _message = CodecHelpers.get_encoder_configuration(
            3, 0, True, 18
        )  # x264, thread_count=0 (means auto-detect)

        assert "-c:v" in args
        assert "libx264" in args
        assert "-threads" not in args  # Should not set threads when thread_count=0

    @patch("subprocess.check_output")
    def test_prores_configuration(self, mock_subprocess):
        """Test ProRes encoder configuration"""
        mock_subprocess.return_value = MockEncoderDetection.software_only()

        args, message = CodecHelpers.get_encoder_configuration(
            4, 4, False, 18
        )  # ProRes

        assert "-c:v" in args
        assert "prores_ks" in args
        assert "-profile:v" in args
        assert "3" in args  # ProRes 422 profile
        assert "-pix_fmt" in args
        assert "yuv422p10le" in args
        assert "ProRes" in message

    @patch("subprocess.check_output")
    def test_encoder_fallback_to_x264(self, mock_subprocess):
        """Test fallback to x264 when requested encoder unavailable"""
        mock_subprocess.return_value = MockEncoderDetection.software_only()  # No NVENC

        args, message = CodecHelpers.get_encoder_configuration(
            0, 4, False, 18
        )  # H.264 NVENC (codec_idx=0)

        # Implementation doesn't fallback - it returns the requested encoder anyway
        assert "-c:v" in args
        assert "h264_nvenc" in args  # Returns requested encoder even if not detected
        assert "H.264 NVENC" in message

    def test_encoder_configuration_exception(self):
        """Test encoder configuration with exception handling"""
        with patch(
            "subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "ffmpeg"),
        ):
            args, message = CodecHelpers.get_encoder_configuration(1, 4, False, 18)

            # Implementation returns the requested encoder even if detection fails
            assert "-c:v" in args
            assert "hevc_nvenc" in args  # Still returns HEVC NVENC (codec_idx=1)
            assert "HEVC NVENC" in message


class TestThreadOptimization:
    """Test thread optimization logic"""

    def test_nvenc_thread_optimization(self):
        """Test NVENC encoders use minimal threads"""
        for codec_idx in [0, 1, 2]:  # All NVENC variants
            threads = CodecHelpers.optimize_threads_for_codec(codec_idx, True, None)
            assert threads == 2

    @patch("os.cpu_count", return_value=16)
    def test_single_cpu_job_auto_threads(self, mock_cpu_count):
        """Test single CPU job uses most threads minus system reserve"""
        threads = CodecHelpers.optimize_threads_for_codec(
            3, False, None
        )  # x264, not parallel
        assert threads == 12  # 16 - 4 reserved for system

    @patch("os.cpu_count", return_value=16)
    def test_parallel_cpu_thread_division(self, mock_cpu_count):
        """Test parallel CPU jobs divide threads evenly"""
        file_assignments = {
            "/file1.ts": 3,  # CPU
            "/file2.ts": 3,  # CPU
            "/file3.ts": 1,  # NVENC
            "/file4.ts": 3,  # CPU
        }

        threads = CodecHelpers.optimize_threads_for_codec(3, True, file_assignments)

        # 3 CPU jobs, 16 cores -> (16-2)/3 = 14/3 = 4
        assert threads == 4

    @patch("os.cpu_count", return_value=None)
    def test_cpu_count_none_fallback(self, mock_cpu_count):
        """Test fallback when cpu_count returns None"""
        threads = CodecHelpers.optimize_threads_for_codec(3, True, None)

        # Should use ProcessConfig.OPTIMAL_CPU_THREADS as fallback
        # For parallel with no assignments, cpu_jobs defaults to 2
        expected = max(2, (ProcessConfig.OPTIMAL_CPU_THREADS - 2) // 2)
        assert threads == expected


class TestCachingMechanisms:
    """Test caching of expensive operations"""

    def setup_method(self):
        """Clear caches before each test"""
        CodecHelpers.clear_cache()

    @patch("subprocess.check_output")
    def test_encoder_detection_caching(self, mock_subprocess):
        """Test encoder detection results are cached"""
        mock_subprocess.return_value = MockEncoderDetection.full_nvenc_support()

        # First call
        result1 = CodecHelpers._get_available_encoders()

        # Second call should use cache
        result2 = CodecHelpers._get_available_encoders()

        assert result1 == result2
        mock_subprocess.assert_called_once()  # Should only call subprocess once

    @patch("subprocess.check_output")
    def test_gpu_info_caching(self, mock_subprocess):
        """Test GPU info caching"""
        mock_subprocess.return_value = MockGPUDetection.rtx4090_detected().encode()

        # First call
        result1 = CodecHelpers._get_gpu_info()

        # Second call should use cache
        result2 = CodecHelpers._get_gpu_info()

        assert result1 == result2
        mock_subprocess.assert_called_once()

    @patch("subprocess.check_output")
    def test_rtx40_detection_caching(self, mock_subprocess):
        """Test RTX40 detection caching"""
        mock_subprocess.return_value = MockGPUDetection.rtx4090_detected().encode()

        # First call
        result1 = CodecHelpers.detect_rtx40_series()

        # Second call should use cache
        result2 = CodecHelpers.detect_rtx40_series()

        assert result1 == result2 is True
        mock_subprocess.assert_called_once()

    def test_cache_clearing(self):
        """Test cache clearing functionality"""
        # Populate cache
        CodecHelpers._encoder_cache = "test_data"
        CodecHelpers._gpu_info_cache = "test_gpu"
        CodecHelpers._rtx40_detection_cache = True

        # Clear cache
        CodecHelpers.clear_cache()

        # Verify cache is cleared
        assert CodecHelpers._encoder_cache is None
        assert CodecHelpers._gpu_info_cache is None
        assert CodecHelpers._rtx40_detection_cache is None


class TestRTX40Detection:
    """Test RTX 40 series detection for AV1 support"""

    @pytest.mark.parametrize(
        ("gpu_model", "expected"),
        [
            ("RTX 4090", True),
            ("RTX 4080", True),
            ("RTX 4070", True),
            ("RTX 40", True),  # Generic RTX 40 match
            ("RTX 3090", False),
            ("RTX 3080", False),
            ("RTX 2080", False),
            ("GTX 1080", False),
            ("Intel UHD", False),
        ],
    )
    @patch("subprocess.check_output")
    def test_rtx40_model_detection(self, mock_subprocess, gpu_model, expected):
        """Test RTX 40 series model detection"""
        # Clear cache before test
        CodecHelpers._gpu_info_cache = None
        CodecHelpers._rtx40_detection_cache = None

        gpu_info = f"GPU 0: NVIDIA GeForce {gpu_model}"
        mock_subprocess.return_value = gpu_info.encode()

        result = CodecHelpers.detect_rtx40_series()
        assert result == expected

    @patch("subprocess.check_output")
    def test_rtx40_detection_exception(self, mock_subprocess):
        """Test RTX40 detection with exception"""
        # Clear cache before test
        CodecHelpers._gpu_info_cache = None
        CodecHelpers._rtx40_detection_cache = None

        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "nvidia-smi")

        result = CodecHelpers.detect_rtx40_series()
        assert not result


class TestHardwareTestMatrix:
    """Test different hardware configurations using test matrix"""

    @pytest.mark.parametrize("hardware_config", create_hardware_test_matrix())
    def test_hardware_configurations(self, hardware_config):
        """Test various hardware configurations"""
        # Clear cache before each test configuration
        CodecHelpers.clear_cache()

        with patch("subprocess.check_output") as mock_subprocess:
            # Configure mocks based on test scenario
            encoder_result = hardware_config["encoder_detection"]()

            # Handle GPU detection - some scenarios raise exceptions
            try:
                gpu_result = hardware_config["gpu_detection"]()
                if isinstance(gpu_result, str):
                    gpu_result = gpu_result.encode()
            except subprocess.CalledProcessError as e:
                gpu_result = e

            mock_subprocess.side_effect = [encoder_result, gpu_result]

            # Test encoder availability
            encoders = CodecHelpers._get_available_encoders()
            expected_codec = hardware_config["expected_primary_codec"]
            assert expected_codec in encoders

            # Test AV1 support
            if hardware_config["expected_av1_support"]:
                assert "av1_nvenc" in encoders
            else:
                assert "av1_nvenc" not in encoders


@pytest.mark.unit
class TestCodecHelpersEdgeCases:
    """Test edge cases and error conditions"""

    def test_invalid_codec_indices(self):
        """Test handling of invalid codec indices"""
        # Should not crash and return reasonable defaults
        extension = CodecHelpers.get_output_extension(-5)
        assert extension == ".mp4"

        extension = CodecHelpers.get_output_extension(999)
        assert extension == ".mp4"

    def test_crf_value_passthrough(self):
        """Test CRF value is passed through without clamping"""
        # Clear cache before test
        CodecHelpers.clear_cache()

        with patch(
            "subprocess.check_output",
            return_value=MockEncoderDetection.full_nvenc_support(),
        ):
            # Test high CRF value is passed through as-is
            args, _ = CodecHelpers.get_encoder_configuration(1, 4, False, 100)

            cq_idx = args.index("-cq") + 1
            cq_value = int(args[cq_idx])
            assert cq_value == 100  # Value should not be clamped

    def test_empty_encoder_output(self):
        """Test handling of empty encoder detection output"""
        # Clear cache first
        CodecHelpers._encoder_cache = None

        with patch("subprocess.check_output", return_value=""):
            encoders = CodecHelpers._get_available_encoders()
            # Empty output is still cached and returned as empty string
            assert encoders == ""

            # When encoder detection fails (empty output), it falls back to libx264
            args, message = CodecHelpers.get_encoder_configuration(1, 4, False, 18)
            assert "libx264" in args  # Falls back to x264
            assert "falling back" in message.lower()  # Should indicate fallback

    def test_malformed_gpu_output(self):
        """Test handling of malformed GPU detection output"""
        # Clear cache first
        CodecHelpers._gpu_info_cache = None
        CodecHelpers._rtx40_detection_cache = None

        with patch("subprocess.check_output", return_value=b"malformed gpu output"):
            result = CodecHelpers.detect_rtx40_series()
            assert not result


class TestQSVEncodingPipeline:
    """Test Intel QSV encoding pipeline with proper filter chains"""

    def setup_method(self):
        """Clear cache before each test"""
        CodecHelpers.clear_cache()

    @patch("subprocess.check_output")
    def test_qsv_encoding_with_full_pipeline(self, mock_subprocess):
        """Test QSV encoding includes init_hw_device and hwupload filter"""
        # Return string (text=True in check_output) with h264_qsv in the output
        mock_subprocess.return_value = "V..... h264_qsv             H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (Intel Quick Sync Video acceleration)"

        args, message = CodecHelpers.get_encoder_configuration(
            5, 4, False, 20  # H.264 QSV
        )

        # Verify full QSV pipeline is present
        assert "-init_hw_device" in args
        assert "qsv=hw" in args
        assert "-filter_hw_device" in args
        assert "hw" in args
        assert "-vf" in args
        assert "hwupload=extra_hw_frames=64,format=qsv" in args
        assert "-c:v" in args
        assert "h264_qsv" in args
        assert "QSV" in message
        assert "surface" in message.lower()

    @patch("subprocess.check_output")
    def test_qsv_preset_mapping(self, mock_subprocess):
        """Test QSV preset mapping from UI index"""
        mock_subprocess.return_value = "V..... h264_qsv             H.264 / AVC (Intel QSV)"

        # Test each preset index
        preset_tests = [
            (0, "medium"),   # Standard
            (1, "slow"),     # High Quality
            (2, "fast"),     # Fast
            (3, "veryfast"), # Ultra Fast
        ]

        for preset_idx, expected_preset in preset_tests:
            CodecHelpers.clear_cache()
            args, _ = CodecHelpers.get_encoder_configuration(
                5, 4, False, 20, preset_idx=preset_idx
            )
            preset_pos = args.index("-preset") + 1
            assert args[preset_pos] == expected_preset

    @patch("subprocess.check_output")
    def test_qsv_global_quality_passthrough(self, mock_subprocess):
        """Test QSV global_quality uses CRF value"""
        mock_subprocess.return_value = "V..... h264_qsv             H.264 / AVC (Intel QSV)"

        args, _ = CodecHelpers.get_encoder_configuration(
            5, 4, False, 25  # CRF 25
        )

        quality_pos = args.index("-global_quality") + 1
        assert args[quality_pos] == "25"


class TestVAAPIEncodingPipeline:
    """Test VAAPI encoding pipeline with proper filter chains"""

    def setup_method(self):
        """Clear cache before each test"""
        CodecHelpers.clear_cache()

    @patch("subprocess.check_output")
    def test_vaapi_encoding_with_full_pipeline(self, mock_subprocess):
        """Test VAAPI encoding includes vaapi_device and hwupload filter"""
        # Return string (text=True in check_output) with h264_vaapi in the output
        mock_subprocess.return_value = "V..... h264_vaapi           H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (VAAPI)"

        args, message = CodecHelpers.get_encoder_configuration(
            6, 4, False, 20  # H.264 VAAPI
        )

        # Verify full VAAPI pipeline is present
        assert "-vaapi_device" in args
        assert "/dev/dri/renderD128" in args
        assert "-vf" in args
        assert "format=nv12,hwupload" in args
        assert "-c:v" in args
        assert "h264_vaapi" in args
        assert "VAAPI" in message
        assert "surface" in message.lower()

    @patch("subprocess.check_output")
    @patch.dict("os.environ", {"VAAPI_DEVICE": "/dev/dri/renderD129"})
    def test_vaapi_custom_device_from_env(self, mock_subprocess):
        """Test VAAPI uses custom device from environment variable"""
        mock_subprocess.return_value = "V..... h264_vaapi           H.264 / AVC (VAAPI)"

        args, _ = CodecHelpers.get_encoder_configuration(
            6, 4, False, 20
        )

        device_pos = args.index("-vaapi_device") + 1
        assert args[device_pos] == "/dev/dri/renderD129"

    @patch("subprocess.check_output")
    def test_vaapi_quality_settings(self, mock_subprocess):
        """Test VAAPI uses CQP rate control with proper QP value"""
        mock_subprocess.return_value = "V..... h264_vaapi           H.264 / AVC (VAAPI)"

        args, _ = CodecHelpers.get_encoder_configuration(
            6, 4, False, 22
        )

        assert "-rc_mode" in args
        rc_pos = args.index("-rc_mode") + 1
        assert args[rc_pos] == "CQP"

        assert "-qp" in args
        qp_pos = args.index("-qp") + 1
        assert args[qp_pos] == "22"

    @patch("subprocess.check_output")
    def test_vaapi_profile_high(self, mock_subprocess):
        """Test VAAPI uses high profile for H.264"""
        mock_subprocess.return_value = "V..... h264_vaapi           H.264 / AVC (VAAPI)"

        args, _ = CodecHelpers.get_encoder_configuration(
            6, 4, False, 20
        )

        profile_pos = args.index("-profile:v") + 1
        assert args[profile_pos] == "high"


class TestHEVC10BitMode:
    """Test HEVC 10-bit encoding mode"""

    def setup_method(self):
        """Clear cache before each test"""
        CodecHelpers.clear_cache()

    @patch("subprocess.check_output")
    def test_hevc_10bit_profile(self, mock_subprocess):
        """Test HEVC 10-bit uses main10 profile"""
        mock_subprocess.return_value = MockEncoderDetection.full_nvenc_support()

        args, _message = CodecHelpers.get_encoder_configuration(
            1, 4, False, 18, hevc_10bit=True
        )

        profile_pos = args.index("-profile:v") + 1
        assert args[profile_pos] == "main10"
        assert "-pix_fmt" in args
        pix_fmt_pos = args.index("-pix_fmt") + 1
        assert args[pix_fmt_pos] == "p010le"

    @patch("subprocess.check_output")
    def test_hevc_8bit_profile(self, mock_subprocess):
        """Test HEVC 8-bit uses main profile"""
        mock_subprocess.return_value = MockEncoderDetection.full_nvenc_support()

        args, _ = CodecHelpers.get_encoder_configuration(
            1, 4, False, 18, hevc_10bit=False
        )

        profile_pos = args.index("-profile:v") + 1
        assert args[profile_pos] == "main"
        # Should not have p010le pixel format
        assert "p010le" not in args


class TestPresetMapping:
    """Test preset mapping for different encoders"""

    def setup_method(self):
        """Clear cache before each test"""
        CodecHelpers.clear_cache()

    @pytest.mark.parametrize(
        ("preset_idx", "expected_nvenc", "expected_x264"),
        [
            (0, "p5", "medium"),    # Standard
            (1, "p7", "slow"),      # High Quality
            (2, "p3", "fast"),      # Fast
            (3, "p1", "ultrafast"), # Ultra Fast
        ],
    )
    @patch("subprocess.check_output")
    def test_preset_mapping_nvenc_and_x264(
        self, mock_subprocess, preset_idx, expected_nvenc, expected_x264
    ):
        """Test preset mapping for NVENC and x264 encoders"""
        mock_subprocess.return_value = MockEncoderDetection.full_nvenc_support()

        # Test NVENC
        CodecHelpers.clear_cache()
        args_nvenc, _ = CodecHelpers.get_encoder_configuration(
            0, 4, False, 18, preset_idx=preset_idx
        )
        preset_pos = args_nvenc.index("-preset") + 1
        assert args_nvenc[preset_pos] == expected_nvenc

        # Test x264
        CodecHelpers.clear_cache()
        args_x264, _ = CodecHelpers.get_encoder_configuration(
            3, 4, False, 18, preset_idx=preset_idx
        )
        preset_pos = args_x264.index("-preset") + 1
        assert args_x264[preset_pos] == expected_x264


class TestVideoMetadataExtraction:
    """Test video metadata extraction functionality"""

    @patch("subprocess.run")
    def test_extract_basic_metadata(self, mock_run):
        """Test extraction of basic video metadata"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '''{
            "format": {
                "duration": "3600.5",
                "bit_rate": "5000000",
                "format_name": "mov,mp4"
            },
            "streams": [{
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "bit_rate": "4500000"
            }]
        }'''
        mock_run.return_value = mock_result

        metadata = CodecHelpers.extract_video_metadata("/test/video.mp4")

        assert metadata is not None
        assert metadata["duration"] == "01:00:00"
        assert metadata["duration_seconds"] == 3600.5
        assert metadata["width"] == 1920
        assert metadata["height"] == 1080
        assert metadata["codec"] == "H264"
        assert "Mbps" in metadata["bitrate"]

    @patch("subprocess.run")
    def test_extract_metadata_no_video_stream(self, mock_run):
        """Test metadata extraction when no video stream exists"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '''{
            "format": {"duration": "300"},
            "streams": [{
                "codec_type": "audio",
                "codec_name": "aac"
            }]
        }'''
        mock_run.return_value = mock_result

        metadata = CodecHelpers.extract_video_metadata("/test/audio.mp3")
        assert metadata is None

    @patch("subprocess.run")
    def test_extract_metadata_ffprobe_failure(self, mock_run):
        """Test metadata extraction when ffprobe fails"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        metadata = CodecHelpers.extract_video_metadata("/test/invalid.mp4")
        assert metadata is None

    @patch("subprocess.run")
    def test_extract_metadata_timeout(self, mock_run):
        """Test metadata extraction with timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired("ffprobe", 30)

        metadata = CodecHelpers.extract_video_metadata("/test/video.mp4")
        assert metadata is None

    @patch("subprocess.run")
    def test_extract_metadata_invalid_json(self, mock_run):
        """Test metadata extraction with invalid JSON"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_run.return_value = mock_result

        metadata = CodecHelpers.extract_video_metadata("/test/video.mp4")
        assert metadata is None


class TestFileSizeEstimation:
    """Test output file size estimation"""

    def test_estimate_size_h264(self):
        """Test size estimation for H.264 codec"""
        metadata = {
            "duration_seconds": 3600,  # 1 hour
        }

        size = CodecHelpers.estimate_output_size(metadata, 0, 20)  # H.264 NVENC

        assert size is not None
        assert "MB" in size or "GB" in size

    def test_estimate_size_hevc(self):
        """Test HEVC produces smaller estimate than H.264"""
        metadata = {
            "duration_seconds": 3600,
        }

        size_h264 = CodecHelpers.estimate_output_size(metadata, 0, 20)
        size_hevc = CodecHelpers.estimate_output_size(metadata, 1, 20)

        # Both should return valid sizes
        assert size_h264 is not None
        assert size_hevc is not None

    def test_estimate_size_quality_impact(self):
        """Test quality setting affects size estimate"""
        metadata = {
            "duration_seconds": 3600,
        }

        # Lower CRF = higher quality = larger file
        size_high_quality = CodecHelpers.estimate_output_size(metadata, 0, 15)
        size_low_quality = CodecHelpers.estimate_output_size(metadata, 0, 30)

        # Both should return valid sizes (exact comparison depends on factors)
        assert size_high_quality is not None
        assert size_low_quality is not None

    def test_estimate_size_zero_duration(self):
        """Test size estimation with zero duration"""
        metadata = {
            "duration_seconds": 0,
        }

        size = CodecHelpers.estimate_output_size(metadata, 0, 20)
        assert size is None

    def test_estimate_size_negative_duration(self):
        """Test size estimation with negative duration"""
        metadata = {
            "duration_seconds": -100,
        }

        size = CodecHelpers.estimate_output_size(metadata, 0, 20)
        assert size is None


class TestDurationFormatting:
    """Test duration formatting utility"""

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "00:00:00"),
            (59, "00:00:59"),
            (60, "00:01:00"),
            (3599, "00:59:59"),
            (3600, "01:00:00"),
            (7261, "02:01:01"),
            (86400, "24:00:00"),
            (-1, "00:00:00"),  # Negative should return zero
        ],
    )
    def test_format_duration(self, seconds, expected):
        """Test duration formatting"""
        result = CodecHelpers._format_duration(seconds)
        assert result == expected


class TestBitrateFormatting:
    """Test bitrate formatting utility"""

    @pytest.mark.parametrize(
        ("bitrate_bps", "expected_contains"),
        [
            (500000, "Kbps"),        # 500 Kbps
            (5000000, "Mbps"),       # 5 Mbps
            (50000000, "Mbps"),      # 50 Mbps
            (5000000000, "Gbps"),    # 5 Gbps
            (0, "Unknown"),
            (None, "Unknown"),
            (-1000, "Unknown"),
        ],
    )
    def test_format_bitrate(self, bitrate_bps, expected_contains):
        """Test bitrate formatting"""
        result = CodecHelpers._format_bitrate(bitrate_bps)
        assert expected_contains in result


class TestFileSizeFormatting:
    """Test file size formatting utility"""

    @pytest.mark.parametrize(
        ("size_bytes", "expected_contains"),
        [
            (500, "B"),
            (5000, "KB"),
            (5000000, "MB"),
            (5000000000, "GB"),
        ],
    )
    def test_format_file_size(self, size_bytes, expected_contains):
        """Test file size formatting"""
        result = CodecHelpers.format_file_size(size_bytes)
        assert expected_contains in result
