"""Single source of truth for codec facts.

Pure leaf: values are *copied* from config.py / settings_panel.py /
codec_helpers.py rather than imported, so the domain layer depends on nothing.

GPU encoders (NVENC/QSV/VAAPI) are availability-gated at encode time and fall
back to libx264 when their encoder is missing; CPU encoders (libx264, prores_ks)
are unconditional. That gating lives in the Phase 3 arg builder; this module
only records the facts (`is_gpu` marks the encoders that require a probe).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Codec:
    """Immutable facts about a single output codec, ordered by UI combo index."""

    index: int
    display_name: str
    encoder_name: str
    container_ext: str
    is_gpu: bool
    is_nvenc: bool
    size_factor: int  # rough MB-per-minute estimate for size projection
    # Alternate MB/min factor for ProRes above the high-CRF threshold (crf > 20):
    # 422 (size_factor) at/below, 4444 above. None for every other codec.
    size_factor_high_crf: int | None = None


# index, display_name, encoder_name, container_ext, is_gpu, is_nvenc, size_factor
CODEC_REGISTRY: tuple[Codec, ...] = (
    Codec(0, "H.264 NVENC", "h264_nvenc", ".mkv", True, True, 8),
    Codec(1, "HEVC NVENC", "hevc_nvenc", ".mkv", True, True, 8),
    Codec(2, "AV1 NVENC", "av1_nvenc", ".mkv", True, True, 6),
    Codec(3, "x264 CPU", "libx264", ".mkv", False, False, 5),
    Codec(
        4, "ProRes CPU", "prores_ks", ".mov", False, False, 50, size_factor_high_crf=80
    ),
    Codec(5, "H.264 QSV", "h264_qsv", ".mkv", True, False, 8),
    Codec(6, "H.264 VAAPI", "h264_vaapi", ".mkv", True, False, 8),
)


def codec_by_index(index: int) -> Codec | None:
    """Return the codec at the given UI combo index, or None if out of range."""
    if 0 <= index < len(CODEC_REGISTRY):
        return CODEC_REGISTRY[index]
    return None
