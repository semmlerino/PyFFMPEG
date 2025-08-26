#!/usr/bin/env python3
"""Test script to verify the application can start without errors."""

import os
import sys
from unittest.mock import MagicMock, patch

# Set up headless mode for testing
os.environ['QT_QPA_PLATFORM'] = 'offscreen'


def test_imports():
    """Test that all main modules can be imported."""
    print("Testing imports...")
    
    try:
        from persistent_bash_session import PersistentBashSession
        from process_pool_manager import ProcessPoolManager
        print("  ✓ ProcessPoolManager and PersistentBashSession")
    except ImportError as e:
        print(f"  ✗ Failed to import process pool components: {e}")
        return False
    
    try:
        from main_window import MainWindow
        print("  ✓ MainWindow")
    except ImportError as e:
        print(f"  ✗ Failed to import MainWindow: {e}")
        return False
    
    try:
        from shot_model import ShotModel
        print("  ✓ ShotModel")
    except ImportError as e:
        print(f"  ✗ Failed to import ShotModel: {e}")
        return False
    
    try:
        from cache_manager import CacheManager
        print("  ✓ CacheManager")
    except ImportError as e:
        print(f"  ✗ Failed to import CacheManager: {e}")
        return False
    
    try:
        from launcher_manager import LauncherManager
        print("  ✓ LauncherManager")
    except ImportError as e:
        print(f"  ✗ Failed to import LauncherManager: {e}")
        return False
    
    return True


def test_model_creation():
    """Test that core models can be instantiated."""
    print("\nTesting model creation...")
    
    try:
        from shot_model import ShotModel
        ShotModel()
        print("  ✓ Created ShotModel")
    except Exception as e:
        print(f"  ✗ Failed to create ShotModel: {e}")
        return False
    
    try:
        from cache_manager import CacheManager
        CacheManager()
        print("  ✓ Created CacheManager")
    except Exception as e:
        print(f"  ✗ Failed to create CacheManager: {e}")
        return False
    
    try:
        from process_pool_manager import ProcessPoolManager
        ProcessPoolManager.get_instance()
        print("  ✓ Created ProcessPoolManager singleton")
    except Exception as e:
        print(f"  ✗ Failed to create ProcessPoolManager: {e}")
        return False
    
    return True


def test_main_window_creation():
    """Test that MainWindow can be created (headless)."""
    print("\nTesting MainWindow creation...")
    
    try:
        from PySide6.QtWidgets import QApplication
        
        # Create QApplication if it doesn't exist
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        from main_window import MainWindow
        
        # Mock the subprocess calls to avoid actually running ws command
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout='',
                stderr='',
                returncode=0
            )
            
            window = MainWindow()
            print("  ✓ Created MainWindow")
            
            # Check key attributes exist
            if hasattr(window, 'shot_model'):
                print("  ✓ MainWindow has shot_model")
            else:
                print("  ✗ MainWindow missing shot_model")
                
            if hasattr(window, 'cache_manager'):
                print("  ✓ MainWindow has cache_manager")
            else:
                print("  ✗ MainWindow missing cache_manager")
                
            # Clean up
            window.close()
            app.quit()
            
        return True
        
    except Exception as e:
        print(f"  ✗ Failed to create MainWindow: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_process_pool_session():
    """Test that ProcessPoolManager can work with PersistentBashSession."""
    print("\nTesting ProcessPoolManager with PersistentBashSession...")
    
    try:
        from process_pool_manager import ProcessPoolManager
        
        # Check that ProcessPoolManager imports PersistentBashSession
        ProcessPoolManager.get_instance()
        
        # Verify the import is used by checking the class source
        import inspect
        source = inspect.getsource(ProcessPoolManager)
        if 'PersistentBashSession' in source:
            print("  ✓ ProcessPoolManager uses PersistentBashSession")
        else:
            print("  ✗ ProcessPoolManager doesn't reference PersistentBashSession")
            return False
        
        # Also verify the import statement
        with open('process_pool_manager.py', 'r') as f:
            content = f.read()
            if 'from persistent_bash_session import PersistentBashSession' in content:
                print("  ✓ ProcessPoolManager imports PersistentBashSession correctly")
            else:
                print("  ✗ ProcessPoolManager missing PersistentBashSession import")
                return False
            
        return True
        
    except Exception as e:
        print(f"  ✗ Failed to test ProcessPoolManager: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing ShotBot Application Startup")
    print("=" * 60)
    
    all_passed = True
    
    if not test_imports():
        all_passed = False
        
    if not test_model_creation():
        all_passed = False
        
    if not test_process_pool_session():
        all_passed = False
        
    if not test_main_window_creation():
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All startup tests PASSED - Application is ready to run!")
        print("\nYou can now run the application with:")
        print("  source venv/bin/activate")
        print("  python shotbot.py")
    else:
        print("✗ Some tests FAILED - Please fix the issues above")
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()