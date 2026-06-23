"""Per-conversion settings value object (pure leaf)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NvencSettings:
    """Advanced NVENC encoder settings emitted by SettingsPanel."""

    b_adapt: int = 2
    ref_frames: int = 4
    rc_mode: str = "vbr"
    aq_strength: int = 8

    @classmethod
    def from_settings_dict(cls, settings: dict[str, int | bool | str]) -> NvencSettings:
        rc_mode = str(settings.get("nvenc_rc_mode", "vbr"))
        if rc_mode not in {"vbr", "cbr", "cqp"}:
            rc_mode = "vbr"

        return cls(
            b_adapt=max(0, min(int(settings.get("nvenc_b_adapt", 2)), 2)),
            ref_frames=max(1, min(int(settings.get("nvenc_ref_frames", 4)), 16)),
            rc_mode=rc_mode,
            aq_strength=max(0, min(int(settings.get("nvenc_aq_strength", 8)), 15)),
        )


@dataclass(frozen=True)
class ConversionSettings:
    """The typed conversion settings consumed by ConversionController.

    Optional fields keep the legacy defaults from the start_conversion signature.
    """

    codec_idx: int
    hwdecode_idx: int
    crf_value: int
    parallel_enabled: bool
    max_parallel: int
    delete_source: bool
    overwrite_mode: bool
    preset_idx: int = 0
    hevc_10bit: bool = False
    threads: int = 0
    priority_idx: int = 1
    smart_buffer: bool = True
    nvenc_settings: NvencSettings = field(default_factory=NvencSettings)

    @classmethod
    def from_settings_dict(
        cls, settings: dict[str, int | bool | str]
    ) -> ConversionSettings:
        """Build from SettingsPanel.get_current_settings().

        That dict carries extra keys (auto_balance) that are not conversion
        settings; they are ignored here.
        """
        return cls(
            codec_idx=int(settings["codec_idx"]),
            hwdecode_idx=int(settings["hwdecode_idx"]),
            crf_value=int(settings["crf_value"]),
            parallel_enabled=bool(settings["parallel_enabled"]),
            max_parallel=int(settings["max_parallel"]),
            delete_source=bool(settings["delete_source"]),
            overwrite_mode=bool(settings["overwrite_mode"]),
            preset_idx=int(settings["preset_idx"]),
            hevc_10bit=bool(settings["hevc_10bit"]),
            threads=int(settings["threads"]),
            priority_idx=int(settings["priority_idx"]),
            smart_buffer=bool(settings["smart_buffer"]),
            nvenc_settings=NvencSettings.from_settings_dict(settings),
        )
