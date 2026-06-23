#!/usr/bin/env python3
"""
Codec and encoding helpers for PyFFMPEG
Provides utility functions for codec selection, hardware acceleration detection,
and encoder configuration to reduce duplication in the main application.
"""

import os
import subprocess
import time
from typing import ClassVar, override

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from config import CodecIndex, EncodingConfig, HardwareConfig, ProcessConfig
from domain.codec import codec_by_index


class GPUDetectionSignals(QObject):
    """Signals for GPU detection worker."""

    detection_complete: ClassVar[Signal] = Signal(
        bool, str, str
    )  # has_gpu, gpu_name, available_encoders


class GPUDetectionWorker(QRunnable):
    """Worker to detect GPU and available encoders in a background thread.

    Prevents UI freezes when probing nvidia-smi and ffmpeg encoders on first use.
    """

    def __init__(self, signals: GPUDetectionSignals):
        super().__init__()
        self.signals: GPUDetectionSignals = signals

    @override
    def run(self) -> None:
        """Probe GPU and encoders, then emit result."""
        gpu_name = ""
        has_gpu = False
        available_encoders = ""

        # Detect GPU via nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=HardwareConfig.GPU_DETECTION_TIMEOUT,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_name = result.stdout.strip().split("\n")[0]
                has_gpu = True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        # Detect available encoders via ffmpeg
        try:
            result = subprocess.run(
                ["ffmpeg", "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=ProcessConfig.SUBPROCESS_TIMEOUT,
                check=False,
            )
            if result.returncode == 0:
                available_encoders = result.stdout.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        self.signals.detection_complete.emit(has_gpu, gpu_name, available_encoders)


class GPUDetector(QObject):
    """Async GPU and encoder detection to prevent UI freezes.

    Usage:
        detector = GPUDetector(parent)
        detector.gpu_detected.connect(on_gpu_detected)
        detector.detect_async()

        def on_gpu_detected(has_gpu, gpu_name, encoders):
            # Update CodecHelpers cache
            CodecHelpers.update_gpu_cache(has_gpu, gpu_name, encoders)
    """

    # Signal emitted when detection completes
    gpu_detected: ClassVar[Signal] = Signal(
        bool, str, str
    )  # has_gpu, gpu_name, available_encoders

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._detection_signals: GPUDetectionSignals | None = None

    def detect_async(self) -> None:
        """Start async GPU detection.

        If cache already exists, emits signal immediately.
        Otherwise runs detection in background thread.
        """
        # Check if already cached using public accessor
        if CodecHelpers.has_cached_info():
            # Emit cached results using public accessors
            cached_gpu_info = CodecHelpers.get_cached_gpu_info()
            has_gpu = bool(cached_gpu_info)
            gpu_name = ""
            if has_gpu and cached_gpu_info:
                # Try to extract GPU name from cached info
                for model in HardwareConfig.RTX40_MODELS:
                    if model in cached_gpu_info:
                        gpu_name = model
                        break
            self.gpu_detected.emit(
                has_gpu, gpu_name, CodecHelpers.get_cached_encoder_info() or ""
            )
            return

        # Run detection in background
        self._detection_signals = GPUDetectionSignals()
        _ = self._detection_signals.detection_complete.connect(
            self._on_detection_complete
        )
        worker = GPUDetectionWorker(self._detection_signals)
        QThreadPool.globalInstance().start(worker)

    def _on_detection_complete(
        self, has_gpu: bool, gpu_name: str, available_encoders: str
    ) -> None:
        """Handle detection result and update cache."""
        # Update CodecHelpers cache
        CodecHelpers.update_gpu_cache(has_gpu, gpu_name, available_encoders)
        # Emit signal for UI handling
        self.gpu_detected.emit(has_gpu, gpu_name, available_encoders)


class CodecHelpers:
    """Helper class for codec selection, hardware acceleration, and encoder configuration"""

    # Cache TTL settings (in seconds)
    # Success cache is longer - hardware doesn't change often
    _CACHE_TTL_SUCCESS: float = 300.0  # 5 minutes for successful detection
    # Failure cache is shorter - allows retry after transient errors
    _CACHE_TTL_FAILURE: float = 30.0  # 30 seconds for failed detection

    # Cache for expensive detection operations (with timestamps)
    _encoder_cache: str | None = None
    _encoder_cache_time: float = 0.0
    _encoder_cache_success: bool = False

    _gpu_info_cache: str | None = None
    _gpu_info_cache_time: float = 0.0
    _gpu_info_cache_success: bool = False

    _rtx40_detection_cache: bool | None = None
    _rtx40_detection_cache_time: float = 0.0

    @staticmethod
    def has_cached_info() -> bool:
        """Check if GPU or encoder info has been cached.

        Used by GPUDetector to avoid redundant detection if cache exists.
        """
        return (
            CodecHelpers._gpu_info_cache is not None
            or CodecHelpers._encoder_cache is not None
        )

    @staticmethod
    def get_cached_gpu_info() -> str | None:
        """Get cached GPU info string.

        Returns:
            Cached GPU info or None if not cached.
        """
        return CodecHelpers._gpu_info_cache

    @staticmethod
    def get_cached_encoder_info() -> str | None:
        """Get cached encoder info string.

        Returns:
            Cached encoder string or None if not cached.
        """
        return CodecHelpers._encoder_cache

    @staticmethod
    def get_output_extension(codec_idx: int) -> str:
        """Determine output file extension based on codec index"""
        codec = codec_by_index(codec_idx)
        return codec.container_ext if codec is not None else ".mkv"

    @staticmethod
    def get_hardware_acceleration_args(hwdecode_idx: int) -> tuple[list[str], str]:
        """Get hardware acceleration arguments based on selected hardware decode option
        Returns a tuple of (args_list, message_for_log)
        """
        args: list[str] = []
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
                    args.extend(
                        [
                            "-hwaccel",
                            "vaapi",
                            "-hwaccel_device",
                            vaapi_device,
                            "-hwaccel_output_format",
                            "vaapi",
                        ]
                    )
                    message = "Using VAAPI hardware acceleration with surface output"
                else:
                    # Windows fallback for VAAPI selection
                    # Note: This appears unreachable on Linux but is needed for Windows
                    args.extend(["-hwaccel", "auto"])  # pyright: ignore[reportUnreachable]
                    message = "VAAPI not available, falling back to auto"
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as e:
            # If any error occurs, fall back to software decoding
            message = (
                f"Hardware acceleration error: {e}, falling back to software decoding"
            )
            # No hwaccel arguments

        return args, message

    @staticmethod
    def get_audio_codec_args(path: str, codec_idx: int) -> tuple[list[str], str]:
        """Get audio codec configuration arguments based on input file and selected video codec
        Returns a tuple of (args_list, message_for_log)
        """
        args: list[str] = []
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
                check=False,
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
                if codec_idx == CodecIndex.PRORES:
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
            if codec_idx == CodecIndex.PRORES:
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
        _is_parallel_enabled: bool,
        crf_value: int,
        hevc_10bit: bool = False,
        _nvenc_settings: object | None = None,
        preset_idx: int = 0,
    ) -> tuple[list[str], str]:
        """Get encoder configuration arguments based on codec index.

        Returns a tuple of (args_list, message_for_log).

        Codec indices are defined in CodecIndex class (config.py).

        Preset mapping (preset_idx from UI):
        0 = Standard, 1 = High Quality, 2 = Fast, 3 = Ultra Fast
        """
        args: list[str] = []
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
            if (
                codec_idx == CodecIndex.H264_NVENC
                and "h264_nvenc" in available_encoders
            ):
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
            elif (
                codec_idx == CodecIndex.HEVC_NVENC
                and "hevc_nvenc" in available_encoders
            ):
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
            elif (
                codec_idx == CodecIndex.AV1_NVENC and "av1_nvenc" in available_encoders
            ):
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
            elif codec_idx == CodecIndex.X264_CPU:
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
            elif codec_idx == CodecIndex.PRORES:
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
            elif codec_idx == CodecIndex.H264_QSV and "h264_qsv" in available_encoders:
                # Full QSV pipeline: init device, set filter device, hwupload filter
                args.extend(
                    [
                        "-init_hw_device",
                        "qsv=hw",
                        "-filter_hw_device",
                        "hw",
                        "-vf",
                        "hwupload=extra_hw_frames=64,format=qsv",
                        "-c:v",
                        "h264_qsv",
                        "-preset",
                        qsv_preset,
                        "-global_quality",
                        str(crf_value),
                    ]
                )
                message = "Using H.264 QSV hardware encoding with surface upload"

            # H.264 VAAPI
            elif (
                codec_idx == CodecIndex.H264_VAAPI
                and "h264_vaapi" in available_encoders
            ):
                # Full VAAPI pipeline: device init and hwupload filter
                vaapi_device = os.environ.get("VAAPI_DEVICE", "/dev/dri/renderD128")
                args.extend(
                    [
                        "-vaapi_device",
                        vaapi_device,
                        "-vf",
                        "format=nv12,hwupload",
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
        file_codec_assignments: dict[str, int] | None = None,
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
            and (now - CodecHelpers._rtx40_detection_cache_time)
            < CodecHelpers._CACHE_TTL_SUCCESS
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
    def is_rtx40_cached() -> bool | None:
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
    def update_gpu_cache(has_gpu: bool, gpu_name: str, available_encoders: str) -> None:
        """Update GPU and encoder caches from async detection results.

        Called by GPUDetector after background detection completes.

        Args:
            has_gpu: Whether a GPU was detected
            gpu_name: Name of the detected GPU (e.g., "RTX 4090")
            available_encoders: Lowercase string of available encoders from ffmpeg
        """
        now = time.time()

        # Update encoder cache
        if available_encoders:
            CodecHelpers._encoder_cache = available_encoders
            CodecHelpers._encoder_cache_time = now
            CodecHelpers._encoder_cache_success = True
        else:
            CodecHelpers._encoder_cache = ""
            CodecHelpers._encoder_cache_time = now
            CodecHelpers._encoder_cache_success = False

        # Update GPU info cache - store GPU name if detected
        if has_gpu and gpu_name:
            CodecHelpers._gpu_info_cache = gpu_name
            CodecHelpers._gpu_info_cache_time = now
            CodecHelpers._gpu_info_cache_success = True

            # Update RTX40 detection cache
            is_rtx40 = any(model in gpu_name for model in HardwareConfig.RTX40_MODELS)
            CodecHelpers._rtx40_detection_cache = is_rtx40
            CodecHelpers._rtx40_detection_cache_time = now
        else:
            CodecHelpers._gpu_info_cache = ""
            CodecHelpers._gpu_info_cache_time = now
            CodecHelpers._gpu_info_cache_success = False
            CodecHelpers._rtx40_detection_cache = False
            CodecHelpers._rtx40_detection_cache_time = now
