#!/usr/bin/env python3
"""
Configuration Constants for PyFFMPEG
Centralizes all magic numbers and configuration values for better maintainability
"""

from typing import Final

from domain.codec import CODEC_REGISTRY


# Process Management Constants
class ProcessConfig:
    """Process and threading related constants"""

    # Maximum parallel processes for different system tiers
    MAX_PARALLEL_HIGH_END: Final[int] = (
        14  # For high-end systems (RTX 4090, etc.) - Optimized for i9-14900HX + RTX 4090
    )
    MAX_PARALLEL_DEFAULT: Final[int] = 4  # Default maximum parallel processes

    # GPU encoding limits
    MAX_GPU_SLOTS: Final[int] = (
        12  # RTX 4090 can handle up to 12 encodes (4 per NVENC engine) with 16GB VRAM
    )
    NVENC_ENGINES_PER_GPU: Final[int] = 3  # Number of NVENC engines per GPU

    # Thread management
    MIN_THREADS_PER_PROCESS: Final[int] = 2  # Minimum threads for any encoding process
    OPTIMAL_CPU_THREADS: Final[int] = (
        32  # Optimal thread count for CPU encoding on i9-14900HX (32 threads)
    )

    # Process timeout values (in seconds)
    SUBPROCESS_TIMEOUT: Final[int] = 30  # Timeout for subprocess calls
    PROCESS_START_TIMEOUT: Final[int] = 5  # Timeout for process startup
    PROCESS_KILL_TIMEOUT: Final[int] = 3  # Timeout when killing processes


# UI Update and Timer Constants
class UIConfig:
    """UI update timing and behavior constants"""

    # Timer intervals (in milliseconds)
    UI_UPDATE_DEFAULT: Final[int] = (
        400  # Default UI update interval - optimized for high-end system
    )
    UI_UPDATE_HIGH_ACTIVITY: Final[int] = (
        150  # Fast updates for high activity (4+ processes) - smoother on RTX 4090
    )
    UI_UPDATE_LOW_ACTIVITY: Final[int] = 1000  # Slow updates for low activity
    UI_UPDATE_FALLBACK: Final[int] = 1000  # Fallback timer interval for MainWindow

    # UI response delays
    WIDGET_REMOVAL_DELAY: Final[int] = (
        5000  # Delay before removing process widgets (ms)
    )
    STOPPED_WIDGET_DELAY: Final[int] = 3000  # Delay for stopped process widgets (ms)

    # Activity timing
    LOW_ACTIVITY_THRESHOLD: Final[int] = (
        5  # Seconds of inactivity before considering "low activity"
    )
    FORCE_UPDATE_INTERVAL: Final[int] = 3  # Force ETA update every N seconds


# Memory and Log Management Constants
class LogConfig:
    """Log size limits and memory management"""

    # Main application log limits
    MAIN_LOG_MAX_SIZE: Final[int] = (
        20000  # Maximum characters in main log - optimized for 32GB RAM
    )
    MAIN_LOG_TRUNCATE_LINES: Final[int] = 100  # Lines to keep when truncating main log

    # Process-specific log limits
    PROCESS_LOG_MAX_SIZE: Final[int] = (
        10000  # Maximum characters per process log - optimized for 32GB RAM
    )
    PROCESS_LOG_TRUNCATE_LINES: Final[int] = (
        50  # Lines to keep when truncating process logs
    )

    # Log history limits for ProcessManager
    MAX_LOG_HISTORY: Final[int] = (
        5000  # Maximum log entries to keep in memory - optimized for 32GB RAM
    )
    TRUNCATE_LOG_HISTORY: Final[int] = 2500  # Truncate to this many entries

    # Memory cleanup thresholds
    MAX_PROCESS_WIDGETS: Final[int] = (
        16  # Maximum concurrent process widgets - matches parallel capacity
    )
    MAX_LOG_TABS: Final[int] = (
        14  # Maximum process log tabs - optimized for high-end system
    )


# Encoding and Quality Constants
class EncodingConfig:
    """Video encoding quality and performance settings"""

    # Default quality settings
    DEFAULT_CRF_H264: Final[int] = (
        16  # Default CRF for H.264 - higher quality for powerful hardware
    )
    DEFAULT_CRF_FALLBACK: Final[int] = 23  # Fallback CRF value

    # Bitrate settings (in kbps)
    AUDIO_BITRATE_DEFAULT: Final[int] = (
        256  # Default audio bitrate - higher quality for powerful hardware
    )

    # Performance presets
    PRESET_FAST: Final[str] = "fast"  # Fast encoding preset
    PRESET_MEDIUM: Final[str] = "medium"  # Medium encoding preset
    PRESET_SLOW: Final[str] = "slow"  # Slow encoding preset

    # Auto-balance distribution ratios
    GPU_RATIO_DEFAULT: Final[float] = (
        0.85  # 85% of files to GPU for RTX 4090 (exceptional GPU power)
    )
    CPU_RATIO_DEFAULT: Final[float] = 0.15  # 15% of files to CPU by default


# Codec Index Constants (maps UI combo box indices to encoders)
class CodecIndex:
    """Codec indices matching UI combo box order.

    These constants eliminate magic numbers when checking codec types.
    The indices correspond to the order in the codec combo box in SettingsPanel.
    """

    # GPU encoders (NVENC)
    H264_NVENC: Final[int] = 0
    HEVC_NVENC: Final[int] = 1
    AV1_NVENC: Final[int] = 2

    # CPU encoders
    X264_CPU: Final[int] = 3
    PRORES: Final[int] = 4

    # Other hardware encoders
    H264_QSV: Final[int] = 5
    H264_VAAPI: Final[int] = 6

    # Grouped indices derived from CODEC_REGISTRY (the single source of truth).
    # The Final[int] public names are preserved so downstream code is untouched.
    # (MP4_CODECS keeps its historical name though the container is now .mkv.)
    GPU_ENCODERS: Final["tuple[int, ...]"] = tuple(
        c.index for c in CODEC_REGISTRY if c.is_gpu
    )
    CPU_ENCODERS: Final["tuple[int, ...]"] = tuple(
        c.index for c in CODEC_REGISTRY if not c.is_gpu
    )
    NVENC_ENCODERS: Final["tuple[int, ...]"] = tuple(
        c.index for c in CODEC_REGISTRY if c.is_nvenc
    )
    MP4_CODECS: Final["tuple[int, ...]"] = tuple(
        c.index for c in CODEC_REGISTRY if c.container_ext == ".mkv"
    )
    MOV_CODECS: Final["tuple[int, ...]"] = tuple(
        c.index for c in CODEC_REGISTRY if c.container_ext == ".mov"
    )


# Hardware Detection Constants
class HardwareConfig:
    """Hardware detection and capability constants"""

    # System capability thresholds
    HIGH_END_CPU_CORES: Final[int] = (
        24  # CPU cores to consider "high-end" - matches i9-14900HX
    )

    # RTX GPU models that support AV1 NVENC
    RTX40_MODELS: Final["tuple[str, ...]"] = (
        "RTX 40",
        "4090",
        "4080",
        "4070",
    )  # Tuple for immutability

    # Hardware acceleration timeout
    GPU_DETECTION_TIMEOUT: Final[int] = (
        2  # Seconds to wait for GPU detection (reduced to prevent UI freeze)
    )


# File and Path Constants
class FileConfig:
    """File handling and path constants"""

    # Supported file extensions
    SUPPORTED_VIDEO_EXTENSIONS: Final["tuple[str, ...]"] = (
        ".ts",
        ".mp4",
        ".m4v",
        ".mov",
    )  # Tuple for immutability

    # Output file suffix
    OUTPUT_SUFFIX: Final[str] = "_RC"  # Suffix added to converted files

    # File size estimation factors (MB per minute)
    SIZE_FACTOR_H264: Final[int] = 8  # H.264 estimated size
    SIZE_FACTOR_HEVC: Final[int] = 8  # HEVC estimated size
    SIZE_FACTOR_AV1: Final[int] = 6  # AV1 estimated size
    SIZE_FACTOR_X264: Final[int] = 5  # x264 estimated size
    SIZE_FACTOR_PRORES_422: Final[int] = 50  # ProRes 422 estimated size
    SIZE_FACTOR_PRORES_4444: Final[int] = 80  # ProRes 4444 estimated size
    SIZE_FACTOR_DEFAULT: Final[int] = 10  # Default fallback size factor


# Pre-flight Validation Constants
class ValidationConfig:
    """Pre-flight validation and safety check constants"""

    # Disk space validation
    DISK_SPACE_SAFETY_MARGIN: Final[float] = (
        0.8  # Require 20% extra free space beyond estimate
    )
    MIN_FREE_SPACE_BYTES: Final[int] = (
        100 * 1024 * 1024
    )  # Minimum 100MB free space required

    # Output integrity verification
    FFPROBE_VERIFY_TIMEOUT: Final[int] = 10  # Seconds to wait for ffprobe verification
    MIN_OUTPUT_SIZE_BYTES: Final[int] = 1024  # Minimum 1KB output to consider valid
    MIN_OUTPUT_SIZE_RATIO: Final[float] = 0.01  # Minimum 1% of input size


# Application Settings
class AppConfig:
    """Application-wide configuration"""

    # Application metadata
    APP_NAME: Final[str] = "PyFFMPEG Video Converter"
    APP_VERSION: Final[str] = "2.1"
    APP_DESCRIPTION: Final[str] = "RTX Advanced Hybrid Encoding"

    # Window settings
    DEFAULT_WINDOW_WIDTH: Final[int] = 1000
    DEFAULT_WINDOW_HEIGHT: Final[int] = 700

    # Settings keys for QSettings
    SETTINGS_ORG: Final[str] = "MyCompany"
    SETTINGS_APP: Final[str] = "TsConverterGuiSeq"
