"""Async GPU and encoder detection via Qt background threads.

Wraps the blocking subprocess probes in a QRunnable worker so the main
thread stays responsive during first-use detection. Results are written into
HARDWARE_PROBE and re-emitted as a Qt signal for UI handlers.
"""

from __future__ import annotations

import subprocess
from typing import ClassVar, override

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from pympeg.config import HardwareConfig, ProcessConfig
from pympeg.hardware.probe import HARDWARE_PROBE


class GPUDetectionSignals(QObject):
    """Signals for GPU detection worker."""

    detection_complete: ClassVar[Signal] = Signal(bool, str, str)


class GPUDetectionWorker(QRunnable):
    """Worker to detect GPU and available encoders in a background thread.

    Prevents UI freezes when probing nvidia-smi and ffmpeg encoders on first use.
    """

    def __init__(self, signals: GPUDetectionSignals):
        super().__init__()
        self.signals: GPUDetectionSignals = signals

    @override
    def run(self) -> None:
        """Probe GPU and encoders, then emit result."""
        gpu_name = ""
        has_gpu = False
        available_encoders = ""

        # Detect GPU via nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=HardwareConfig.GPU_DETECTION_TIMEOUT,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_name = result.stdout.strip().split("\n")[0]
                has_gpu = True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        # Detect available encoders via ffmpeg
        try:
            result = subprocess.run(
                ["ffmpeg", "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=ProcessConfig.SUBPROCESS_TIMEOUT,
                check=False,
            )
            if result.returncode == 0:
                available_encoders = result.stdout.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        self.signals.detection_complete.emit(has_gpu, gpu_name, available_encoders)


class GPUDetector(QObject):
    """Async GPU and encoder detection to prevent UI freezes.

    Usage:
        detector = GPUDetector(parent)
        detector.gpu_detected.connect(on_gpu_detected)
        detector.detect_async()

        def on_gpu_detected(has_gpu, gpu_name, encoders):
            # HARDWARE_PROBE cache is already updated by GPUDetector
    """

    # Signal emitted when detection completes
    gpu_detected: ClassVar[Signal] = Signal(
        bool, str, str
    )  # has_gpu, gpu_name, available_encoders

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._detection_signals: GPUDetectionSignals | None = None

    def detect_async(self) -> None:
        """Start async GPU detection.

        If cache already exists, emits signal immediately.
        Otherwise runs detection in background thread.
        """
        # Check if already cached using public accessor
        if HARDWARE_PROBE.has_cached_info():
            # Emit cached results using public accessors
            cached_gpu_info = HARDWARE_PROBE.get_cached_gpu_info()
            has_gpu = bool(cached_gpu_info)
            gpu_name = ""
            if has_gpu and cached_gpu_info:
                # Try to extract GPU name from cached info
                for model in HardwareConfig.RTX40_MODELS:
                    if model in cached_gpu_info:
                        gpu_name = model
                        break
            self.gpu_detected.emit(
                has_gpu, gpu_name, HARDWARE_PROBE.get_cached_encoder_info() or ""
            )
            return

        # Run detection in background
        self._detection_signals = GPUDetectionSignals()
        _ = self._detection_signals.detection_complete.connect(
            self._on_detection_complete
        )
        worker = GPUDetectionWorker(self._detection_signals)
        QThreadPool.globalInstance().start(worker)

    def _on_detection_complete(
        self, has_gpu: bool, gpu_name: str, available_encoders: str
    ) -> None:
        """Handle detection result and update cache."""
        # Update HARDWARE_PROBE cache
        HARDWARE_PROBE.update_cache(has_gpu, gpu_name, available_encoders)
        # Emit signal for UI handling
        self.gpu_detected.emit(has_gpu, gpu_name, available_encoders)
