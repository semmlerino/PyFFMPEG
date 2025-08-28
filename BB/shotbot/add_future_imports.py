#!/usr/bin/env python3
"""Add 'from __future__ import annotations' to files that need it."""

import re
from pathlib import Path

FILES = [
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/accessibility_manager.py',
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/cache_manager.py',
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/previous_shots_worker.py',
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/process_pool_manager.py',
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/cache/cache_validator.py',
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/cache/failure_tracker.py',
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/cache/memory_manager.py',
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/cache/shot_cache.py',
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/cache/threede_cache.py',
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/cache/thumbnail_loader.py',
    '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/cache/thumbnail_processor.py',
]

def add_future_import(file_path):
    """Add future annotations import after module docstring."""
    file_path = Path(file_path)
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Find where to insert the import
    insert_index = 0
    in_docstring = False
    docstring_char = None
    
    for i, line in enumerate(lines):
        # Check for docstring start
        if not in_docstring:
            if line.strip().startswith('"""'):
                in_docstring = True
                docstring_char = '"""'
                if line.count('"""') >= 2:
                    # Single line docstring
                    in_docstring = False
                    insert_index = i + 1
                    break
            elif line.strip().startswith("'''"):
                in_docstring = True
                docstring_char = "'''"
                if line.count("'''") >= 2:
                    # Single line docstring
                    in_docstring = False
                    insert_index = i + 1
                    break
            elif not line.strip() or line.strip().startswith('#'):
                # Skip empty lines and comments at the beginning
                continue
            else:
                # No docstring, insert at the beginning after shebang/encoding
                if line.strip().startswith('#!') or 'coding' in line:
                    continue
                insert_index = i
                break
        else:
            # In docstring, check for end
            if docstring_char in line:
                in_docstring = False
                insert_index = i + 1
                break
    
    # Add the import
    import_line = 'from __future__ import annotations\n'
    
    # Check if next line is blank, if not add one
    if insert_index < len(lines) and lines[insert_index].strip():
        import_line = '\n' + import_line
    
    lines.insert(insert_index, import_line)
    
    # Write back
    with open(file_path, 'w') as f:
        f.writelines(lines)
    
    print(f"✓ Added future import to {file_path.name}")

def main():
    """Add future imports to all files."""
    for file_path in FILES:
        try:
            add_future_import(file_path)
        except Exception as e:
            print(f"✗ Error processing {file_path}: {e}")

if __name__ == '__main__':
    main()