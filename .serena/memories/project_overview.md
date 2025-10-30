# ShotBot - Project Overview

## Purpose
ShotBot is a PySide6-based GUI application for VFX shot browsing and application launching. It integrates with VFX pipeline tools using the `ws` (workspace) command to list and navigate shots. The application provides a visual interface for artists to browse shots, view thumbnails, and launch VFX applications (3DE, Nuke, Maya, RV) in the correct shot context.

## Key Features
- Visual shot browsing with thumbnail grid
- Three-tab interface:
  - **My Shots**: Current shots from `ws -sg` command
  - **Other 3DE Scenes**: Browse 3DE scenes created by other artists
  - **Previous Shots**: Historical shots from user's work
- Launch applications in shot context with proper environment
- Automatic thumbnail loading with multi-format support (JPEG, EXR, PIL)
- Resizable thumbnails with Ctrl+scroll zoom
- Dark theme optimized for VFX workflows
- Show filtering across all tabs
- Background refresh with change detection

## Security Context
This is a **personal VFX pipeline tool running on a secure, isolated network**. Security hardening is NOT a concern. Focus on functionality, performance, and VFX workflow optimization.

## Environment Support
- **Production mode**: Requires VFX environment with `ws` command
- **Mock mode**: Full development environment with 432 production shots simulated
- **Headless mode**: For CI/CD with Qt offscreen rendering
