"""Test doubles for Previous Shots feature following UNIFIED_TESTING_GUIDE.

This module provides lightweight test doubles that follow the guide's principles:
- Real signals where needed (Qt objects)
- SignalDouble pattern for non-Qt doubles
- Predictable behavior over mocks
- Thread-safe operations
"""

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from shot_model import Shot

# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)


class FakeSignal:
    """Lightweight signal test double from UNIFIED_TESTING_GUIDE."""

    def __init__(self):
        self.emissions = []
        self.callbacks = []

    def emit(self, *args):
        self.emissions.append(args)
        for callback in self.callbacks:
            callback(*args)

    def connect(self, callback):
        self.callbacks.append(callback)

    def disconnect(self, callback=None):
        if callback:
            if callback in self.callbacks:
                self.callbacks.remove(callback)
        else:
            self.callbacks.clear()

    @property
    def was_emitted(self):
        return len(self.emissions) > 0

    @property
    def emit_count(self):
        return len(self.emissions)

    def last_emission(self):
        return self.emissions[-1] if self.emissions else None


class FakeShotModel(QObject):
    """Test double for ShotModel with real Qt signals and predictable behavior."""

    # Real Qt signals
    shots_updated = Signal()
    refresh_started = Signal()
    refresh_finished = Signal()

    def __init__(self, initial_shots=None):
        super().__init__()
        self.shots = initial_shots or []
        self.refresh_calls = []
        self.get_shots_calls = 0

    def get_shots(self) -> List[Shot]:
        """Return configured shots."""
        self.get_shots_calls += 1
        return self.shots.copy()

    def set_shots(self, shots: List[Shot]):
        """Configure shots for testing."""
        self.shots = shots
        self.shots_updated.emit()

    def refresh_shots(self):
        """Record refresh call."""
        self.refresh_calls.append(True)
        self.refresh_started.emit()
        # Simulate async completion
        self.refresh_finished.emit()
        return True


class FakePreviousShotsFinder:
    """Test double for PreviousShotsFinder with predictable behavior."""

    def __init__(self, username="testuser"):
        self.username = username
        self.user_path_pattern = f"/user/{username}"

        # Track method calls
        self.find_user_shots_calls = []
        self.find_approved_shots_calls = []
        self.filter_approved_shots_calls = []
        self.get_shot_details_calls = []

        # Configurable return values
        self.user_shots_to_return = []
        self.approved_shots_to_return = []
        self.shot_details_to_return = {}

    def find_user_shots(self, shows_root: Path = Path("/shows")) -> List[Shot]:
        """Record call and return configured shots."""
        self.find_user_shots_calls.append(shows_root)
        return self.user_shots_to_return.copy()

    def filter_approved_shots(
        self, all_user_shots: List[Shot], active_shots: List[Shot]
    ) -> List[Shot]:
        """Record call and return configured shots."""
        self.filter_approved_shots_calls.append((all_user_shots, active_shots))

        # Simulate real filtering behavior
        if self.approved_shots_to_return:
            return self.approved_shots_to_return.copy()

        # Default: filter out active shots
        active_ids = {(s.show, s.sequence, s.shot) for s in active_shots}
        return [
            s for s in all_user_shots if (s.show, s.sequence, s.shot) not in active_ids
        ]

    def find_approved_shots(
        self, active_shots: List[Shot], shows_root: Path = Path("/shows")
    ) -> List[Shot]:
        """Record call and return configured shots."""
        self.find_approved_shots_calls.append((active_shots, shows_root))

        if self.approved_shots_to_return:
            return self.approved_shots_to_return.copy()

        # Simulate real behavior
        user_shots = self.find_user_shots(shows_root)
        return self.filter_approved_shots(user_shots, active_shots)

    def get_shot_details(self, shot: Shot) -> Dict[str, Any]:
        """Record call and return configured details."""
        self.get_shot_details_calls.append(shot)

        # Use shot ID as key instead of object (Shot is unhashable)
        shot_id = (shot.show, shot.sequence, shot.shot)
        if shot_id in self.shot_details_to_return:
            return self.shot_details_to_return[shot_id]

        # Default details
        return {
            "show": shot.show,
            "sequence": shot.sequence,
            "shot": shot.shot,
            "workspace_path": shot.workspace_path,
            "user_path": f"{shot.workspace_path}{self.user_path_pattern}",
            "status": "approved",
            "user_dir_exists": "True",
        }


class FakeCacheManager(QObject):
    """Test double for CacheManager with real signals and memory tracking."""

    # Real Qt signal for compatibility
    cache_updated = Signal()

    def __init__(self, cache_dir=None):
        super().__init__()
        self.cache_dir = cache_dir

        # In-memory storage
        self._cache_data = {}
        self._previous_shots_cache = None

        # Track method calls
        self.get_cached_previous_shots_calls = 0
        self.cache_previous_shots_calls = []
        self.clear_cached_data_calls = []

    def get_cached_previous_shots(self) -> Optional[List[Dict[str, Any]]]:
        """Return cached previous shots."""
        self.get_cached_previous_shots_calls += 1
        return self._previous_shots_cache

    def cache_previous_shots(self, shots: List[Dict[str, Any]]) -> None:
        """Cache previous shots data."""
        self.cache_previous_shots_calls.append(shots)
        self._previous_shots_cache = shots
        self.cache_updated.emit()

    def clear_cached_data(self, key: str) -> None:
        """Clear cached data by key."""
        self.clear_cached_data_calls.append(key)
        if key == "previous_shots":
            self._previous_shots_cache = None
        elif key in self._cache_data:
            del self._cache_data[key]

    def get_cached_thumbnail(
        self, source_path: str, show: str = "", sequence: str = "", shot: str = ""
    ) -> Optional[str]:
        """Return cached thumbnail path (fake implementation)."""
        # Return None to simulate no cached thumbnail exists
        return None

    def cache_thumbnail(
        self, source_path: str, show: str = "", sequence: str = "", shot: str = ""
    ) -> Optional[str]:
        """Cache a thumbnail (fake implementation)."""
        # Return a fake cache path
        cache_key = f"{show}_{sequence}_{shot}"
        self._cache_data[cache_key] = f"/fake/cache/{cache_key}.jpg"
        return self._cache_data[cache_key]


class FakePreviousShotsWorker:
    """Test double for PreviousShotsWorker with controlled behavior."""

    def __init__(self):
        # Use FakeSignal for non-Qt double
        self.shot_found = FakeSignal()
        self.scan_progress = FakeSignal()
        self.scan_finished = FakeSignal()
        self.error_occurred = FakeSignal()

        # Control behavior
        self.should_stop = False
        self.run_calls = 0
        self.shots_to_find = []

    def run(self):
        """Simulate worker execution."""
        self.run_calls += 1

        # Emit signals based on configuration
        for i, shot in enumerate(self.shots_to_find):
            if self.should_stop:
                break

            shot_dict = {
                "show": shot.show,
                "sequence": shot.sequence,
                "shot": shot.shot,
                "workspace_path": shot.workspace_path,
            }
            self.shot_found.emit(shot_dict)
            self.scan_progress.emit(i + 1, len(self.shots_to_find))

        if not self.should_stop:
            self.scan_finished.emit([])

    def stop(self):
        """Request stop."""
        self.should_stop = True


def create_test_shot(show="test", seq="seq01", shot="0010", path=None):
    """Factory function for creating test shots."""
    if path is None:
        path = f"/shows/{show}/shots/{seq}/{shot}"
    return Shot(show=show, sequence=seq, shot=shot, workspace_path=path)


def create_test_shots(count=3, show="test"):
    """Create multiple test shots."""
    return [
        create_test_shot(show, f"seq{i:02d}", f"{(i + 1) * 10:04d}")
        for i in range(count)
    ]
