"""Type stubs for shot_model module."""

import re
from pathlib import Path
from typing import NamedTuple

from cache_manager import CacheManager
from type_definitions import ShotDict

class RefreshResult(NamedTuple):
    """Result of shot refresh operation."""

    success: bool
    has_changes: bool

class Shot:
    """Represents a single shot."""

    show: str
    sequence: str
    shot: str
    workspace_path: str

    def __init__(
        self,
        show: str,
        sequence: str,
        shot: str,
        workspace_path: str,
    ) -> None: ...
    @property
    def full_name(self) -> str: ...
    @property
    def thumbnail_dir(self) -> Path: ...
    def get_thumbnail_path(self) -> Path | None: ...
    def to_dict(self) -> ShotDict: ...
    @classmethod
    def from_dict(cls, data: ShotDict) -> Shot: ...

class ShotModel:
    """Manages shot data and parsing."""

    shots: list[Shot]
    cache_manager: CacheManager
    _parse_pattern: re.Pattern[str]
    _selected_shot: Shot | None

    def __init__(
        self,
        cache_manager: CacheManager | None = ...,
        load_cache: bool = ...,
    ) -> None: ...
    def _load_from_cache(self) -> bool: ...
    def refresh_shots(self) -> RefreshResult: ...
    def _parse_ws_output(self, output: str) -> list[Shot]: ...
    def get_shot_by_index(self, index: int) -> Shot | None: ...
    def find_shot_by_name(self, full_name: str) -> Shot | None: ...
