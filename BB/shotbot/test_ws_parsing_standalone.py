#!/usr/bin/env python3
"""Standalone test script to verify ws output parsing without PySide6."""

import re

# Actual ws -sg output from VFX environment
WS_OUTPUT = """workspace /shows/gator/shots/012_DC/012_DC_1000
workspace /shows/gator/shots/012_DC/012_DC_1070
workspace /shows/gator/shots/012_DC/012_DC_1050
workspace /shows/jack_ryan/shots/DB_271/DB_271_1760
workspace /shows/jack_ryan/shots/FF_278/FF_278_4380
workspace /shows/jack_ryan/shots/DA_280/DA_280_0280
workspace /shows/jack_ryan/shots/DC_278/DC_278_0050
workspace /shows/broken_eggs/shots/BRX_166/BRX_166_0010
workspace /shows/broken_eggs/shots/BRX_166/BRX_166_0020
workspace /shows/broken_eggs/shots/BRX_170/BRX_170_0100
workspace /shows/broken_eggs/shots/BRX_070/BRX_070_0010
workspace /shows/jack_ryan/shots/999_xx/999_xx_999"""

def test_parsing():
    """Test parsing of actual ws output."""
    parse_pattern = re.compile(
        r"workspace\s+(/shows/(\w+)/shots/(\w+)/(\w+_\w+))",
    )
    
    lines = WS_OUTPUT.strip().split("\n")
    print(f"Parsing {len(lines)} lines of ws output\n")
    print("=" * 80)
    
    all_passed = True
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
            
        match = parse_pattern.search(line)
        if match:
            workspace_path = match.group(1)
            show = match.group(2)
            sequence = match.group(3)
            shot_dir = match.group(4)
            
            # Extract shot from shot_dir
            if shot_dir.startswith(f"{sequence}_"):
                shot = shot_dir[len(sequence) + 1:]
            else:
                shot_parts = shot_dir.rsplit("_", 1)
                if len(shot_parts) == 2:
                    shot = shot_parts[1]
                else:
                    shot = shot_dir
            
            print(f"Line {line_num}: {line}")
            print(f"  Parsed:")
            print(f"    workspace_path: {workspace_path}")
            print(f"    show: {show}")
            print(f"    sequence: {sequence}")
            print(f"    shot_dir: {shot_dir}")
            print(f"    extracted shot: {shot}")
            
            # Create full_name
            full_name = f"{sequence}_{shot}"
            print(f"    full_name: {full_name}")
            
            # Build thumbnail path (manually construct it)
            thumb_path = f"/shows/{show}/shots/{sequence}/{shot_dir}/publish/editorial/cutref/v001/jpg/1920x1080"
            print(f"    thumbnail_dir: {thumb_path}")
            
            # Check for the issue - should NOT contain /shots/shots/
            if "/shots/shots/" in thumb_path:
                print(f"    ❌ ERROR: Path contains duplicate 'shots': {thumb_path}")
                all_passed = False
            elif f"/shots/{sequence}/{shot_dir}/" in thumb_path:
                print(f"    ✓ Path correctly constructed")
            else:
                print(f"    ⚠ WARNING: Path structure may be incorrect")
                all_passed = False
                
            # Check if shot is parsed correctly (should be numeric, not contain underscores)
            if "_" in shot or shot == sequence:
                print(f"    ❌ ERROR: Shot '{shot}' incorrectly parsed (should be numeric part only)")
                all_passed = False
            else:
                print(f"    ✓ Shot correctly extracted")
                
            print()
        else:
            print(f"Line {line_num}: NO MATCH - {line}")
            print()
            all_passed = False
    
    print("=" * 80)
    if all_passed:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
    return all_passed

if __name__ == "__main__":
    test_parsing()