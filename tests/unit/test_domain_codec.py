"""Unit tests for domain.codec — the single source of truth for codec facts.

The expected table is transcribed from the legacy index-driven plumbing:
- display names: SettingsPanel codec combo (settings_panel.py)
- encoder names + container: CodecHelpers arg builder / get_output_extension
- is_gpu / is_nvenc: CodecIndex.GPU_ENCODERS / NVENC_ENCODERS (config.py)
- size_factor: FileConfig.SIZE_FACTOR_* (config.py)
"""

import dataclasses

import pytest

from domain.codec import CODEC_REGISTRY, codec_by_index

# (index, display_name, encoder_name, container_ext, is_gpu, is_nvenc, size_factor)
EXPECTED = [
    (0, "H.264 NVENC", "h264_nvenc", ".mkv", True, True, 8),
    (1, "HEVC NVENC", "hevc_nvenc", ".mkv", True, True, 8),
    (2, "AV1 NVENC", "av1_nvenc", ".mkv", True, True, 6),
    (3, "x264 CPU", "libx264", ".mkv", False, False, 5),
    (4, "ProRes CPU", "prores_ks", ".mov", False, False, 50),
    (5, "H.264 QSV", "h264_qsv", ".mkv", True, False, 8),
    (6, "H.264 VAAPI", "h264_vaapi", ".mkv", True, False, 8),
]


class TestCodecRegistry:
    def test_registry_has_seven_codecs(self):
        assert len(CODEC_REGISTRY) == 7

    def test_index_equals_position(self):
        for position, codec in enumerate(CODEC_REGISTRY):
            assert codec.index == position

    @pytest.mark.parametrize("expected", EXPECTED)
    def test_codec_facts_match_legacy_mapping(self, expected):
        idx, display, encoder, ext, is_gpu, is_nvenc, size = expected
        codec = CODEC_REGISTRY[idx]
        assert codec.display_name == display
        assert codec.encoder_name == encoder
        assert codec.container_ext == ext
        assert codec.is_gpu is is_gpu
        assert codec.is_nvenc is is_nvenc
        assert codec.size_factor == size

    def test_every_nvenc_codec_is_gpu(self):
        for codec in CODEC_REGISTRY:
            if codec.is_nvenc:
                assert codec.is_gpu

    def test_only_prores_uses_mov(self):
        mov = [c for c in CODEC_REGISTRY if c.container_ext == ".mov"]
        assert [c.display_name for c in mov] == ["ProRes CPU"]

    def test_prores_has_high_crf_size_factor(self):
        # ProRes uses 4444 (80) above crf 20; 422 (50) at/below — see estimate_output_size.
        prores = CODEC_REGISTRY[4]
        assert prores.size_factor == 50
        assert prores.size_factor_high_crf == 80

    def test_only_prores_has_high_crf_size_factor(self):
        for codec in CODEC_REGISTRY:
            if codec.index != 4:
                assert codec.size_factor_high_crf is None

    def test_codec_is_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            CODEC_REGISTRY[0].index = 99  # type: ignore[misc]


class TestCodecByIndex:
    def test_valid_index_returns_codec(self):
        codec = codec_by_index(4)
        assert codec is not None
        assert codec.encoder_name == "prores_ks"

    def test_out_of_range_returns_none(self):
        assert codec_by_index(99) is None
        assert codec_by_index(-1) is None
