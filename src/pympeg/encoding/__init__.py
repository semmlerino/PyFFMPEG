"""FFmpeg argument builders for PyFFMPEG.

Owns codec-specific CLI flag construction (CodecArgBuilder) without coupling to
hardware detection; probe results are fetched from hardware.probe.HARDWARE_PROBE.
"""
