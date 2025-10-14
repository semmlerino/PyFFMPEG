#!/usr/bin/env python3
"""Helper script to take a screenshot of the screen."""

from pathlib import Path

from PIL import ImageGrab


def take_screenshot() -> Path:
    """Capture screenshot and save it."""
    output_path = Path("/tmp/shotbot_screenshot.png")

    # Grab the entire screen
    screenshot = ImageGrab.grab()

    # Save to file
    screenshot.save(str(output_path))
    print(f"Screenshot saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    take_screenshot()
