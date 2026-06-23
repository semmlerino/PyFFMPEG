"""Pure domain containers for a conversion job and its runtime state.

No Qt objects live here: per-process state is keyed by a ``process_id`` string,
never by a ``QProcess`` handle, so the Qt manager can own the handles while the
domain owns the state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Imported at runtime (not guarded by TYPE_CHECKING) so the dataclass field types
# stay resolvable via typing.get_type_hints. These are pure sibling modules with
# no circular-import risk.
from pympeg.domain.codec import Codec  # noqa: TC001
from pympeg.domain.settings import ConversionSettings  # noqa: TC001


@dataclass(frozen=True)
class ConversionJob:
    """An immutable unit of work: one input file -> one output file."""

    input_path: str
    output_path: str
    codec: Codec
    settings: ConversionSettings


@dataclass
class ProcessState:
    """Mutable per-process progress state (mirrors the legacy tracker dict)."""

    path: str
    duration: float
    start_time: float
    current_pct: float = 0.0
    fps: float = 0.0
    last_frame: int = 0
    last_fps_time: float = 0.0
    elapsed_sec: float = 0.0
    prev_eta_values: list[float] = field(default_factory=list)
    last_progress_time: float = 0.0
    last_progress_value: float = 0.0


@dataclass
class BatchState:
    """Aggregate state for a conversion batch, keyed by process_id."""

    total: int = 0
    completed_count: int = 0
    failed_count: int = 0
    processes: dict[str, ProcessState] = field(default_factory=dict)
