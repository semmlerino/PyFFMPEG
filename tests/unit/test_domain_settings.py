"""Unit tests for domain.settings.ConversionSettings.

ConversionSettings captures the 12 per-conversion parameters that
ConversionController.start_conversion() takes today, and bridges the 17-key
dict returned by SettingsPanel.get_current_settings() via from_settings_dict().
"""

import dataclasses

import pytest

from pympeg.domain.settings import ConversionSettings


def _full_settings_dict() -> dict[str, int | bool | str]:
    """Mirror SettingsPanel.get_current_settings() — 17 keys, extras included."""
    return {
        "codec_idx": 2,
        "preset_idx": 1,
        "hwdecode_idx": 3,
        "crf_value": 18,
        "threads": 8,
        "parallel_enabled": True,
        "max_parallel": 6,
        "delete_source": True,
        "overwrite_mode": False,
        "smart_buffer": False,
        "auto_balance": True,
        "priority_idx": 2,
        "hevc_10bit": True,
        "nvenc_b_adapt": True,
        "nvenc_ref_frames": 3,
        "nvenc_rc_mode": "vbr",
        "nvenc_aq_strength": 8,
    }


class TestFromSettingsDict:
    def test_maps_all_twelve_controller_params(self):
        s = ConversionSettings.from_settings_dict(_full_settings_dict())
        assert s.codec_idx == 2
        assert s.hwdecode_idx == 3
        assert s.crf_value == 18
        assert s.parallel_enabled is True
        assert s.max_parallel == 6
        assert s.delete_source is True
        assert s.overwrite_mode is False
        assert s.preset_idx == 1
        assert s.hevc_10bit is True
        assert s.threads == 8
        assert s.priority_idx == 2
        assert s.smart_buffer is False

    def test_only_twelve_controller_fields(self):
        # auto_balance + nvenc_* live on the panel but are not start_conversion params.
        names = {f.name for f in dataclasses.fields(ConversionSettings)}
        assert names == {
            "codec_idx",
            "hwdecode_idx",
            "crf_value",
            "parallel_enabled",
            "max_parallel",
            "delete_source",
            "overwrite_mode",
            "preset_idx",
            "hevc_10bit",
            "threads",
            "priority_idx",
            "smart_buffer",
        }


class TestConversionSettingsDefaults:
    def test_optional_fields_have_legacy_defaults(self):
        s = ConversionSettings(
            codec_idx=0,
            hwdecode_idx=0,
            crf_value=16,
            parallel_enabled=False,
            max_parallel=4,
            delete_source=False,
            overwrite_mode=False,
        )
        assert s.preset_idx == 0
        assert s.hevc_10bit is False
        assert s.threads == 0
        assert s.priority_idx == 1
        assert s.smart_buffer is True

    def test_is_frozen(self):
        s = ConversionSettings(
            codec_idx=0,
            hwdecode_idx=0,
            crf_value=16,
            parallel_enabled=False,
            max_parallel=4,
            delete_source=False,
            overwrite_mode=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.crf_value = 23  # type: ignore[misc]
