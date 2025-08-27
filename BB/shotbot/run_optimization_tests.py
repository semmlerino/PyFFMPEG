#!/usr/bin/env python3
"""Quick runner for optimization-specific tests."""

import subprocess
import sys

def run_optimization_tests():
    """Run the new optimization tests with proper setup."""
    
    test_files = [
        "test_async_shot_loader.py",
        "test_optimized_cache_scenarios.py", 
        "test_concurrent_optimizations.py",
        "test_error_recovery_optimized.py",
        "test_qt_integration_optimized.py"
    ]
    
    # Set environment for Qt testing
    env = {
        "QT_QPA_PLATFORM": "offscreen",
        "QT_LOGGING_RULES": "*.debug=false"
    }
    
    for test_file in test_files:
        print(f"\n{'='*60}")
        print(f"Running {test_file}")
        print(f"{'='*60}")
        
        try:
            result = subprocess.run([
                sys.executable, "-m", "pytest", 
                test_file, 
                "-v", "--tb=short", "--no-header"
            ], env=env, timeout=300)
            
            if result.returncode != 0:
                print(f"❌ {test_file} had failures")
            else:
                print(f"✅ {test_file} passed")
                
        except subprocess.TimeoutExpired:
            print(f"⏰ {test_file} timed out")
        except Exception as e:
            print(f"💥 {test_file} crashed: {e}")

if __name__ == "__main__":
    run_optimization_tests()