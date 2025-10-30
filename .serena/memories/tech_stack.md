# Technology Stack

## Core Technologies
- **Python**: 3.11+ (uses modern union syntax `str | None`)
- **GUI Framework**: PySide6 (Qt for Python)
- **Package Manager**: uv (fast Python package/project manager)

## Key Dependencies
- **PySide6** >= 6.0.0 - Qt GUI framework
- **psutil** >= 5.9.0 - Process and system utilities
- **Pillow** >= 10.0.0 - Image processing
- **Jinja2** >= 3.0.0 - Template engine (for Nuke scripts)
- **OpenEXR** >= 1.3.0 - EXR image support for VFX thumbnails
- **olefile** >= 0.46 - OLE file format support
- **typing_extensions** >= 4.0.0 - Python 3.11 compatibility (@override decorator)

## Development Tools
- **pytest** >= 8.0.0 - Testing framework
- **pytest-qt** >= 4.0.0 - Qt testing support
- **pytest-xdist** >= 3.8.0 - Parallel test execution
- **pytest-timeout** >= 2.0.0 - Test timeout management
- **hypothesis** >= 6.0.0 - Property-based testing
- **ruff** >= 0.1.0 - Fast Python linter and formatter
- **basedpyright** >= 1.31.0 - Type checker (recommended mode)

## Architecture Patterns
- **Model-View**: Qt's signal-slot mechanism for loose coupling
- **Dependency Injection**: ProcessPoolFactory for mock injection
- **Generic Base Classes**: BaseItemModel[T] for shared Qt infrastructure
- **Worker Pattern**: QThread workers for background operations
- **Singleton**: ProcessPoolManager for subprocess management
