"""Output file size estimation for PyFFMPEG."""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import FileConfig
from domain.codec import codec_by_index

if TYPE_CHECKING:
    from metadata.probe import VideoMetadata


class SizeEstimator:
    """Pure (cache-free) output file size estimation."""

    @staticmethod
    def estimate_output_size(
        input_metadata: VideoMetadata, codec_idx: int, crf_value: int
    ) -> str | None:
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

        # Base size factor comes from the codec registry. ProRes carries a second
        # factor (4444) used above the high-CRF threshold; every other codec has a
        # single factor (size_factor_high_crf is None).
        codec = codec_by_index(codec_idx)
        if codec is None:
            base_factor = FileConfig.SIZE_FACTOR_DEFAULT
        elif codec.size_factor_high_crf is not None and crf_value > 20:
            base_factor = codec.size_factor_high_crf
        else:
            base_factor = codec.size_factor

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

        return SizeEstimator.format_file_size(estimated_mb * 1_000_000)

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
