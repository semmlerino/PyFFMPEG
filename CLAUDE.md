# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

PyFFMPEG (package `pympeg`, console script `pympeg`) is a PySide6 GUI for batch video conversion
via FFmpeg, with GPU/CPU auto-balanced parallel encoding. Layout lives under `src/pympeg/`
(`domain/`, `encoding/`, `hardware/`, `metadata/`, `sizing/` + top-level UI/controller modules) —
use `get_symbols_overview` rather than trusting a static file inventory here; it has drifted before
(the old monolithic `PyMPEG.py` this doc used to describe as "kept for reference" is gone).

## Commands

```bash
uv sync --extra dev
uv run pympeg                                  # run the app
uv run ruff check . --fix && uv run ruff format .
uv run basedpyright --level error              # 0 errors required; excludes nothing now — legacy monolith removed
QT_QPA_PLATFORM=offscreen uv run --extra dev pytest -q   # --extra dev needed: addopts pulls in pytest-cov
```

## Non-obvious behavior

**Progress parsing (`output_buffer.py` → `progress_tracker.py`).** FFmpeg's `-progress pipe:1`
stream is `key=value` lines on stdout, one per line; stderr carries human log lines plus MPEGTS
timing-warning detection (`SeparateChannels`, so don't conflate the two streams). `out_time_us` is
microseconds, and confusingly so is the legacy `out_time_ms` key — both need the same `/1e6`
conversion, not `/1000`. A carry-over rule reassembles `key=value` lines that QProcess reads split
mid-line; `force_process()` flushes the final, possibly-unterminated block. `probe_duration()`
(ffprobe) supplies the denominator for percentage; 100% is forced on process finish since
`out_time` rarely reaches the exact source duration.

**Hardware detection (`hardware/probe.py`, singleton `HARDWARE_PROBE`).** TTL-cached (dual
success/failure TTL via `TtlCache`) to avoid repeated `nvidia-smi`/`ffmpeg -encoders` subprocess
calls. Fallback chain: NVENC → QSV → VAAPI → software. Auto-balance splits files ~70% GPU / 30%
CPU.

**Thread allocation (`encoding/arg_builder.py::CodecArgBuilder.optimize_threads_for_codec`).**
NVENC encoders get 2 threads (minimal CPU use); a single CPU job gets 0 (auto-detect, all
threads); parallel CPU jobs split `cpu_count() // cpu_jobs` evenly, with `None`-safety on
`cpu_count()`.

**Type checking:** `[tool.basedpyright]` in `pyproject.toml` covers only the current package —
there is no legacy-module exclusion to maintain anymore.
