#!/usr/bin/env python3
"""Fix all docstring syntax errors in test files."""

import re
from pathlib import Path

def fix_docstrings(file_path):
    """Fix triple quote syntax errors in a file."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Fix the pattern where docstrings have extra triple quotes at the end
    # Pattern: .""""""  ->  ."""
    fixed_content = re.sub(r'\.""""""', r'."""', content)
    
    if fixed_content != content:
        with open(file_path, 'w') as f:
            f.write(fixed_content)
        return True
    return False

def main():
    """Fix all test files."""
    test_dir = Path(__file__).parent / "tests"
    
    fixed_files = []
    for test_file in test_dir.rglob("*.py"):
        if fix_docstrings(test_file):
            fixed_files.append(test_file)
    
    if fixed_files:
        print(f"Fixed {len(fixed_files)} files:")
        for f in fixed_files:
            print(f"  - {f.relative_to(Path.cwd())}")
    else:
        print("No files needed fixing")

if __name__ == "__main__":
    main()