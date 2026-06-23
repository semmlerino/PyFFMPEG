"""Unit tests for HardwareProbe TTL caching and detection (Phase 3b)."""

from unittest.mock import patch

from pympeg.hardware.probe import HardwareProbe, TtlCache


class TestTtlCache:
    def test_miss_returns_none(self):
        c: TtlCache[str] = TtlCache(300, 30)
        assert c.get_fresh(0.0) is None
        assert c.raw is None

    def test_fresh_success_within_ttl(self):
        c: TtlCache[str] = TtlCache(300, 30)
        c.set("x", now=100.0, success=True)
        assert c.get_fresh(now=399.0) == "x"  # 299s < 300 -> fresh
        assert c.get_fresh(now=401.0) is None  # 301s > 300 -> stale
        assert c.raw == "x"  # raw ignores freshness

    def test_failure_uses_short_ttl(self):
        c: TtlCache[str] = TtlCache(300, 30)
        c.set("", now=100.0, success=False)
        assert c.get_fresh(now=120.0) == ""  # 20s < 30 -> fresh failure
        assert c.get_fresh(now=140.0) is None  # 40s > 30 -> stale

    def test_clear(self):
        c: TtlCache[str] = TtlCache(300, 30)
        c.set("x", now=0.0, success=True)
        c.clear()
        assert c.raw is None


class TestHardwareProbe:
    def test_available_encoders_caches(self):
        probe = HardwareProbe()
        with patch(
            "pympeg.hardware.probe.subprocess.check_output",
            return_value="H264_NVENC\nlibx264\n",
        ) as mock:
            first = probe.available_encoders()
            second = probe.available_encoders()
        assert first == "h264_nvenc\nlibx264\n"  # lowercased
        assert second == first
        mock.assert_called_once()  # second call served from cache

    def test_available_encoders_failure_returns_empty(self):
        probe = HardwareProbe()
        with patch(
            "pympeg.hardware.probe.subprocess.check_output", side_effect=OSError
        ):
            assert probe.available_encoders() == ""

    def test_update_cache_populates_all(self):
        probe = HardwareProbe()
        probe.update_cache(
            has_gpu=True,
            gpu_name="NVIDIA GeForce RTX 4090",
            available_encoders="h264_nvenc",
        )
        assert probe.get_cached_encoder_info() == "h264_nvenc"
        assert probe.get_cached_gpu_info() == "NVIDIA GeForce RTX 4090"
        assert probe.is_rtx40_cached() is True
        assert probe.has_cached_info() is True

    def test_update_cache_no_gpu(self):
        probe = HardwareProbe()
        probe.update_cache(has_gpu=False, gpu_name="", available_encoders="")
        assert probe.is_rtx40_cached() is False
        assert probe.get_cached_gpu_info() == ""

    def test_is_rtx40_cached_none_before_detection(self):
        probe = HardwareProbe()
        assert probe.is_rtx40_cached() is None
        assert probe.has_cached_info() is False

    def test_detect_rtx40_from_gpu_info(self):
        probe = HardwareProbe()
        with patch(
            "pympeg.hardware.probe.subprocess.check_output",
            return_value=b"Product Name : NVIDIA GeForce RTX 4090",
        ):
            assert probe.detect_rtx40() is True

    def test_detect_rtx40_false_without_rtx40(self):
        probe = HardwareProbe()
        with patch(
            "pympeg.hardware.probe.subprocess.check_output",
            return_value=b"Product Name : NVIDIA GeForce GTX 1080",
        ):
            assert probe.detect_rtx40() is False

    def test_clear_resets(self):
        probe = HardwareProbe()
        probe.update_cache(has_gpu=True, gpu_name="RTX 4090", available_encoders="x")
        probe.clear()
        assert probe.is_rtx40_cached() is None
        assert probe.has_cached_info() is False
