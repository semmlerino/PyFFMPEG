"""FFmpeg argument builder for codec and hardware acceleration selection.

All methods are stateless (pure inputs → CLI args) so they are safe to call
from any thread. Hardware detection is delegated to HARDWARE_PROBE.
"""

from __future__ import annotations

import os
import subprocess

from pympeg.config import CodecIndex, EncodingConfig, ProcessConfig
from pympeg.domain.codec import codec_by_index
from pympeg.domain.settings import NvencSettings
from pympeg.ffprobe import run_ffprobe
from pympeg.hardware.probe import HARDWARE_PROBE


class CodecArgBuilder:
    """Builds FFmpeg CLI arguments for codec selection, hardware acceleration, and audio."""

    @staticmethod
    def _nvenc_quality_args(
        crf_value: int,
        nvenc_settings: NvencSettings,
        *,
        include_b_frame_count: bool,
    ) -> list[str]:
        """Build shared NVENC quality/rate-control options."""
        rc_mode = "constqp" if nvenc_settings.rc_mode == "cqp" else nvenc_settings.rc_mode
        args = ["-rc", rc_mode]

        if rc_mode == "constqp":
            args.extend(["-qp", str(crf_value)])
        elif rc_mode == "vbr":
            args.extend(["-cq", str(crf_value), "-b:v", "0"])

        b_adapt_enabled = "1" if nvenc_settings.b_adapt > 0 else "0"
        b_ref_mode = (
            "disabled"
            if nvenc_settings.b_adapt == 0
            else "each"
            if nvenc_settings.b_adapt == 1
            else "middle"
        )
        if include_b_frame_count:
            args.extend(["-bf", "4"])
        args.extend(["-b_adapt", b_adapt_enabled, "-b_ref_mode", b_ref_mode])

        aq_enabled = "1" if nvenc_settings.aq_strength > 0 else "0"
        args.extend(["-temporal-aq", aq_enabled, "-spatial-aq", aq_enabled])
        if nvenc_settings.aq_strength > 0:
            args.extend(["-aq-strength", str(nvenc_settings.aq_strength)])

        args.extend(
            [
                "-rc-lookahead",
                "32",
                "-dpb_size",
                str(nvenc_settings.ref_frames),
            ]
        )
        return args

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
                gpu_info = HARDWARE_PROBE.gpu_info()
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

        # Probe the first audio stream's codec name. None means the probe could
        # not run at all (timeout / ffprobe missing / non-zero exit) -> fall back
        # to default encoding rather than re-encoding a stream we couldn't read.
        audio_codec = run_ffprobe(
            [
                "-v",
                "quiet",
                "-show_entries",
                "stream=codec_name",
                "-select_streams",
                "a:0",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                path,
            ]
        )

        if audio_codec is None:
            # Probe failed entirely - fall back to default encoding.
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

        audio_codec = audio_codec.strip()

        # Copy AC-3/AAC audio to skip needless re-encode
        if audio_codec in ("aac", "ac3", "eac3"):
            args.extend(["-c:a", "copy"])
            message = f"Detected {audio_codec} audio - using passthrough"
        elif codec_idx == CodecIndex.PRORES:
            # Handle ProRes special case, otherwise AAC
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

        return args, message

    @staticmethod
    def get_encoder_configuration(
        codec_idx: int,
        thread_count: int,
        _is_parallel_enabled: bool,
        crf_value: int,
        hevc_10bit: bool = False,
        nvenc_settings: NvencSettings | None = None,
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
        nvenc_settings = nvenc_settings or NvencSettings()

        try:
            # Get cached or detect available encoders
            available_encoders = HARDWARE_PROBE.available_encoders()

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
                        *CodecArgBuilder._nvenc_quality_args(
                            crf_value,
                            nvenc_settings,
                            include_b_frame_count=True,
                        ),
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
                        *CodecArgBuilder._nvenc_quality_args(
                            crf_value,
                            nvenc_settings,
                            include_b_frame_count=True,
                        ),
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
                        *CodecArgBuilder._nvenc_quality_args(
                            crf_value,
                            nvenc_settings,
                            include_b_frame_count=False,
                        ),
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
