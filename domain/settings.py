"""Per-conversion settings value object (pure leaf)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversionSettings:
    """The 12 parameters ConversionController.start_conversion() consumes.

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

    @classmethod
    def from_settings_dict(
        cls, settings: dict[str, int | bool | str]
    ) -> ConversionSettings:
        """Build from SettingsPanel.get_current_settings().

        That dict carries extra keys (auto_balance, nvenc_*) that are not
        start_conversion parameters; they are ignored here.
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
        )
