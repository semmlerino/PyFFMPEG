#!/usr/bin/env python3
"""ShotBot launcher with EARLY mock injection for development/testing.

This launcher ensures mock ProcessPoolManager is injected BEFORE any imports
that might create singleton instances using the new dependency injection system.
It also detects and uses recreated VFX filesystem if available.
"""

import logging
import os
import sys

# CRITICAL: Set mock mode FIRST
os.environ["SHOTBOT_MOCK"] = "1"

# CRITICAL: Set SHOWS_ROOT immediately to ensure Config uses mock path
# This MUST happen before ANY module imports that might load Config
# Respect SHOWS_ROOT if already set (e.g., by run_mock_vfx_env.py)
if "SHOWS_ROOT" not in os.environ:
    # Default to the shows directory within mock VFX structure for consistent paths
    os.environ["SHOWS_ROOT"] = "/tmp/mock_vfx/shows"

# Set up logging immediately
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

logger.info("🚀 Starting ShotBot in MOCK MODE")

# Check for recreated VFX structure
from pathlib import Path  # noqa: E402

MOCK_VFX_PATHS = [
    Path("/tmp/mock_vfx/shows"),
    Path("/tmp/shows"),  # Symlink
    Path.home() / "mock_vfx" / "shows",
]

mock_filesystem_found = False
for mock_path in MOCK_VFX_PATHS:
    if mock_path.exists():
        # Found mock filesystem - just report it (don't override SHOWS_ROOT if already set correctly)
        logger.info(f"🎬 Using mock VFX filesystem at: {mock_path}")
        logger.info(f"   SHOWS_ROOT is: {os.environ.get('SHOWS_ROOT', 'NOT SET')}")
        mock_filesystem_found = True

        # Also check if we have the marker file
        marker = mock_path.parent / "MOCK_VFX_ENVIRONMENT.txt"
        if marker.exists():
            logger.info("   ✅ Valid mock environment detected")
        break

if not mock_filesystem_found:
    # SHOWS_ROOT should already be set correctly by earlier logic
    logger.info(
        "ℹ️  No mock filesystem found. Run recreate_vfx_structure.py to create one."
    )
    logger.info("   The app will work but paths won't exist.")
    logger.info(f"   SHOWS_ROOT is: {os.environ.get('SHOWS_ROOT', 'NOT SET')}")

# CRITICAL: Use the new dependency injection system BEFORE any app imports
from process_pool_factory import ProcessPoolFactory  # noqa: E402

# Enable mock mode in the factory
ProcessPoolFactory.set_mock_mode(True)
logger.info("✅ Mock mode enabled in ProcessPoolFactory")

# The factory will automatically load demo_shots.json and create the mock instance
# when get_instance() is called for the first time

# NOW we can import the rest of the app
logger.info("Loading ShotBot application...")

# Import the original main function
from shotbot import main  # noqa: E402

# Run the original main but skip the mock injection part
# (since we already did it properly)
if __name__ == "__main__":
    # The main() in shotbot.py will still parse args and check for --mock,
    # but our early injection ensures it works properly

    # For WSL compatibility, set some defaults
    if "WSL" in os.uname().release or "Microsoft" in os.uname().release:
        logger.info("🖥️  WSL detected - using compatibility settings")
        # Use xcb platform for WSL
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
        # Ensure display is set
        os.environ.setdefault("DISPLAY", ":0")

    try:
        main()
    except Exception as e:
        logger.error(f"❌ Error running ShotBot: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
