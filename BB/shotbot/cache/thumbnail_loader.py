"""Async thumbnail loading with QRunnable background processing."""

from __future__ import annotations

import logging
from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QMutex,
    QMutexLocker,
    QObject,
    QRunnable,
    QWaitCondition,
    Signal,
)

from runnable_tracker import get_tracker

# Import sip at module level to avoid threading issues
try:
    import sip
    SIP_AVAILABLE = True
except ImportError:
    SIP_AVAILABLE = False
    sip = None

if TYPE_CHECKING:
    from .failure_tracker import FailureTracker
    from .thumbnail_processor import ThumbnailProcessor

logger = logging.getLogger(__name__)


class ThumbnailCacheResult:
    """Result container for async thumbnail caching operations.

    This class provides thread-safe result handling for background
    thumbnail processing with synchronization support.
    """

    def __init__(self) -> None:
        """Initialize result container."""
        super().__init__()
        self.future: Future[Path | None] = Future()
        self.cache_path: Path | None = None
        self.error: str | None = None
        self._complete_condition = QWaitCondition()
        self._completed_mutex = QMutex()
        self._is_complete = False

    def set_result(self, cache_path: Path) -> None:
        """Set successful result (thread-safe, prevents multiple completions).

        Args:
            cache_path: Path to the cached thumbnail
        """
        with QMutexLocker(self._completed_mutex):
            if self._is_complete:
                return  # Already completed, ignore
            self._is_complete = True

        self.cache_path = cache_path
        try:
            self.future.set_result(cache_path)
        except Exception:
            pass  # Future already completed
        self._complete_condition.wakeAll()

    def set_error(self, error: str) -> None:
        """Set error result (thread-safe, prevents multiple completions).

        Args:
            error: Error message describing the failure
        """
        with QMutexLocker(self._completed_mutex):
            if self._is_complete:
                return  # Already completed, ignore
            self._is_complete = True

        self.error = error
        try:
            self.future.set_exception(Exception(error))
        except Exception:
            pass  # Future already completed
        self._complete_condition.wakeAll()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for completion.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if completed within timeout
        """
        self._completed_mutex.lock()
        try:
            if self._is_complete:
                return True
            # Convert seconds to milliseconds for Qt
            timeout_ms = int(timeout * 1000) if timeout is not None else -1
            result = self._complete_condition.wait(self._completed_mutex, timeout_ms)
            return result and self._is_complete
        finally:
            self._completed_mutex.unlock()

    def get_result(self, timeout: float | None = None) -> Path | None:
        """Get result with optional timeout.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            Cached path or None if failed/timeout
        """
        try:
            return self.future.result(timeout=timeout)
        except Exception:
            return None

    def is_complete(self) -> bool:
        """Check if the operation is complete.

        Returns:
            True if operation completed (success or failure)
        """
        with QMutexLocker(self._completed_mutex):
            return self._is_complete

    def __repr__(self) -> str:
        """String representation of result."""
        status = "complete" if self.is_complete() else "pending"
        if self.error:
            return f"ThumbnailCacheResult(status={status}, error='{self.error}')"
        elif self.cache_path:
            return f"ThumbnailCacheResult(status={status}, path={self.cache_path.name})"
        else:
            return f"ThumbnailCacheResult(status={status})"


class ThumbnailLoader(QRunnable):
    """Background thumbnail loader with result synchronization.

    This QRunnable worker processes thumbnails in background threads
    using ThumbnailProcessor and integrates with FailureTracker for
    retry management.
    """

    class Signals(QObject):
        """Signal definitions for thumbnail loading events."""

        loaded = Signal(str, str, str, Path)  # show, sequence, shot, cache_path
        failed = Signal(str, str, str, str)  # show, sequence, shot, error_msg

    def __init__(
        self,
        thumbnail_processor: ThumbnailProcessor,
        failure_tracker: FailureTracker,
        source_path: Path,
        cache_path: Path,
        show: str,
        sequence: str,
        shot: str,
        result: ThumbnailCacheResult | None = None,
    ) -> None:
        """Initialize thumbnail loader.

        Args:
            thumbnail_processor: Processor for image operations
            failure_tracker: Tracker for handling failures
            source_path: Path to source image file
            cache_path: Path where thumbnail should be cached
            show: Show name for organization
            sequence: Sequence name for organization
            shot: Shot name for identification
            result: result container for synchronization
        """
        super().__init__()
        self._thumbnail_processor = thumbnail_processor
        self._failure_tracker = failure_tracker
        self.source_path = source_path
        self.cache_path = cache_path
        self.show = show
        self.sequence = sequence
        self.shot = shot
        self.signals = self.Signals()
        self.result = result or ThumbnailCacheResult()
        self.setAutoDelete(True)

    def run(self) -> None:
        """Process the thumbnail in background with result synchronization."""
        tracker = get_tracker()
        metadata = {
            "type": "ThumbnailLoader",
            "shot": self.shot,
            "show": self.show,
            "sequence": self.sequence,
        }
        tracker.register(self, metadata)

        cache_key = f"{self.show}_{self.sequence}_{self.shot}"

        try:
            # Use the thumbnail processor to create the thumbnail
            success = self._thumbnail_processor.process_thumbnail(
                self.source_path, self.cache_path
            )

            if success and self.cache_path.exists():
                # Set successful result
                self.result.set_result(self.cache_path)

                # Emit success signal if still valid
                if hasattr(self, "signals") and self.signals:
                    try:
                        # Check if signal object still exists before emission
                        if SIP_AVAILABLE and sip is not None:
                            try:
                                if not sip.isdeleted(self.signals):
                                    self.signals.loaded.emit(
                                        self.show,
                                        self.sequence,
                                        self.shot,
                                        self.cache_path,
                                    )
                                else:
                                    logger.debug(
                                        "Signal object deleted, skipping loaded emission"
                                    )
                            except Exception:
                                pass  # Signal deleted or other error
                        else:
                            # Fallback if sip not available
                            try:
                                self.signals.loaded.emit(
                                    self.show,
                                    self.sequence,
                                    self.shot,
                                    self.cache_path,
                                )
                            except RuntimeError:
                                pass  # Signals deleted
                    except RuntimeError:
                        pass  # Signals deleted

                logger.debug(f"Successfully cached thumbnail for {self.shot}")
            else:
                # Set error result
                error_msg = f"Thumbnail processing failed for {self.shot}"
                self.result.set_error(error_msg)

                # Record the failed attempt for backoff
                self._failure_tracker.record_failure(
                    cache_key, error_msg, self.source_path
                )

                if hasattr(self, "signals") and self.signals:
                    try:
                        # Check if signal object still exists before emission
                        if SIP_AVAILABLE and sip is not None:
                            try:
                                if not sip.isdeleted(self.signals):
                                    self.signals.failed.emit(
                                        self.show,
                                        self.sequence,
                                        self.shot,
                                        error_msg,
                                    )
                                else:
                                    logger.debug(
                                        "Signal object deleted, skipping failed emission"
                                    )
                            except Exception:
                                pass  # Signal deleted or other error
                        else:
                            # Fallback if sip not available
                            try:
                                self.signals.failed.emit(
                                    self.show,
                                    self.sequence,
                                    self.shot,
                                    error_msg,
                                )
                            except RuntimeError:
                                pass  # Signals deleted
                    except RuntimeError:
                        pass  # Signals deleted

                logger.warning(error_msg)

        except Exception as e:
            # Set exception result
            error_msg = f"Exception while caching thumbnail for {self.shot}: {e}"
            self.result.set_error(str(e))

            # Record the failed attempt for backoff
            self._failure_tracker.record_failure(cache_key, error_msg, self.source_path)

            # Check if signals object still exists before emitting
            if hasattr(self, "signals") and self.signals:
                try:
                    # Check if signal object still exists before emission
                    if SIP_AVAILABLE and sip is not None:
                        try:
                            if not sip.isdeleted(self.signals):
                                self.signals.failed.emit(
                                    self.show,
                                    self.sequence,
                                    self.shot,
                                    str(e),
                                )
                            else:
                                logger.debug(
                                    "Signal object deleted, skipping exception emission"
                                )
                        except Exception:
                            pass  # Signal deleted or other error
                    else:
                        # Fallback if sip not available
                        self.signals.failed.emit(
                            self.show,
                            self.sequence,
                            self.shot,
                            str(e),
                        )
                except RuntimeError:
                    pass  # Signals deleted

            logger.error(error_msg)
        finally:
            # Always unregister from tracker when done
            tracker.unregister(self)

    def get_cache_key(self) -> str:
        """Get the cache key for this thumbnail.

        Returns:
            Unique cache key for this thumbnail
        """
        return f"{self.show}_{self.sequence}_{self.shot}"

    def __repr__(self) -> str:
        """String representation of thumbnail loader."""
        return f"ThumbnailLoader(shot={self.shot}, source={self.source_path.name})"
