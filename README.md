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

- Python 3.8+
- PySide6
- FFmpeg (must be in PATH)

## Installation

```bash
# Using uv (recommended)
uv sync --dev

# Or using pip
pip install -e .
```

## Usage

```bash
# Run the refactored version (recommended)
python main_window_refactored.py

# Or use the installed command
pympeg
```

## Development

```bash
# Install development dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linting
uv run ruff check .

# Run type checking
uv run basedpyright
```

## License

MIT
