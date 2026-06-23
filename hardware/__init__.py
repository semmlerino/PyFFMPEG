"""Hardware detection services for PyFFMPEG.

Owns GPU/encoder probing and its cache (HardwareProbe) plus the async Qt
adapter (GPUDetector). The single shared HardwareProbe instance (HARDWARE_PROBE)
is thread-safe so the background detection worker can update it safely.
"""
