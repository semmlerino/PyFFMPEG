#!/usr/bin/env python3
"""
Codec and encoding helpers for PyFFMPEG
Provides utility functions for codec selection, hardware acceleration detection,
and encoder configuration to reduce duplication in the main application.
"""

import os
import subprocess

from config import ProcessConfig, HardwareConfig, EncodingConfig


class CodecHelpers:
    """Helper class for codec selection, hardware acceleration, and encoder configuration"""

    # Cache for expensive detection operations
    _encoder_cache = None
    _gpu_info_cache = None
    _rtx40_detection_cache = None

    @staticmethod
    def get_output_extension(codec_idx):
        """Determine output file extension based on codec index"""
        if codec_idx in [0, 1, 2, 3, 5, 6]:  # H.264, HEVC, AV1, QSV, VAAPI
            return ".mp4"
        elif codec_idx == 4:  # ProRes
            return ".mov"
        return ".mp4"  # Default

    @staticmethod
    def get_hardware_acceleration_args(hwdecode_idx):
        """Get hardware acceleration arguments based on selected hardware decode option
        Returns a tuple of (args_list, message_for_log)
        """
        args = []
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
                args.extend(["-hwaccel", "qsv"])
                message = "Using QSV hardware acceleration"
            elif hwdecode_idx == 3:  # VAAPI
                # Only on Linux systems
                if os.name == "posix":
                    args.extend(
                        ["-hwaccel", "vaapi", "-hwaccel_device", "/dev/dri/renderD128"]
                    )
                    message = "Using VAAPI hardware acceleration"
                else:
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
    def get_audio_codec_args(path, codec_idx):
        """Get audio codec configuration arguments based on input file and selected video codec
        Returns a tuple of (args_list, message_for_log)
        """
        args = []
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
                text=True,
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
        codec_idx,
        thread_count,
        is_parallel_enabled,
        crf_value,
        hevc_10bit=False,
        nvenc_settings=None,
    ):
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
        """
        args = []
        message = ""

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
                        "p7",  # High quality preset
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
                        "p7",
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
                        "p7",
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
                        "medium",
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
                args.extend(
                    [
                        "-c:v",
                        "h264_qsv",
                        "-preset",
                        "medium",
                        "-global_quality",
                        str(crf_value),
                    ]
                )
                message = "Using H.264 QSV hardware encoding"

            # H.264 VAAPI
            elif codec_idx == 6 and "h264_vaapi" in available_encoders:
                args.extend(
                    [
                        "-c:v",
                        "h264_vaapi",
                        "-profile:v",
                        "high",
                        "-rc_mode",
                        "CQP",
                        "-qp",
                        str(crf_value),
                    ]
                )
                message = "Using H.264 VAAPI hardware encoding"

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
        codec_idx, is_parallel_enabled, file_codec_assignments=None
    ):
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
            cpu_jobs = max(1, sum(1 for c in file_codec_assignments.values() if c in (3, 4)))  # x264, ProRes
        else:
            cpu_jobs = 2  # Conservative estimate for parallel processing
            
        cpu_count = os.cpu_count() or ProcessConfig.OPTIMAL_CPU_THREADS
        threads_per_job = max(2, (cpu_count - 2) // cpu_jobs)  # Leave 2 threads for system
        return threads_per_job

    @staticmethod
    def _get_available_encoders():
        """Get available encoders with caching for performance"""
        if CodecHelpers._encoder_cache is not None:
            return CodecHelpers._encoder_cache

        try:
            encoders_output = subprocess.check_output(
                ["ffmpeg", "-encoders"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=ProcessConfig.SUBPROCESS_TIMEOUT,
            )
            CodecHelpers._encoder_cache = encoders_output.lower()
            return CodecHelpers._encoder_cache
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            # Cache the failure to avoid repeated attempts
            CodecHelpers._encoder_cache = ""
            return ""

    @staticmethod
    def _get_gpu_info():
        """Get GPU information with caching"""
        if CodecHelpers._gpu_info_cache is not None:
            return CodecHelpers._gpu_info_cache

        try:
            gpu_info = subprocess.check_output(
                ["nvidia-smi", "-q"], timeout=HardwareConfig.GPU_DETECTION_TIMEOUT
            ).decode("utf-8")
            CodecHelpers._gpu_info_cache = gpu_info
            return gpu_info
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            CodecHelpers._gpu_info_cache = ""
            return ""

    @staticmethod
    def detect_rtx40_series():
        """Detect if system has RTX 40 series GPU for AV1 encoding support with caching"""
        if CodecHelpers._rtx40_detection_cache is not None:
            return CodecHelpers._rtx40_detection_cache

        try:
            gpu_info = CodecHelpers._get_gpu_info()
            has_rtx40 = any(gpu in gpu_info for gpu in HardwareConfig.RTX40_MODELS)
            CodecHelpers._rtx40_detection_cache = has_rtx40
            return has_rtx40
        except Exception:
            CodecHelpers._rtx40_detection_cache = False
            return False

    @staticmethod
    def clear_cache():
        """Clear all cached detection results - useful for testing or system changes"""
        CodecHelpers._encoder_cache = None
        CodecHelpers._gpu_info_cache = None
        CodecHelpers._rtx40_detection_cache = None
