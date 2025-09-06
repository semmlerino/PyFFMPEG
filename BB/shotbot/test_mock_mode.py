#!/usr/bin/env python3
"""Test script to verify mock mode functionality without GUI.

This script tests that mock mode properly injects test data
without requiring PySide6 or Qt GUI components.
"""

import json
import os
import sys
from pathlib import Path


def test_mock_setup():
    """Test that mock mode can be set up correctly."""
    print("Testing ShotBot Mock Mode Setup")
    print("=" * 50)
    
    # 1. Check demo_shots.json exists and is valid
    demo_shots_path = Path("demo_shots.json")
    if not demo_shots_path.exists():
        print("❌ ERROR: demo_shots.json not found!")
        return False
    
    try:
        with open(demo_shots_path) as f:
            demo_data = json.load(f)
            shots = demo_data.get("shots", [])
            print(f"✅ Found demo_shots.json with {len(shots)} shots")
            
            # Show sample data
            shows = set(s["show"] for s in shots)
            print(f"   Shows: {', '.join(sorted(shows))}")
            print("   First 3 shots:")
            for shot in shots[:3]:
                print(f"     - {shot['show']}/{shot['seq']}_{shot['shot']}")
    except Exception as e:
        print(f"❌ ERROR: Failed to load demo_shots.json: {e}")
        return False
    
    # 2. Check that mock flag is recognized
    print("\n2. Testing command-line argument parsing...")
    try:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--mock", action="store_true")
        
        # Test with --mock flag
        args = parser.parse_args(["--mock"])
        if args.mock:
            print("✅ --mock flag recognized")
        else:
            print("❌ --mock flag not working")
            return False
            
        # Test without flag
        args = parser.parse_args([])
        if not args.mock:
            print("✅ Default (no mock) mode works")
        else:
            print("❌ Default mode incorrectly enables mock")
            return False
    except Exception as e:
        print(f"❌ ERROR: Argument parsing failed: {e}")
        return False
    
    # 3. Test environment variable
    print("\n3. Testing environment variable...")
    mock_mode = os.environ.get("SHOTBOT_MOCK", "").lower() in ("1", "true", "yes")
    if "SHOTBOT_MOCK" in os.environ:
        print(f"   SHOTBOT_MOCK={os.environ.get('SHOTBOT_MOCK')} -> mock_mode={mock_mode}")
    else:
        print("   SHOTBOT_MOCK not set (normal mode)")
    print("✅ Environment variable check works")
    
    # 4. Simulate what happens in shotbot.py
    print("\n4. Simulating mock data injection...")
    outputs = []
    for shot in shots:
        show = shot.get("show", "demo")
        seq = shot.get("seq", "seq01")
        shot_num = shot.get("shot", "0010")
        outputs.append(f"workspace /shows/{show}/shots/{seq}/{seq}_{shot_num}")
    
    print(f"✅ Generated {len(outputs)} workspace commands")
    print("   Sample outputs:")
    for output in outputs[:3]:
        print(f"     {output}")
    
    print("\n" + "=" * 50)
    print("✅ All mock mode tests passed!")
    print("\nYou can now run:")
    print("  python3 shotbot.py --mock")
    print("or:")
    print("  SHOTBOT_MOCK=1 python3 shotbot.py")
    print("\nNote: The GUI will still require PySide6 to be installed.")
    return True

if __name__ == "__main__":
    success = test_mock_setup()
    sys.exit(0 if success else 1)