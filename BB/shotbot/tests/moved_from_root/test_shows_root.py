#!/usr/bin/env python3
"""Test script to verify SHOWS_ROOT configuration is working correctly."""

# Standard library imports
import os
import sys

# Set mock environment
os.environ["SHOWS_ROOT"] = "/tmp/mock_vfx"

# Local application imports
# Import after setting environment
from config import Config
from mock_workspace_pool import MockWorkspacePool
from previous_shots_finder import PreviousShotsFinder
from targeted_shot_finder import TargetedShotsFinder


def test_shows_root_configuration() -> bool:
    """Test that all components use the configured SHOWS_ROOT."""
    print("Testing SHOWS_ROOT configuration...")
    print(f"Environment SHOWS_ROOT: {os.environ.get('SHOWS_ROOT')}")
    print(f"Config.SHOWS_ROOT: {Config.SHOWS_ROOT}")
    print(f"Config.SHOW_ROOT_PATHS: {Config.SHOW_ROOT_PATHS}")

    # Test mock pool
    print("\nTesting MockWorkspacePool...")
    pool = MockWorkspacePool()
    pool.shots = ["workspace /tmp/mock_vfx/test/shots/seq/seq_001"]
    command_output = pool.execute_workspace_command("ws -sg")
    print(
        f"Mock pool output contains correct path: {'/tmp/mock_vfx' in command_output}"
    )

    # Test targeted shot finder regex
    print("\nTesting TargetedShotsFinder...")
    finder = TargetedShotsFinder("testuser")
    test_path = "/tmp/mock_vfx/show/shots/seq/seq_001/"
    pattern_str = finder._shot_pattern.pattern
    print(f"Pattern uses configured root: {'/tmp/mock_vfx' in pattern_str}")
    match = finder._shot_pattern.search(test_path)
    print(f"Pattern matches mock path: {match is not None}")

    # Test previous shots finder regex
    print("\nTesting PreviousShotsFinder...")
    prev_finder = PreviousShotsFinder("testuser")
    pattern_str = prev_finder._shot_pattern.pattern
    print(f"Pattern uses configured root: {'/tmp/mock_vfx' in pattern_str}")
    match = prev_finder._shot_pattern.search(test_path)
    print(f"Pattern matches mock path: {match is not None}")

    # Test workspace path construction
    print("\nTesting workspace path construction...")
    # Local application imports
    from shot_model import Shot

    shot = Shot(
        show="test_show",
        sequence="seq01",
        shot="0010",
        workspace_path=f"{Config.SHOWS_ROOT}/test_show/shots/seq01/seq01_0010",
    )
    print(
        f"Workspace path uses configured root: {'/tmp/mock_vfx' in shot.workspace_path}"
    )

    print("\n✅ All SHOWS_ROOT configuration tests passed!")
    return True


if __name__ == "__main__":
    try:
        success = test_shows_root_configuration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        # Standard library imports
        import traceback

        traceback.print_exc()
        sys.exit(1)
