# PyMPEG

A PySide6-based GUI application for batch video conversion using FFmpeg.

## Features

- Hardware-accelerated encoding (NVENC, QSV, VAAPI)
- Parallel processing with load balancing
- Real-time progress tracking with ETA calculations
- Support for multiple codecs: H.264, HEVC, AV1, ProRes
- Smart buffer mode for performance optimization
- Auto-balance feature for hybrid GPU/CPU encoding workloads

## Requirements

- Python 3.12+
- PySide6
- psutil
- FFmpeg / ffprobe (must be in PATH)

## Installation

```bash
# Using uv (recommended) — installs runtime + dev dependencies
uv sync --extra dev

# Or using pip (runtime only)
pip install -e .
```

## Usage

```bash
# Run the refactored version (recommended)
uv run python main_window_refactored.py

# Or use the installed command
uv run pympeg
```

## Development

```bash
# Install development dependencies
uv sync --extra dev

# Run tests (--extra dev is required: addopts pulls in pytest-cov)
uv run --extra dev pytest

# Run linting
uv run ruff check .

# Run type checking
uv run basedpyright --level error
```

## License

MIT
