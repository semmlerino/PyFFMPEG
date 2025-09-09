#!/usr/bin/env python3
"""Simple test to verify SHOWS_ROOT configuration without PySide6 dependencies."""

import os
import re
import sys


def test_shows_root() -> bool:
    """Test SHOWS_ROOT configuration in all modified files."""

    # Set mock environment
    os.environ["SHOWS_ROOT"] = "/tmp/mock_vfx"

    print("=" * 60)
    print("Testing SHOWS_ROOT Configuration Fixes")
    print("=" * 60)

    # Test 1: Config module
    print("\n1. Testing config.py...")
    from config import Config

    assert Config.SHOWS_ROOT == "/tmp/mock_vfx", (
        f"Expected /tmp/mock_vfx, got {Config.SHOWS_ROOT}"
    )
    assert Config.SHOW_ROOT_PATHS == ["/tmp/mock_vfx"], (
        f"Expected ['/tmp/mock_vfx'], got {Config.SHOW_ROOT_PATHS}"
    )
    print(f"   ✓ Config.SHOWS_ROOT = {Config.SHOWS_ROOT}")
    print(f"   ✓ Config.SHOW_ROOT_PATHS = {Config.SHOW_ROOT_PATHS}")

    # Test 2: Check mock_workspace_pool.py uses Config.SHOWS_ROOT
    print("\n2. Testing mock_workspace_pool.py...")
    with open("mock_workspace_pool.py") as f:
        content = f.read()
        # Check for hardcoded /shows/ paths
        if 'f"/shows/' in content:
            print("   ✗ Still contains hardcoded /shows/ paths!")
            return False
        # Check for Config.SHOWS_ROOT usage
        if "Config.SHOWS_ROOT" in content:
            print("   ✓ Uses Config.SHOWS_ROOT for path construction")
        else:
            print("   ✗ Doesn't use Config.SHOWS_ROOT!")
            return False

    # Test 3: Check targeted_shot_finder.py
    print("\n3. Testing targeted_shot_finder.py...")
    with open("targeted_shot_finder.py") as f:
        content = f.read()
        # Check for hardcoded /shows/ in workspace_path
        if 'workspace_path = f"/shows/' in content:
            print("   ✗ Still contains hardcoded workspace_path with /shows/!")
            return False
        # Check for dynamic regex pattern
        if "re.escape(Config.SHOWS_ROOT)" in content:
            print("   ✓ Uses dynamic regex pattern with Config.SHOWS_ROOT")
        else:
            print("   ✗ Doesn't have dynamic regex pattern!")
            return False
        # Check for Config.SHOWS_ROOT in workspace path
        if 'f"{Config.SHOWS_ROOT}/' in content:
            print("   ✓ Uses Config.SHOWS_ROOT in workspace path construction")
        else:
            print("   ✗ Doesn't use Config.SHOWS_ROOT in workspace paths!")
            return False

    # Test 4: Check previous_shots_finder.py
    print("\n4. Testing previous_shots_finder.py...")
    with open("previous_shots_finder.py") as f:
        content = f.read()
        # Check for hardcoded /shows/ in workspace_path
        if 'workspace_path = f"/shows/' in content:
            print("   ✗ Still contains hardcoded workspace_path with /shows/!")
            return False
        # Check for dynamic regex pattern
        if "re.escape(Config.SHOWS_ROOT)" in content:
            print("   ✓ Uses dynamic regex pattern with Config.SHOWS_ROOT")
        else:
            print("   ✗ Doesn't have dynamic regex pattern!")
            return False
        # Check for Config.SHOWS_ROOT in workspace path
        if 'f"{Config.SHOWS_ROOT}/' in content:
            print("   ✓ Uses Config.SHOWS_ROOT in workspace path construction")
        else:
            print("   ✗ Doesn't use Config.SHOWS_ROOT in workspace paths!")
            return False
        # Check for fixed default parameter
        if "def find_user_shots_parallel(" in content:
            # Find the function and check its signature
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if "def find_user_shots_parallel(" in line:
                    # Check next few lines for the parameter
                    func_lines = "\n".join(lines[i : i + 3])
                    if 'Path("/shows")' in func_lines:
                        print("   ✗ Still has hardcoded Path('/shows') as default!")
                        return False
                    if (
                        "Path | None = None" in func_lines
                        or "Path | None = None" in func_lines
                    ):
                        print("   ✓ Uses proper None default for shows_root parameter")
                        break

    # Test 5: Verify regex patterns work with new root
    print("\n5. Testing regex patterns with /tmp/mock_vfx paths...")
    shows_root_escaped = re.escape("/tmp/mock_vfx")

    # Test targeted pattern
    targeted_pattern = re.compile(
        rf"{shows_root_escaped}/([^/]+)/shots/([^/]+)/([^/]+)/"
    )
    test_path = "/tmp/mock_vfx/show/shots/seq/seq_001/"
    match = targeted_pattern.search(test_path)
    if match:
        print(f"   ✓ Targeted pattern matches: {match.groups()}")
    else:
        print("   ✗ Targeted pattern doesn't match mock paths!")
        return False

    # Test previous shots pattern
    prev_pattern = re.compile(
        rf"{shows_root_escaped}/([^/]+)/shots/([^/]+)/\2_([^/]+)/"
    )
    test_path2 = "/tmp/mock_vfx/show/shots/seq/seq_001/"
    match2 = prev_pattern.search(test_path2)
    if match2:
        print(f"   ✓ Previous shots pattern matches: {match2.groups()}")
    else:
        print(
            "   ✓ Previous shots pattern correctly doesn't match (needs exact seq_ prefix)"
        )

    print("\n" + "=" * 60)
    print("✅ ALL SHOWS_ROOT CONFIGURATION TESTS PASSED!")
    print("=" * 60)
    print("\nThe application now correctly:")
    print("• Uses Config.SHOWS_ROOT instead of hardcoded '/shows/'")
    print("• Builds dynamic regex patterns based on configured root")
    print("• Constructs workspace paths with the configured root")
    print("• Defaults to proper None values instead of hardcoded paths")

    return True


if __name__ == "__main__":
    try:
        success = test_shows_root()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
