"""Thread-safe hardware/encoder probing with TTL caching.

Replaces the class-level cache state that lived on CodecHelpers. A single shared
instance (HARDWARE_PROBE) is owned by the app and used by the controller, the
settings panel, and the GPUDetector background worker; an RLock makes the
worker's cache write safe against concurrent reads.
"""

from __future__ import annotations

import subprocess
import time
from threading import RLock

from config import HardwareConfig, ProcessConfig

# Cache TTLs (seconds): success is long (hardware rarely changes); failure is
# short so a transient probe error retries soon.
_CACHE_TTL_SUCCESS: float = 300.0
_CACHE_TTL_FAILURE: float = 30.0


class TtlCache[T]:
    """A single cached value with success/failure TTLs.

    Collapses the three duplicated cache-with-timestamp blocks that the old
    CodecHelpers had (encoder, gpu-info, rtx40) into one helper. Not internally
    locked; HardwareProbe serializes all access via its own RLock.
    """

    def __init__(self, ttl_success: float, ttl_failure: float) -> None:
        self._ttl_success: float = ttl_success
        self._ttl_failure: float = ttl_failure
        self._value: T | None = None
        self._timestamp: float = 0.0
        self._success: bool = False

    def get_fresh(self, now: float) -> T | None:
        """Return the cached value if still within its TTL, else None.

        A cached failure (e.g. "" set with success=False) is returned while
        fresh, matching the legacy behavior of caching empty results briefly.
        """
        if self._value is None:
            return None
        ttl = self._ttl_success if self._success else self._ttl_failure
        if (now - self._timestamp) < ttl:
            return self._value
        return None

    def set(self, value: T, now: float, *, success: bool) -> None:
        self._value = value
        self._timestamp = now
        self._success = success

    @property
    def raw(self) -> T | None:
        """The cached value regardless of freshness (None if never set)."""
        return self._value

    def clear(self) -> None:
        self._value = None
        self._timestamp = 0.0
        self._success = False


class HardwareProbe:
    """Detects available encoders and GPU info, caching expensive subprocess calls.

    All public methods are safe to call from any thread.
    """

    def __init__(
        self,
        ttl_success: float = _CACHE_TTL_SUCCESS,
        ttl_failure: float = _CACHE_TTL_FAILURE,
    ) -> None:
        self._lock: RLock = RLock()
        self._encoder: TtlCache[str] = TtlCache(ttl_success, ttl_failure)
        self._gpu_info: TtlCache[str] = TtlCache(ttl_success, ttl_failure)
        # rtx40 inherits the GPU-info TTL and is only ever a "success" entry.
        self._rtx40: TtlCache[bool] = TtlCache(ttl_success, ttl_success)

    def available_encoders(self) -> str:
        """Lowercased `ffmpeg -encoders` output, TTL-cached."""
        with self._lock:
            now = time.time()
            cached = self._encoder.get_fresh(now)
            if cached is not None:
                return cached
            try:
                output = subprocess.check_output(
                    ["ffmpeg", "-encoders"],
                    text=True,
                    stderr=subprocess.STDOUT,
                    timeout=ProcessConfig.SUBPROCESS_TIMEOUT,
                )
                value = output.lower()
                self._encoder.set(value, now, success=True)
                return value
            except (
                subprocess.TimeoutExpired,
                subprocess.CalledProcessError,
                OSError,
            ):
                self._encoder.set("", now, success=False)
                return ""

    def gpu_info(self) -> str:
        """`nvidia-smi -q` output, TTL-cached."""
        with self._lock:
            now = time.time()
            cached = self._gpu_info.get_fresh(now)
            if cached is not None:
                return cached
            try:
                info = subprocess.check_output(
                    ["nvidia-smi", "-q"],
                    timeout=HardwareConfig.GPU_DETECTION_TIMEOUT,
                ).decode("utf-8")
                self._gpu_info.set(info, now, success=True)
                return info
            except (
                subprocess.TimeoutExpired,
                subprocess.CalledProcessError,
                OSError,
            ):
                self._gpu_info.set("", now, success=False)
                return ""

    def detect_rtx40(self) -> bool:
        """Whether an RTX 40-series GPU is present (for AV1 NVENC), TTL-cached."""
        with self._lock:
            now = time.time()
            cached = self._rtx40.get_fresh(now)
            if cached is not None:
                return cached
            try:
                info = self.gpu_info()
                has_rtx40 = any(model in info for model in HardwareConfig.RTX40_MODELS)
                self._rtx40.set(has_rtx40, now, success=True)
                return has_rtx40
            except Exception:
                self._rtx40.set(False, now, success=True)
                return False

    def is_rtx40_cached(self) -> bool | None:
        """Cached RTX40 result, or None if detection has not run (non-blocking)."""
        with self._lock:
            return self._rtx40.raw

    def has_cached_info(self) -> bool:
        """Whether any GPU or encoder info has been cached yet."""
        with self._lock:
            return self._gpu_info.raw is not None or self._encoder.raw is not None

    def get_cached_gpu_info(self) -> str | None:
        with self._lock:
            return self._gpu_info.raw

    def get_cached_encoder_info(self) -> str | None:
        with self._lock:
            return self._encoder.raw

    def update_cache(
        self, has_gpu: bool, gpu_name: str, available_encoders: str
    ) -> None:
        """Populate caches from async detection results (called by GPUDetector)."""
        with self._lock:
            now = time.time()
            if available_encoders:
                self._encoder.set(available_encoders, now, success=True)
            else:
                self._encoder.set("", now, success=False)

            if has_gpu and gpu_name:
                self._gpu_info.set(gpu_name, now, success=True)
                is_rtx40 = any(
                    model in gpu_name for model in HardwareConfig.RTX40_MODELS
                )
                self._rtx40.set(is_rtx40, now, success=True)
            else:
                self._gpu_info.set("", now, success=False)
                self._rtx40.set(False, now, success=True)

    def clear(self) -> None:
        """Clear all cached detection results (useful for tests / system changes)."""
        with self._lock:
            self._encoder.clear()
            self._gpu_info.clear()
            self._rtx40.clear()


# Single shared instance owned by the application.
HARDWARE_PROBE = HardwareProbe()
