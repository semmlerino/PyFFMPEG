#!/usr/bin/env python3
"""Find Python files using | operator but missing future annotations import."""

import os
import re
from pathlib import Path

def needs_future_import(file_path):
    """Check if file uses | operator with types but lacks future import."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check if already has future import
        if 'from __future__ import annotations' in content:
            return False
        
        # Check if uses | operator with type hints
        # Look for patterns like: str | None, "Type" | None, etc.
        patterns = [
            r':\s*["\']?\w+["\']?\s*\|\s*None',  # : Type | None or : "Type" | None
            r':\s*\w+\s*\|\s*\w+',                # : Type | OtherType
            r'\[\s*["\']?\w+["\']?\s*\|\s*None',  # [Type | None] in generics
        ]
        
        for pattern in patterns:
            if re.search(pattern, content):
                return True
        
        return False
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return False

def main():
    """Find all Python files needing future import."""
    root = Path('/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot')
    
    # Directories to check
    dirs_to_check = [root, root / 'cache', root / 'launcher']
    
    files_needing_import = []
    
    for check_dir in dirs_to_check:
        if not check_dir.exists():
            continue
        
        for py_file in check_dir.glob('*.py'):
            if py_file.name.startswith('test_'):
                continue  # Skip test files for now
            if needs_future_import(py_file):
                files_needing_import.append(py_file)
    
    if files_needing_import:
        print("Files needing 'from __future__ import annotations':")
        for f in files_needing_import:
            print(f"  {f}")
    else:
        print("No files need the future import added.")
    
    return files_needing_import

if __name__ == '__main__':
    main()