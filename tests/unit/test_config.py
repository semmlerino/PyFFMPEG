"""Tests for config groupings derived from the codec registry.

These lock the registry-derived CodecIndex tuples to the exact values the
hardcoded tuples had before Phase 2, so downstream code that reads them is
unaffected.
"""

from pympeg.config import CodecIndex


class TestCodecIndexGroups:
    def test_gpu_encoders(self):
        # NVENC (0,1,2) + QSV (5) + VAAPI (6)
        assert CodecIndex.GPU_ENCODERS == (0, 1, 2, 5, 6)

    def test_cpu_encoders(self):
        assert CodecIndex.CPU_ENCODERS == (3, 4)

    def test_nvenc_encoders(self):
        assert CodecIndex.NVENC_ENCODERS == (0, 1, 2)

    def test_mkv_codecs(self):
        # Historically named MP4_CODECS; every non-ProRes codec.
        assert CodecIndex.MP4_CODECS == (0, 1, 2, 3, 5, 6)

    def test_mov_codecs(self):
        assert CodecIndex.MOV_CODECS == (4,)

    def test_gpu_and_cpu_partition_all_codecs(self):
        assert set(CodecIndex.GPU_ENCODERS) | set(CodecIndex.CPU_ENCODERS) == set(
            range(7)
        )

    def test_individual_constants_match_positions(self):
        assert CodecIndex.H264_NVENC == 0
        assert CodecIndex.HEVC_NVENC == 1
        assert CodecIndex.AV1_NVENC == 2
        assert CodecIndex.X264_CPU == 3
        assert CodecIndex.PRORES == 4
        assert CodecIndex.H264_QSV == 5
        assert CodecIndex.H264_VAAPI == 6
