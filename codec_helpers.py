#!/usr/bin/env python3
"""
Codec and encoding helpers for PyFFMPEG
Provides utility functions for codec selection, hardware acceleration detection,
and encoder configuration to reduce duplication in the main application.
"""

import contextlib
import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from config import EncodingConfig, FileConfig, HardwareConfig, ProcessConfig


class CodecHelpers:
    """Helper class for codec selection, hardware acceleration, and encoder configuration"""

    # Cache TTL settings (in seconds)
    # Success cache is longer - hardware doesn't change often
    _CACHE_TTL_SUCCESS: float = 300.0  # 5 minutes for successful detection
    # Failure cache is shorter - allows retry after transient errors
    _CACHE_TTL_FAILURE: float = 30.0  # 30 seconds for failed detection

    # Cache for expensive detection operations (with timestamps)
    _encoder_cache: Optional[str] = None
    _encoder_cache_time: float = 0.0
    _encoder_cache_success: bool = False

    _gpu_info_cache: Optional[str] = None
    _gpu_info_cache_time: float = 0.0
    _gpu_info_cache_success: bool = False

    _rtx40_detection_cache: Optional[bool] = None
    _rtx40_detection_cache_time: float = 0.0

    @staticmethod
    def get_output_extension(codec_idx: int) -> str:
        """Determine output file extension based on codec index"""
        if codec_idx in [0, 1, 2, 3, 5, 6]:  # H.264, HEVC, AV1, QSV, VAAPI
            return ".mp4"
        if codec_idx == 4:  # ProRes
            return ".mov"
        return ".mp4"  # Default

    @staticmethod
    def get_hardware_acceleration_args(hwdecode_idx: int) -> Tuple[List[str], str]:
        """Get hardware acceleration arguments based on selected hardware decode option
        Returns a tuple of (args_list, message_for_log)
        """
        args: List[str] = []
        message = ""

        try:
            if hwdecode_idx == 0:  # Auto
                # Use cached GPU detection for better performance
                gpu_info = CodecHelpers._get_gpu_info()
                if gpu_info and "GPU" in gpu_info:
                    args.extend(["-hwaccel", "cuda"])
                    message = "Using CUDA hardware acceleration (cached detection)"
                else:
                    # Try Intel QSV if NVIDIA not found
                    args.extend(["-hwaccel", "auto"])
                    message = "Using auto hardware acceleration"
            elif hwdecode_idx == 1:  # NVIDIA
                args.extend(["-hwaccel", "cuda"])
                message = "Using CUDA hardware acceleration"
            elif hwdecode_idx == 2:  # Intel QSV
                args.extend(["-hwaccel", "qsv", "-hwaccel_output_format", "qsv"])
                message = "Using QSV hardware acceleration with surface output"
            elif hwdecode_idx == 3:  # VAAPI
                # Only on Linux systems
                if os.name == "posix":
                    vaapi_device = os.environ.get("VAAPI_DEVICE", "/dev/dri/renderD128")
                    args.extend([
                        "-hwaccel", "vaapi",
                        "-hwaccel_device", vaapi_device,
                        "-hwaccel_output_format", "vaapi",
                    ])
                    message = "Using VAAPI hardware acceleration with surface output"
                else:
                    # Windows fallback for VAAPI selection
                    args.extend(["-hwaccel", "auto"])
                    message = "VAAPI not available, falling back to auto"
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as e:
            # If any error occurs, fall back to software decoding
            message = (
                f"Hardware acceleration error: {e}, falling back to software decoding"
            )
            # No hwaccel arguments

        return args, message

    @staticmethod
    def get_audio_codec_args(path: str, codec_idx: int) -> Tuple[List[str], str]:
        """Get audio codec configuration arguments based on input file and selected video codec
        Returns a tuple of (args_list, message_for_log)
        """
        args: List[str] = []
        message = ""

        try:
            # Check for existing audio - try to pass through when possible
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-show_entries",
                    "stream=codec_name",
                    "-select_streams",
                    "a:0",
                    "-of",
                    "default=nokey=1:noprint_wrappers=1",
                    path,
                ],
                check=False, text=True,
                capture_output=True,
                timeout=ProcessConfig.SUBPROCESS_TIMEOUT,
            )
            audio_codec = probe.stdout.strip()

            # Copy AC-3/AAC audio to skip needless re-encode
            if audio_codec in ("aac", "ac3", "eac3"):
                args.extend(["-c:a", "copy"])
                message = f"Detected {audio_codec} audio - using passthrough"
            else:
                # Handle ProRes special case, otherwise AAC
                if codec_idx == 4:  # ProRes
                    args.extend(["-c:a", "pcm_s16le"])
                    message = "Using PCM audio for ProRes"
                else:
                    args.extend(
                        [
                            "-c:a",
                            "aac",
                            "-b:a",
                            f"{EncodingConfig.AUDIO_BITRATE_DEFAULT}k",
                        ]
                    )
                    message = f"Converting audio to AAC {EncodingConfig.AUDIO_BITRATE_DEFAULT}k"
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            # Fallback to default encoding on error
            if codec_idx == 4:  # ProRes
                args.extend(["-c:a", "pcm_s16le"])
                message = "Fallback to PCM audio for ProRes"
            else:
                args.extend(
                    ["-c:a", "aac", "-b:a", f"{EncodingConfig.AUDIO_BITRATE_DEFAULT}k"]
                )
                message = (
                    f"Fallback to AAC {EncodingConfig.AUDIO_BITRATE_DEFAULT}k audio"
                )

        return args, message

    @staticmethod
    def get_encoder_configuration(
        codec_idx: int,
        thread_count: int,
        is_parallel_enabled: bool,
        crf_value: int,
        hevc_10bit: bool = False,
        nvenc_settings: Optional[Dict[str, Any]] = None,
        preset_idx: int = 0,
    ) -> Tuple[List[str], str]:
        """Get encoder configuration arguments based on codec index
        Returns a tuple of (args_list, message_for_log)

        Codec mapping:
        0 = H.264 NVENC
        1 = HEVC NVENC
        2 = AV1 NVENC
        3 = x264 CPU
        4 = ProRes CPU
        5 = H.264 QSV
        6 = H.264 VAAPI

        Preset mapping (preset_idx from UI):
        0 = Standard, 1 = High Quality, 2 = Fast, 3 = Ultra Fast
        """
        args: List[str] = []
        message = ""

        # Map UI preset index to NVENC presets (p1=fastest, p7=highest quality)
        nvenc_presets = {0: "p5", 1: "p7", 2: "p3", 3: "p1"}
        # Map UI preset index to x264/software presets
        x264_presets = {0: "medium", 1: "slow", 2: "fast", 3: "ultrafast"}
        # Map UI preset index to QSV presets
        qsv_presets = {0: "medium", 1: "slow", 2: "fast", 3: "veryfast"}

        nvenc_preset = nvenc_presets.get(preset_idx, "p5")
        x264_preset = x264_presets.get(preset_idx, "medium")
        qsv_preset = qsv_presets.get(preset_idx, "medium")

        try:
            # Get cached or detect available encoders
            available_encoders = CodecHelpers._get_available_encoders()

            # H.264 NVENC
            if codec_idx == 0 and "h264_nvenc" in available_encoders:
                args.extend(
                    [
                        "-c:v",
                        "h264_nvenc",
                        "-preset",
                        nvenc_preset,
                        "-profile:v",
                        "high",
                        "-rc",
                        "vbr",  # Use standard vbr mode
                        "-cq",
                        str(crf_value),
                        "-b:v",
                        "0",  # Required for VBR mode
                        "-bf",
                        "4",
                        "-b_ref_mode",
                        "middle",
                        "-temporal-aq",
                        "1",
                        "-spatial-aq",
                        "1",
                        "-rc-lookahead",
                        "32",
                    ]
                )
                message = "Using H.264 NVENC hardware encoding"

            # HEVC NVENC
            elif codec_idx == 1 and "hevc_nvenc" in available_encoders:
                args.extend(
                    [
                        "-c:v",
                        "hevc_nvenc",
                        "-preset",
                        nvenc_preset,
                        "-profile:v",
                        "main10" if hevc_10bit else "main",
                        "-rc",
                        "vbr",  # Use standard vbr mode
                        "-cq",
                        str(crf_value),
                        "-b:v",
                        "0",  # Required for VBR mode
                        "-bf",
                        "4",
                        "-b_ref_mode",
                        "middle",
                        "-temporal-aq",
                        "1",
                        "-spatial-aq",
                        "1",
                        "-rc-lookahead",
                        "32",
                    ]
                )
                if hevc_10bit:
                    args.extend(["-pix_fmt", "p010le"])
                message = "Using HEVC NVENC hardware encoding"

            # AV1 NVENC
            elif codec_idx == 2 and "av1_nvenc" in available_encoders:
                args.extend(
                    [
                        "-c:v",
                        "av1_nvenc",
                        "-preset",
                        nvenc_preset,
                        "-rc",
                        "vbr",  # AV1 NVENC uses 'vbr' not 'vbr_hq'
                        "-cq",
                        str(crf_value),
                        "-b:v",
                        "0",  # Required for VBR mode
                        "-temporal-aq",
                        "1",
                        "-spatial-aq",
                        "1",
                        "-rc-lookahead",
                        "32",
                        "-highbitdepth",
                        "1",
                    ]
                )
                message = "Using AV1 NVENC hardware encoding"

            # x264 CPU
            elif codec_idx == 3:
                args.extend(
                    [
                        "-c:v",
                        "libx264",
                        "-crf",
                        str(crf_value),
                        "-preset",
                        x264_preset,
                        "-pix_fmt",
                        "yuv420p",
                    ]
                )
                if thread_count > 0:
                    args.extend(["-threads", str(thread_count)])
                message = "Using x264 CPU encoding"

            # ProRes
            elif codec_idx == 4:
                args.extend(
                    [
                        "-c:v",
                        "prores_ks",
                        "-profile:v",
                        "3",
                        "-vendor",
                        "ap10",
                        "-pix_fmt",
                        "yuv422p10le",
                    ]
                )
                if thread_count > 0:
                    args.extend(["-threads", str(thread_count)])
                message = "Using ProRes 422 encoding"

            # H.264 QSV
            elif codec_idx == 5 and "h264_qsv" in available_encoders:
                # Full QSV pipeline: init device, set filter device, hwupload filter
                args.extend(
                    [
                        "-init_hw_device", "qsv=hw",
                        "-filter_hw_device", "hw",
                        "-vf", "hwupload=extra_hw_frames=64,format=qsv",
                        "-c:v", "h264_qsv",
                        "-preset", qsv_preset,
                        "-global_quality", str(crf_value),
                    ]
                )
                message = "Using H.264 QSV hardware encoding with surface upload"

            # H.264 VAAPI
            elif codec_idx == 6 and "h264_vaapi" in available_encoders:
                # Full VAAPI pipeline: device init and hwupload filter
                vaapi_device = os.environ.get("VAAPI_DEVICE", "/dev/dri/renderD128")
                args.extend(
                    [
                        "-vaapi_device", vaapi_device,
                        "-vf", "format=nv12,hwupload",
                        "-c:v", "h264_vaapi",
                        "-profile:v", "high",
                        "-rc_mode", "CQP",
                        "-qp", str(crf_value),
                    ]
                )
                message = "Using H.264 VAAPI hardware encoding with surface upload"

            else:
                # Fallback to basic h264
                args.extend(
                    [
                        "-c:v",
                        "libx264",
                        "-crf",
                        str(EncodingConfig.DEFAULT_CRF_FALLBACK),
                        "-preset",
                        "medium",
                        "-pix_fmt",
                        "yuv420p",
                    ]
                )
                if thread_count > 0:
                    args.extend(["-threads", str(thread_count)])
                message = f"Selected codec not available (codec_idx={codec_idx}), falling back to libx264"

        except Exception as e:
            # Ultimate fallback
            message = f"Error selecting codec: {e}, using safe defaults"
            args.extend(
                [
                    "-c:v",
                    "libx264",
                    "-crf",
                    "23",
                    "-preset",
                    "medium",
                    "-pix_fmt",
                    "yuv420p",
                ]
            )
            if thread_count > 0:
                args.extend(["-threads", str(thread_count)])

        return args, message

    @staticmethod
    def optimize_threads_for_codec(
        codec_idx: int,
        is_parallel_enabled: bool,
        file_codec_assignments: Optional[Dict[str, int]] = None,
    ) -> int:
        """Optimize thread count based on selected codec and parallel processing mode"""
        # NVENC encoders - minimal CPU usage
        if codec_idx in (0, 1, 2):  # Any NVENC encoder
            return 2

        # Hardware encoders (QSV, VAAPI) - moderate CPU usage
        if codec_idx in (5, 6):  # QSV, VAAPI
            return 4

        # Single CPU job - let encoder use most threads but leave some for system
        if not is_parallel_enabled:
            cpu_count = os.cpu_count() or ProcessConfig.OPTIMAL_CPU_THREADS
            return max(2, cpu_count - 4)  # Leave 4 threads for system

        # Parallel CPU jobs - divide threads efficiently
        # For auto-balance: assume worst case of all CPU jobs running simultaneously
        if file_codec_assignments:
            cpu_jobs = max(
                1, sum(1 for c in file_codec_assignments.values() if c in (3, 4))
            )  # x264, ProRes
        else:
            cpu_jobs = 2  # Conservative estimate for parallel processing

        cpu_count = os.cpu_count() or ProcessConfig.OPTIMAL_CPU_THREADS
        threads_per_job = max(
            2, (cpu_count - 2) // cpu_jobs
        )  # Leave 2 threads for system
        return threads_per_job

    @staticmethod
    def _get_available_encoders() -> str:
        """Get available encoders with TTL-based caching for performance.

        Uses different TTLs for success vs failure to allow retry after transient errors
        while avoiding repeated expensive calls during normal operation.
        """
        now = time.time()

        # Check if cache is still valid
        if CodecHelpers._encoder_cache is not None:
            ttl = (
                CodecHelpers._CACHE_TTL_SUCCESS
                if CodecHelpers._encoder_cache_success
                else CodecHelpers._CACHE_TTL_FAILURE
            )
            if (now - CodecHelpers._encoder_cache_time) < ttl:
                return CodecHelpers._encoder_cache

        try:
            encoders_output = subprocess.check_output(
                ["ffmpeg", "-encoders"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=ProcessConfig.SUBPROCESS_TIMEOUT,
            )
            CodecHelpers._encoder_cache = encoders_output.lower()
            CodecHelpers._encoder_cache_time = now
            CodecHelpers._encoder_cache_success = True
            return CodecHelpers._encoder_cache
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            # Cache the failure with shorter TTL to allow retry
            CodecHelpers._encoder_cache = ""
            CodecHelpers._encoder_cache_time = now
            CodecHelpers._encoder_cache_success = False
            return ""

    @staticmethod
    def _get_gpu_info() -> str:
        """Get GPU information with TTL-based caching.

        Uses different TTLs for success vs failure to allow retry after transient errors.
        """
        now = time.time()

        # Check if cache is still valid
        if CodecHelpers._gpu_info_cache is not None:
            ttl = (
                CodecHelpers._CACHE_TTL_SUCCESS
                if CodecHelpers._gpu_info_cache_success
                else CodecHelpers._CACHE_TTL_FAILURE
            )
            if (now - CodecHelpers._gpu_info_cache_time) < ttl:
                return CodecHelpers._gpu_info_cache

        try:
            gpu_info = subprocess.check_output(
                ["nvidia-smi", "-q"], timeout=HardwareConfig.GPU_DETECTION_TIMEOUT
            ).decode("utf-8")
            CodecHelpers._gpu_info_cache = gpu_info
            CodecHelpers._gpu_info_cache_time = now
            CodecHelpers._gpu_info_cache_success = True
            return gpu_info
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            CodecHelpers._gpu_info_cache = ""
            CodecHelpers._gpu_info_cache_time = now
            CodecHelpers._gpu_info_cache_success = False
            return ""

    @staticmethod
    def detect_rtx40_series() -> bool:
        """Detect if system has RTX 40 series GPU for AV1 encoding support with TTL caching.

        Cache inherits TTL from _get_gpu_info() since it depends on that data.
        """
        now = time.time()

        # Check if cache is still valid (use same TTL as GPU info since it depends on it)
        if (
            CodecHelpers._rtx40_detection_cache is not None
            and (now - CodecHelpers._rtx40_detection_cache_time) < CodecHelpers._CACHE_TTL_SUCCESS
        ):
            return CodecHelpers._rtx40_detection_cache

        try:
            gpu_info = CodecHelpers._get_gpu_info()
            has_rtx40 = any(gpu in gpu_info for gpu in HardwareConfig.RTX40_MODELS)
            CodecHelpers._rtx40_detection_cache = has_rtx40
            CodecHelpers._rtx40_detection_cache_time = now
            return has_rtx40
        except Exception:
            CodecHelpers._rtx40_detection_cache = False
            CodecHelpers._rtx40_detection_cache_time = now
            return False

    @staticmethod
    def is_rtx40_cached() -> Optional[bool]:
        """Check if RTX40 detection result is cached (returns None if not cached).

        Use this for UI validation to avoid blocking the main thread.
        Returns True/False if cached, None if detection hasn't run yet.
        """
        return CodecHelpers._rtx40_detection_cache

    @staticmethod
    def clear_cache() -> None:
        """Clear all cached detection results - useful for testing or system changes"""
        CodecHelpers._encoder_cache = None
        CodecHelpers._encoder_cache_time = 0.0
        CodecHelpers._encoder_cache_success = False

        CodecHelpers._gpu_info_cache = None
        CodecHelpers._gpu_info_cache_time = 0.0
        CodecHelpers._gpu_info_cache_success = False

        CodecHelpers._rtx40_detection_cache = None
        CodecHelpers._rtx40_detection_cache_time = 0.0

    @staticmethod
    def extract_video_metadata(file_path: str) -> Optional[Dict[str, Any]]:
        """Extract video metadata using ffprobe

        Returns:
            Dict with keys: duration, width, height, codec, bitrate, format_name
            None if extraction fails
        """
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]

            result = subprocess.run(
                cmd,
                check=False, capture_output=True,
                text=True,
                timeout=ProcessConfig.SUBPROCESS_TIMEOUT,
            )

            if result.returncode != 0:
                return None

            data = json.loads(result.stdout)

            # Find video stream
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if not video_stream:
                return None

            # Extract format info
            format_info = data.get("format", {})

            # Parse duration
            duration_str = format_info.get("duration", "0")
            try:
                duration_seconds = float(duration_str)
                duration_formatted = CodecHelpers._format_duration(duration_seconds)
            except (ValueError, TypeError):
                duration_formatted = "Unknown"
                duration_seconds = 0

            # Extract video properties
            width = video_stream.get("width", 0)
            height = video_stream.get("height", 0)
            codec_name = video_stream.get("codec_name", "Unknown")

            # Calculate bitrate
            bitrate_bps = None
            if "bit_rate" in video_stream:
                with contextlib.suppress(ValueError, TypeError):
                    bitrate_bps = int(video_stream["bit_rate"])

            if not bitrate_bps and "bit_rate" in format_info:
                with contextlib.suppress(ValueError, TypeError):
                    bitrate_bps = int(format_info["bit_rate"])

            bitrate_formatted = (
                CodecHelpers._format_bitrate(bitrate_bps) if bitrate_bps else "Unknown"
            )

            return {
                "duration": duration_formatted,
                "duration_seconds": duration_seconds,
                "width": width,
                "height": height,
                "codec": codec_name.upper(),
                "bitrate": bitrate_formatted,
                "bitrate_bps": bitrate_bps,
                "format_name": format_info.get("format_name", "Unknown"),
            }

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
            OSError,
            Exception,
        ):
            return None

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration from seconds to HH:MM:SS"""
        if seconds <= 0:
            return "00:00:00"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _format_bitrate(bitrate_bps: Optional[int]) -> str:
        """Format bitrate from bits per second to human readable"""
        if not bitrate_bps or bitrate_bps <= 0:
            return "Unknown"

        # Convert to Mbps
        mbps = bitrate_bps / 1_000_000

        if mbps >= 1000:
            return f"{mbps / 1000:.1f} Gbps"
        if mbps >= 1:
            return f"{mbps:.1f} Mbps"
        # Convert to Kbps
        kbps = bitrate_bps / 1000
        return f"{kbps:.0f} Kbps"

    @staticmethod
    def estimate_output_size(
        input_metadata: Dict[str, Any], codec_idx: int, crf_value: int
    ) -> Optional[str]:
        """Estimate output file size based on input metadata and encoding settings

        Args:
            input_metadata: Metadata dict from extract_video_metadata
            codec_idx: Codec index (0=H.264 NVENC, 1=HEVC NVENC, etc.)
            crf_value: Quality setting

        Returns:
            Formatted size string like "850 MB" or None if calculation fails
        """
        duration_seconds = input_metadata.get("duration_seconds", 0)
        if duration_seconds <= 0:
            return None

        # Get base size factor from config
        size_factors = {
            0: FileConfig.SIZE_FACTOR_H264,  # H.264 NVENC
            1: FileConfig.SIZE_FACTOR_HEVC,  # HEVC NVENC
            2: FileConfig.SIZE_FACTOR_AV1,  # AV1 NVENC
            3: FileConfig.SIZE_FACTOR_X264,  # x264
            4: FileConfig.SIZE_FACTOR_PRORES_422
            if crf_value <= 20
            else FileConfig.SIZE_FACTOR_PRORES_4444,  # ProRes
            5: FileConfig.SIZE_FACTOR_H264,  # H.264 QSV
            6: FileConfig.SIZE_FACTOR_H264,  # H.264 VAAPI
        }

        base_factor = size_factors.get(codec_idx, FileConfig.SIZE_FACTOR_DEFAULT)

        # Apply quality multiplier based on CRF
        # Lower CRF = higher quality = larger file
        if crf_value <= 15:
            quality_multiplier = 1.5
        elif crf_value <= 18:
            quality_multiplier = 1.2
        elif crf_value <= 23:
            quality_multiplier = 1.0
        elif crf_value <= 28:
            quality_multiplier = 0.8
        else:
            quality_multiplier = 0.6

        # Calculate size in MB
        duration_minutes = duration_seconds / 60
        estimated_mb = duration_minutes * base_factor * quality_multiplier

        return CodecHelpers.format_file_size(
            estimated_mb * 1_000_000
        )  # Convert to bytes

    @staticmethod
    def format_file_size(size_bytes: float) -> str:
        """Format file size in bytes to human readable"""
        if size_bytes < 1024:
            return f"{size_bytes:.0f} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.0f} MB"
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
