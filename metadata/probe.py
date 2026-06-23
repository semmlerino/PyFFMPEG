"""Video metadata extraction using ffprobe."""

from __future__ import annotations

import contextlib
import json
import subprocess
from typing import TypedDict

from config import ProcessConfig


class VideoMetadata(TypedDict):
    """Type definition for video metadata extracted from ffprobe."""

    duration: str
    duration_seconds: float
    width: int
    height: int
    codec: str
    bitrate: str
    bitrate_bps: int | None
    format_name: str


class MetadataProbe:
    """Pure (cache-free) video metadata extraction via ffprobe."""

    @staticmethod
    def extract_video_metadata(file_path: str) -> VideoMetadata | None:
        """Extract video metadata using ffprobe

        Returns:
            Dict with keys: duration, width, height, codec, bitrate, format_name
            None if extraction fails
        """
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]

            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=ProcessConfig.SUBPROCESS_TIMEOUT,
            )

            if result.returncode != 0:
                return None

            # Parse JSON with type safety
            # json.loads returns object, validate structure with isinstance
            # Note: Type checker cannot infer dict structure from json.loads,
            # so we suppress type warnings after runtime validation
            data_obj: object = json.loads(result.stdout)  # pyright: ignore[reportAny]
            if not isinstance(data_obj, dict):
                return None

            # Find video stream
            streams_obj = data_obj.get("streams")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            if not isinstance(streams_obj, list):
                return None

            video_stream_obj: object | None = None
            for stream_obj in streams_obj:  # pyright: ignore[reportUnknownVariableType]
                if (
                    isinstance(stream_obj, dict)
                    and stream_obj.get("codec_type") == "video"
                ):  # pyright: ignore[reportUnknownMemberType]
                    video_stream_obj = stream_obj  # pyright: ignore[reportUnknownVariableType]
                    break

            if not isinstance(video_stream_obj, dict):
                return None

            # Extract format info
            format_info_obj = data_obj.get("format")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            if not isinstance(format_info_obj, dict):
                return None

            # Parse duration
            duration_obj = format_info_obj.get("duration", "0")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            duration_str = str(duration_obj) if duration_obj is not None else "0"  # pyright: ignore[reportUnknownArgumentType]
            try:
                duration_seconds = float(duration_str)
                duration_formatted = MetadataProbe._format_duration(duration_seconds)
            except (ValueError, TypeError):
                duration_formatted = "Unknown"
                duration_seconds = 0.0

            # Extract video properties with type safety
            width_obj = video_stream_obj.get("width", 0)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            width = int(width_obj) if isinstance(width_obj, (int, float)) else 0

            height_obj = video_stream_obj.get("height", 0)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            height = int(height_obj) if isinstance(height_obj, (int, float)) else 0

            codec_name_obj = video_stream_obj.get("codec_name", "Unknown")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            codec_name = (
                str(codec_name_obj) if codec_name_obj is not None else "Unknown"
            )  # pyright: ignore[reportUnknownArgumentType]

            # Calculate bitrate with type safety
            bitrate_bps: int | None = None
            if "bit_rate" in video_stream_obj:
                bitrate_obj = video_stream_obj["bit_rate"]  # pyright: ignore[reportUnknownVariableType]
                if isinstance(bitrate_obj, (int, str)):
                    with contextlib.suppress(ValueError, TypeError):
                        bitrate_bps = int(bitrate_obj)

            if not bitrate_bps and "bit_rate" in format_info_obj:
                bitrate_obj = format_info_obj["bit_rate"]  # pyright: ignore[reportUnknownVariableType]
                if isinstance(bitrate_obj, (int, str)):
                    with contextlib.suppress(ValueError, TypeError):
                        bitrate_bps = int(bitrate_obj)

            bitrate_formatted = (
                MetadataProbe._format_bitrate(bitrate_bps) if bitrate_bps else "Unknown"
            )

            # Extract format name with type safety
            format_name_obj = format_info_obj.get("format_name", "Unknown")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            format_name = (
                str(format_name_obj) if format_name_obj is not None else "Unknown"
            )  # pyright: ignore[reportUnknownArgumentType]

            return VideoMetadata(
                duration=duration_formatted,
                duration_seconds=duration_seconds,
                width=width,
                height=height,
                codec=codec_name.upper(),
                bitrate=bitrate_formatted,
                bitrate_bps=bitrate_bps,
                format_name=format_name,
            )

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
            OSError,
            Exception,
        ):
            return None

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration from seconds to HH:MM:SS"""
        if seconds <= 0:
            return "00:00:00"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _format_bitrate(bitrate_bps: int | None) -> str:
        """Format bitrate from bits per second to human readable"""
        if not bitrate_bps or bitrate_bps <= 0:
            return "Unknown"

        # Convert to Mbps
        mbps = bitrate_bps / 1_000_000

        if mbps >= 1000:
            return f"{mbps / 1000:.1f} Gbps"
        if mbps >= 1:
            return f"{mbps:.1f} Mbps"
        # Convert to Kbps
        kbps = bitrate_bps / 1000
        return f"{kbps:.0f} Kbps"
