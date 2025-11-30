"""Pin manager for tracking and persisting pinned shots.

This module provides PinManager which handles:
- Tracking which shots are pinned
- Persistence to cache (survives application restarts)
- Pin ordering (most recently pinned first)
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import TYPE_CHECKING, Any, cast

from logging_mixin import LoggingMixin


if TYPE_CHECKING:
    from cache_manager import CacheManager
    from shot_model import Shot


# Cache key for pinned shots
PINNED_SHOTS_CACHE_KEY = "pinned_shots"


class PinManager(LoggingMixin):
    """Manages pinned shot tracking and persistence.

    Tracks shots by composite key (show, sequence, shot) to handle
    Shot objects which may be recreated between sessions.

    Pin order is most-recently-pinned-first.
    """

    _cache_manager: CacheManager
    _pinned_keys: list[tuple[str, str, str]]

    def __init__(self, cache_manager: CacheManager) -> None:
        """Initialize the pin manager.

        Args:
            cache_manager: Cache manager for persistence
        """
        super().__init__()
        self._cache_manager = cache_manager
        self._pinned_keys = []  # (show, seq, shot)
        self._load_pins()

    def _load_pins(self) -> None:
        """Load pinned shots from cache."""
        cache_file = self._cache_manager.cache_dir / f"{PINNED_SHOTS_CACHE_KEY}.json"

        if not cache_file.exists():
            self._pinned_keys = []
            return

        try:
            with open(cache_file) as f:
                raw_data: Any = json.load(f)  # pyright: ignore[reportAny]

            if not isinstance(raw_data, list):
                self.logger.warning(f"Invalid pinned shots cache format: {type(raw_data)}")
                self._pinned_keys = []
                return

            # Cast to expected type for iteration
            data = cast("list[dict[str, str] | list[str]]", raw_data)

            # Convert stored dicts to keys
            self._pinned_keys = []
            for item in data:
                if isinstance(item, dict):
                    try:
                        show_val = item.get("show")
                        seq_val = item.get("sequence")
                        shot_val = item.get("shot")
                        if isinstance(show_val, str) and isinstance(seq_val, str) and isinstance(shot_val, str):
                            self._pinned_keys.append((show_val, seq_val, shot_val))
                    except (KeyError, TypeError) as e:
                        self.logger.warning(f"Invalid pinned shot entry: {e}")
                elif isinstance(item, list) and len(item) == 3:  # pyright: ignore[reportUnnecessaryIsInstance]
                    # Also support tuple-as-list format
                    v0, v1, v2 = item[0], item[1], item[2]
                    # Runtime safety check - cast doesn't guarantee actual types
                    if isinstance(v0, str) and isinstance(v1, str) and isinstance(v2, str):  # pyright: ignore[reportUnnecessaryIsInstance]
                        self._pinned_keys.append((v0, v1, v2))

            self.logger.info(f"Loaded {len(self._pinned_keys)} pinned shots from cache")

        except (json.JSONDecodeError, OSError) as e:
            self.logger.warning(f"Failed to load pinned shots: {e}")
            self._pinned_keys = []

    def _save_pins(self) -> None:
        """Save pinned shots to cache."""
        cache_file = self._cache_manager.cache_dir / f"{PINNED_SHOTS_CACHE_KEY}.json"

        # Convert keys to dicts for JSON serialization
        pin_dicts = [
            {"show": show, "sequence": seq, "shot": shot}
            for show, seq, shot in self._pinned_keys
        ]

        try:
            # Atomic write via temp file
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=cache_file.parent,
                suffix=".tmp",
                delete=False,
            ) as f:
                json.dump(pin_dicts, f, indent=2)
                temp_path = f.name

            os.replace(temp_path, cache_file)
            self.logger.debug(f"Saved {len(self._pinned_keys)} pinned shots to cache")
        except OSError as e:
            self.logger.error(f"Failed to save pinned shots: {e}")

    def _get_key(self, shot: Shot) -> tuple[str, str, str]:
        """Get composite key for shot.

        Args:
            shot: Shot object

        Returns:
            Tuple of (show, sequence, shot) for uniqueness
        """
        return (shot.show, shot.sequence, shot.shot)

    def pin_shot(self, shot: Shot) -> None:
        """Pin a shot (adds to front of list).

        If shot is already pinned, moves it to the front.

        Args:
            shot: Shot to pin
        """
        key = self._get_key(shot)

        # Remove if already present (will re-add at front)
        if key in self._pinned_keys:
            self._pinned_keys.remove(key)
            self.logger.debug(f"Moving pinned shot to front: {shot.full_name}")
        else:
            self.logger.info(f"Pinning shot: {shot.full_name}")

        # Add to front
        self._pinned_keys.insert(0, key)
        self._save_pins()

    def unpin_shot(self, shot: Shot) -> None:
        """Unpin a shot.

        Args:
            shot: Shot to unpin
        """
        key = self._get_key(shot)

        if key in self._pinned_keys:
            self._pinned_keys.remove(key)
            self.logger.info(f"Unpinned shot: {shot.full_name}")
            self._save_pins()

    def is_pinned(self, shot: Shot) -> bool:
        """Check if a shot is pinned.

        Args:
            shot: Shot to check

        Returns:
            True if shot is pinned
        """
        return self._get_key(shot) in self._pinned_keys

    def get_pin_order(self, shot: Shot) -> int:
        """Get pin order for a shot.

        Args:
            shot: Shot to check

        Returns:
            Pin order (0 = most recent), or -1 if not pinned
        """
        key = self._get_key(shot)
        try:
            return self._pinned_keys.index(key)
        except ValueError:
            return -1

    def get_pinned_count(self) -> int:
        """Get the number of pinned shots.

        Returns:
            Number of pinned shots
        """
        return len(self._pinned_keys)

    def clear_pins(self) -> None:
        """Clear all pinned shots."""
        self._pinned_keys.clear()
        self._save_pins()
        self.logger.info("Cleared all pinned shots")
