#!/usr/bin/env python3
"""Run basedpyright type checking with proper timeout handling."""

import subprocess
import sys
from pathlib import Path


def run_basedpyright():
    """Run basedpyright on main source files."""
    print("🔍 Running basedpyright type checker...")
    
    # Get all main Python files (exclude test files and scripts)
    project_dir = Path(__file__).parent
    
    # Core files to check (excluding tests and utility scripts)
    core_files = [
        "shotbot.py",
        "main_window.py",
        "shot_model.py",
        "shot_grid.py",
        "cache_manager.py",
        "command_launcher.py",
        "launcher_manager.py",
        "launcher_dialog.py",
        "threede_scene_finder.py",
        "threede_scene_model.py",
        "threede_scene_worker.py",
        "threede_shot_grid.py",
        "previous_shots_finder.py",
        "previous_shots_model.py",
        "previous_shots_worker.py",
        "previous_shots_grid.py",
        "shot_info_panel.py",
        "thumbnail_widget.py",
        "utils.py",
        "config.py",
        "type_definitions.py",
        "shot_model_optimized.py",
        "base_shot_model.py",
        "process_pool_manager.py",
    ]
    
    # Add cache directory files
    cache_files = list((project_dir / "cache").glob("*.py"))
    cache_file_names = [str(f) for f in cache_files]
    
    # Add launcher directory files
    launcher_files = list((project_dir / "launcher").glob("*.py"))
    launcher_file_names = [str(f) for f in launcher_files]
    
    # Combine all files
    all_files = core_files + cache_file_names + launcher_file_names
    
    # Run basedpyright with a reasonable timeout
    cmd = ["./venv/bin/basedpyright"] + all_files
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,  # 1 minute timeout
            cwd=project_dir
        )
        
        # Parse output for summary
        lines = result.stdout.split("\n")
        
        # Find error summary
        errors_found = False
        for line in lines:
            if "error" in line.lower() or "warning" in line.lower():
                errors_found = True
                print(line)
        
        if not errors_found and result.returncode == 0:
            print("✅ No type errors found!")
        else:
            print("\n❌ Type errors found. Full output:")
            print(result.stdout)
            if result.stderr:
                print("Stderr:", result.stderr)
        
        return result.returncode
        
    except subprocess.TimeoutExpired:
        print("⏰ Type checking timed out after 60 seconds")
        print("Try running on fewer files or increase timeout")
        return 1
    except FileNotFoundError:
        print("❌ basedpyright not found. Install with: pip install basedpyright")
        return 1
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(run_basedpyright())