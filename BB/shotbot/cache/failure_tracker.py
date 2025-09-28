"""Failure tracking with exponential backoff for cache operations."""

from __future__ import annotations

# Standard library imports
import logging
import threading
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Standard library imports
    from pathlib import Path

logger = logging.getLogger(__name__)


class FailureTracker:
    """Tracks failed cache operations and implements exponential backoff.

    This class manages failed thumbnail generation attempts, implementing
    exponential backoff to prevent repeated failures from overwhelming
    the system. Failed attempts are tracked per cache key with timestamps
    and automatic cleanup.
    """

    def __init__(
        self,
        base_retry_delay_minutes: int = 5,
        max_retry_delay_minutes: int = 120,
        retry_multiplier: int = 3,
        max_failed_attempts: int = 4,
        cleanup_age_hours: int = 24,
    ) -> None:
        """Initialize failure tracker with configurable parameters.

        Args:
            base_retry_delay_minutes: Initial delay in minutes (default: 5)
            max_retry_delay_minutes: Maximum delay in minutes (default: 120)
            retry_multiplier: Exponential backoff multiplier (default: 3)
            max_failed_attempts: Max attempts before using max delay (default: 4)
            cleanup_age_hours: Hours after which to clean old failures (default: 24)
        """
        self._failed_attempts: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

        # Configuration
        self._base_retry_delay_minutes = base_retry_delay_minutes
        self._max_retry_delay_minutes = max_retry_delay_minutes
        self._retry_multiplier = retry_multiplier
        self._max_failed_attempts = max_failed_attempts
        self._cleanup_age_hours = cleanup_age_hours

    def should_retry(
        self, cache_key: str, source_path: Path | None = None
    ) -> tuple[bool, str]:
        """Check if an operation should be retried for the given cache key.

        Args:
            cache_key: Unique identifier for the cache operation
            source_path: source path for better logging

        Returns:
            Tuple of (should_retry, reason_message)
            - should_retry: True if retry is allowed, False if should skip
            - reason_message: Explanation for the decision
        """
        with self._lock:
            if cache_key not in self._failed_attempts:
                return True, "No previous failures recorded"

            failure_info = self._failed_attempts[cache_key]
            next_retry = failure_info.get("next_retry")
            attempts = failure_info.get("attempts", 0)

            if next_retry and datetime.now() < next_retry:
                time_remaining = next_retry - datetime.now()
                minutes_remaining = int(time_remaining.total_seconds() / 60)

                source_name = source_path.name if source_path else cache_key
                reason = (
                    f"Skipping recently failed operation for {source_name} "
                    f"(attempt {attempts}, retry in {minutes_remaining}min)"
                )
                return False, reason

            return True, f"Retry allowed after {attempts} previous attempts"

    def record_failure(
        self, cache_key: str, error_message: str, source_path: Path | None = None
    ) -> None:
        """Record a failed operation with exponential backoff calculation.

        Args:
            cache_key: Unique identifier for the cache operation
            error_message: Error message from the failure
            source_path: source path for better logging
        """
        with self._lock:
            now = datetime.now()

            if cache_key in self._failed_attempts:
                # Increment existing failure count
                failure_info = self._failed_attempts[cache_key]
                attempts = failure_info.get("attempts", 0) + 1
            else:
                # First failure
                attempts = 1

            # Calculate next retry time with exponential backoff
            delay_minutes = self._calculate_retry_delay(attempts)
            next_retry = now + timedelta(minutes=delay_minutes)

            # Store failure information
            self._failed_attempts[cache_key] = {
                "timestamp": now,
                "attempts": attempts,
                "next_retry": next_retry,
                "error": error_message,
                "source_path": str(source_path) if source_path else cache_key,
            }

            source_name = source_path.name if source_path else cache_key
            logger.info(
                f"Recorded failed attempt #{attempts} for {source_name}, "
                + f"next retry in {delay_minutes:.2f}min ({next_retry.strftime('%H:%M:%S')})"
            )

            # Cleanup old failures periodically
            if len(self._failed_attempts) > 10:  # Arbitrary threshold
                self._cleanup_old_failures()

    def clear_failures(self, cache_key: str | None = None) -> None:
        """Clear failure records to allow immediate retry.

        Args:
            cache_key: Specific cache key to clear, or None to clear all failures
        """
        with self._lock:
            if cache_key:
                if cache_key in self._failed_attempts:
                    failure_info = self._failed_attempts.pop(cache_key)
                    source_path = failure_info.get("source_path", cache_key)
                    logger.info(f"Cleared failure record for {source_path}")
                else:
                    logger.debug(f"No failure record found for {cache_key}")
            else:
                count = len(self._failed_attempts)
                self._failed_attempts.clear()
                if count > 0:
                    logger.info(f"Cleared all {count} failure records")

    def get_failure_status(self) -> dict[str, dict[str, Any]]:
        """Get current status of all failed attempts for debugging.

        Returns:
            Dictionary mapping cache_key -> failure info
        """
        with self._lock:
            return dict(self._failed_attempts)

    def get_failure_count(self) -> int:
        """Get total number of tracked failures.

        Returns:
            Number of currently tracked failed operations
        """
        with self._lock:
            return len(self._failed_attempts)

    def cleanup_old_failures(self) -> int:
        """Manually trigger cleanup of old failure records.

        Returns:
            Number of failure records cleaned up
        """
        with self._lock:
            return self._cleanup_old_failures()

    def _calculate_retry_delay(self, attempts: int) -> float:
        """Calculate retry delay using exponential backoff.

        Args:
            attempts: Number of failed attempts

        Returns:
            Delay in minutes before next retry
        """
        if attempts >= self._max_failed_attempts:
            # Max attempts reached, use maximum delay
            return float(self._max_retry_delay_minutes)

        # Exponential backoff: 5min, 15min, 45min, 135min...
        delay_minutes = min(
            self._base_retry_delay_minutes * (self._retry_multiplier ** (attempts - 1)),
            self._max_retry_delay_minutes,
        )

        return delay_minutes

    def _cleanup_old_failures(self) -> int:
        """Clean up failure records older than the configured age.

        Returns:
            Number of records cleaned up
        """
        now = datetime.now()
        max_age = timedelta(hours=self._cleanup_age_hours)

        keys_to_remove = []
        for cache_key, failure_info in self._failed_attempts.items():
            timestamp = failure_info.get("timestamp", now)
            if now - timestamp > max_age:
                keys_to_remove.append(cache_key)

        for key in keys_to_remove:
            del self._failed_attempts[key]

        if keys_to_remove:
            logger.debug(f"Cleaned up {len(keys_to_remove)} old failure records")

        return len(keys_to_remove)

    def __len__(self) -> int:
        """Return number of tracked failures."""
        return self.get_failure_count()

    def __contains__(self, cache_key: str) -> bool:
        """Check if cache key has recorded failures."""
        with self._lock:
            return cache_key in self._failed_attempts

    def __repr__(self) -> str:
        """String representation of failure tracker."""
        count = self.get_failure_count()
        return f"FailureTracker(failures={count}, max_delay={self._max_retry_delay_minutes}min)"
