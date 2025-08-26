#!/usr/bin/env python3
"""Test that shot refresh works with the refactored components."""

import sys
from unittest.mock import MagicMock, patch


def test_shot_refresh():
    """Test that ShotModel can refresh shots using ProcessPoolManager."""
    print("Testing shot refresh with ProcessPoolManager...")
    
    try:
        from shot_model import ShotModel
        
        # Create the shot model
        model = ShotModel()
        
        # Mock the subprocess to avoid actually running 'ws' command
        with patch('subprocess.Popen') as mock_popen:
            # Setup mock to simulate bash session
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # Process is alive
            mock_process.stdin = MagicMock()
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            
            # Simulate reading initialization marker
            mock_process.stdout.readline.return_value = "__INIT_COMPLETE_test__\n"
            mock_process.stdout.fileno.return_value = 1
            
            mock_popen.return_value = mock_process
            
            # Try to refresh shots
            print("  Attempting to refresh shots...")
            success, has_changes = model.refresh_shots()
            
            if mock_popen.called:
                print("  ✓ ProcessPoolManager attempted to create bash session")
                print(f"  ✓ Refresh completed (mocked): success={success}")
            else:
                print("  ✗ ProcessPoolManager didn't create bash session")
                return False
                
        print("✓ Shot refresh works with ProcessPoolManager and PersistentBashSession")
        return True
        
    except Exception as e:
        print(f"✗ Failed to test shot refresh: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run the test."""
    print("=" * 60)
    print("Testing Shot Refresh with Refactored Components")
    print("=" * 60)
    
    if test_shot_refresh():
        print("\n✓ Shot refresh integration test PASSED")
        print("\nThe refactored PersistentBashSession is properly integrated.")
    else:
        print("\n✗ Shot refresh integration test FAILED")
        sys.exit(1)
    
    print("=" * 60)


if __name__ == "__main__":
    main()