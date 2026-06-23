"""Unit tests for domain.job — ConversionJob, ProcessState, BatchState.

These are pure domain containers with NO Qt objects: per-process state is keyed
by a process_id string, never by a QProcess handle.
"""

import dataclasses

import pytest

from domain.codec import CODEC_REGISTRY
from domain.job import BatchState, ConversionJob, ProcessState
from domain.settings import ConversionSettings


def _settings() -> ConversionSettings:
    return ConversionSettings(
        codec_idx=0,
        hwdecode_idx=0,
        crf_value=16,
        parallel_enabled=False,
        max_parallel=4,
        delete_source=False,
        overwrite_mode=False,
    )


class TestConversionJob:
    def test_holds_paths_codec_and_settings(self):
        job = ConversionJob(
            input_path="/in/a.ts",
            output_path="/in/a_RC.mkv",
            codec=CODEC_REGISTRY[0],
            settings=_settings(),
        )
        assert job.input_path == "/in/a.ts"
        assert job.output_path == "/in/a_RC.mkv"
        assert job.codec.encoder_name == "h264_nvenc"
        assert job.settings.crf_value == 16

    def test_job_is_immutable(self):
        job = ConversionJob("/in/a.ts", "/out/a.mkv", CODEC_REGISTRY[3], _settings())
        with pytest.raises(dataclasses.FrozenInstanceError):
            job.input_path = "/other"  # type: ignore[misc]


class TestProcessState:
    def test_field_set_matches_legacy_dict(self):
        names = {f.name for f in dataclasses.fields(ProcessState)}
        assert names == {
            "path",
            "duration",
            "start_time",
            "current_pct",
            "fps",
            "last_frame",
            "last_fps_time",
            "elapsed_sec",
            "prev_eta_values",
            "last_progress_time",
            "last_progress_value",
        }

    def test_defaults(self):
        ps = ProcessState(path="/in/a.ts", duration=120.0, start_time=1000.0)
        assert ps.current_pct == 0.0
        assert ps.fps == 0.0
        assert ps.prev_eta_values == []

    def test_prev_eta_values_not_shared_between_instances(self):
        a = ProcessState(path="a", duration=1.0, start_time=0.0)
        b = ProcessState(path="b", duration=1.0, start_time=0.0)
        a.prev_eta_values.append(5.0)
        assert b.prev_eta_values == []

    def test_is_mutable(self):
        ps = ProcessState(path="a", duration=1.0, start_time=0.0)
        ps.current_pct = 42.0
        assert ps.current_pct == 42.0


class TestBatchState:
    def test_defaults_empty(self):
        bs = BatchState()
        assert bs.total == 0
        assert bs.completed_count == 0
        assert bs.failed_count == 0
        assert bs.processes == {}

    def test_keyed_by_process_id_string(self):
        bs = BatchState(total=2)
        bs.processes["proc-1"] = ProcessState(path="a", duration=1.0, start_time=0.0)
        assert "proc-1" in bs.processes
        assert bs.processes["proc-1"].path == "a"

    def test_processes_not_shared_between_instances(self):
        a = BatchState()
        b = BatchState()
        a.processes["x"] = ProcessState(path="x", duration=1.0, start_time=0.0)
        assert b.processes == {}
