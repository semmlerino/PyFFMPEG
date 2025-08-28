#!/usr/bin/env python3
"""Clean up unnecessary typing imports after modernization to Python 3.10+ syntax."""

from __future__ import annotations

import ast
import re
from pathlib import Path


def should_remove_import(name: str, content: str) -> bool:
    """Check if a typing import can be safely removed."""
    
    # These can be removed if using modern syntax
    removable = {
        'List': r'\bList\b(?!\[)',  # List not followed by [
        'Dict': r'\bDict\b(?!\[)',  # Dict not followed by [
        'Set': r'\bSet\b(?!\[)',   # Set not followed by [
        'Tuple': r'\bTuple\b(?!\[)', # Tuple not followed by [
        'Optional': r'\bOptional\b(?!\[)', # Optional not followed by [
        'Union': r'\bUnion\b(?!\[)', # Union not followed by [
        'FrozenSet': r'\bFrozenSet\b(?!\[)',
        'Deque': r'\bDeque\b(?!\[)',
    }
    
    if name not in removable:
        return False
    
    # Check if it's still used outside of type hints
    pattern = removable[name]
    return not re.search(pattern, content)


def clean_file(filepath: Path) -> bool:
    """Clean unnecessary typing imports from a file."""
    try:
        content = filepath.read_text()
        original_content = content
        
        # Parse to find typing imports
        tree = ast.parse(content)
        lines = content.splitlines()
        modified = False
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == 'typing':
                line_num = node.lineno - 1
                if line_num >= len(lines):
                    continue
                    
                import_line = lines[line_num]
                
                # Get all imported names
                imported_names = []
                remaining_names = []
                
                for alias in node.names:
                    name = alias.name
                    if should_remove_import(name, content):
                        # Can be removed
                        pass
                    else:
                        remaining_names.append(name)
                    imported_names.append(name)
                
                # If something was removed
                if len(remaining_names) < len(imported_names):
                    modified = True
                    if remaining_names:
                        # Update the import line
                        lines[line_num] = f"from typing import {', '.join(remaining_names)}"
                    else:
                        # Remove the entire line
                        lines[line_num] = ''
        
        if modified:
            # Clean up empty lines
            cleaned_lines = []
            prev_empty = False
            for line in lines:
                if line.strip() == '':
                    if not prev_empty:
                        cleaned_lines.append(line)
                    prev_empty = True
                else:
                    cleaned_lines.append(line)
                    prev_empty = False
            
            new_content = '\n'.join(cleaned_lines)
            
            # Ensure file ends with newline if original did
            if original_content.endswith('\n') and not new_content.endswith('\n'):
                new_content += '\n'
            
            if new_content != original_content:
                filepath.write_text(new_content)
                return True
                
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
    
    return False


def main():
    """Main entry point."""
    import sys
    
    dry_run = '--dry-run' in sys.argv
    
    # Get all Python files in main directory and specific subdirs
    project_dir = Path(__file__).parent
    
    python_files = list(project_dir.glob('*.py'))
    for subdir in ['cache', 'launcher']:
        subdir_path = project_dir / subdir
        if subdir_path.exists():
            python_files.extend(subdir_path.glob('*.py'))
    
    # Exclude this script and test files
    python_files = [
        f for f in python_files
        if f.name != 'cleanup_typing_imports.py'
        and 'test' not in str(f)
        and 'venv' not in str(f)
    ]
    
    print(f"{'DRY RUN: ' if dry_run else ''}Cleaning typing imports from {len(python_files)} files...")
    
    cleaned_count = 0
    for filepath in sorted(python_files):
        if dry_run:
            # Just check if file needs cleaning
            content = filepath.read_text()
            if re.search(r'from typing import.*(List|Dict|Set|Tuple|Optional|Union)', content):
                cleaned_count += 1
                print(f"Would clean: {filepath.relative_to(project_dir)}")
        else:
            if clean_file(filepath):
                cleaned_count += 1
                print(f"Cleaned: {filepath.relative_to(project_dir)}")
    
    print(f"\n{'Would clean' if dry_run else 'Cleaned'} {cleaned_count}/{len(python_files)} files")
    
    if dry_run:
        print("\nRun without --dry-run to apply changes")


if __name__ == "__main__":
    main()