#!/usr/bin/env python3
"""Modernize all type hints in the codebase to Python 3.10+ syntax.

This script:
1. Adds 'from __future__ import annotations' where needed
2. Converts Optional[T] to T | None
3. Converts Union[A, B] to A | B
4. Converts List[T] to list[T], Dict[K, V] to dict[K, V], etc.
5. Removes unnecessary typing imports
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


def needs_future_import(content: str) -> bool:
    """Check if file needs future annotations import."""
    # Check if it uses | syntax or lowercase generics
    patterns = [
        r'\w+\s*\|\s*None',  # X | None
        r'\w+\s*\|\s*\w+',    # X | Y
        r'list\[',            # list[T]
        r'dict\[',            # dict[K, V]
        r'set\[',             # set[T]
        r'tuple\[',           # tuple[T, ...]
    ]
    return any(re.search(pattern, content) for pattern in patterns)


def has_future_import(content: str) -> bool:
    """Check if file already has future annotations import."""
    return 'from __future__ import annotations' in content


def add_future_import(content: str) -> str:
    """Add future annotations import after module docstring and before other imports."""
    lines = content.splitlines()
    
    # Find where to insert
    insert_idx = 0
    in_docstring = False
    docstring_char = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Handle docstrings
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_char = '"""' if stripped.startswith('"""') else "'''"
                if stripped.count(docstring_char) == 2:
                    # Single line docstring
                    insert_idx = i + 1
                else:
                    # Multi-line docstring
                    in_docstring = True
            elif stripped.startswith('#'):
                # Skip comments
                continue
            elif stripped and not stripped.startswith('from __future__'):
                # First non-comment, non-docstring, non-future import line
                insert_idx = i
                break
        else:
            # In multi-line docstring
            if docstring_char in line:
                in_docstring = False
                insert_idx = i + 1
    
    # Insert the import
    if insert_idx < len(lines) and lines[insert_idx].strip():
        lines.insert(insert_idx, '')
    lines.insert(insert_idx, 'from __future__ import annotations')
    if insert_idx == 0 or (insert_idx > 0 and lines[insert_idx - 1].strip()):
        lines.insert(insert_idx, '')
    
    return '\n'.join(lines)


def modernize_type_hints(content: str) -> tuple[str, list[str]]:
    """Modernize type hints in the content."""
    changes = []
    
    # Convert Optional[T] to T | None
    pattern = r'Optional\[([^\]]+)\]'
    new_content = re.sub(pattern, lambda m: f"{m.group(1)} | None", content)
    if new_content != content:
        changes.append("Converted Optional[T] to T | None")
        content = new_content
    
    # Convert Union[A, B] to A | B (handle nested brackets)
    def replace_union(match):
        args = match.group(1)
        # Simple split by comma at top level
        depth = 0
        parts = []
        current = []
        for char in args:
            if char == '[':
                depth += 1
            elif char == ']':
                depth -= 1
            elif char == ',' and depth == 0:
                parts.append(''.join(current).strip())
                current = []
                continue
            current.append(char)
        if current:
            parts.append(''.join(current).strip())
        return ' | '.join(parts)
    
    pattern = r'Union\[([^\]]+(?:\[[^\]]*\])*[^\]]*)\]'
    new_content = re.sub(pattern, replace_union, content)
    if new_content != content:
        changes.append("Converted Union[A, B] to A | B")
        content = new_content
    
    # Convert List, Dict, Set, Tuple to lowercase
    replacements = [
        (r'\bList\[', 'list['),
        (r'\bDict\[', 'dict['),
        (r'\bSet\[', 'set['),
        (r'\bTuple\[', 'tuple['),
        (r'\bFrozenSet\[', 'frozenset['),
        (r'\bDeque\[', 'deque['),
    ]
    
    for pattern, replacement in replacements:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            changes.append(f"Converted {pattern.strip('\\b[')} to {replacement.strip('[')}")
            content = new_content
    
    return content, changes


def clean_typing_imports(content: str) -> tuple[str, list[str]]:
    """Remove unnecessary typing imports after modernization."""
    changes = []
    
    # Parse AST to understand imports
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content, changes
    
    typing_imports_to_remove = {
        'Optional', 'Union', 'List', 'Dict', 'Set', 'Tuple', 'FrozenSet', 'Deque'
    }
    
    lines = content.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'typing':
            import_line_num = node.lineno - 1
            import_line = lines[import_line_num]
            
            # Check each imported name
            remaining_names = []
            removed_names = []
            for alias in node.names:
                name = alias.name
                if name not in typing_imports_to_remove:
                    remaining_names.append(name)
                else:
                    # Check if it's still used (not in type hints)
                    pattern = rf'\b{name}\b(?!\[)'
                    if re.search(pattern, content):
                        remaining_names.append(name)
                    else:
                        removed_names.append(name)
            
            if removed_names:
                if remaining_names:
                    # Update the import line
                    new_import = f"from typing import {', '.join(remaining_names)}"
                    lines[import_line_num] = new_import
                    changes.append(f"Removed {', '.join(removed_names)} from typing imports")
                else:
                    # Remove the entire import line
                    lines[import_line_num] = ''
                    changes.append(f"Removed entire typing import line")
    
    return '\n'.join(lines), changes


def process_file(filepath: Path, dry_run: bool = False) -> list[str]:
    """Process a single Python file."""
    try:
        content = filepath.read_text()
        original_content = content
        all_changes = []
        
        # Skip if it's a test file or already processed
        if 'from __future__ import annotations' in content and not re.search(r'Optional\[|Union\[|List\[|Dict\[', content):
            return []
        
        # Modernize type hints
        content, changes = modernize_type_hints(content)
        all_changes.extend(changes)
        
        # Add future import if needed and not present
        if needs_future_import(content) and not has_future_import(content):
            content = add_future_import(content)
            all_changes.append("Added 'from __future__ import annotations'")
        
        # Clean up typing imports
        content, changes = clean_typing_imports(content)
        all_changes.extend(changes)
        
        # Write back if changed
        if content != original_content and not dry_run:
            filepath.write_text(content)
            
        return all_changes
    except Exception as e:
        return [f"ERROR: {e}"]


def main():
    """Main entry point."""
    import sys
    
    dry_run = '--dry-run' in sys.argv
    
    # Find all Python files
    project_dir = Path(__file__).parent
    
    # Get ALL Python files recursively (including tests directory)
    python_files = list(project_dir.rglob('*.py'))
    
    # Exclude this script and other generated scripts
    exclude_files = {
        'modernize_all_type_hints.py',
        'modernize_type_hints.py', 
        'fix_unknown_type_cascade.py',
        'find_missing_future_imports.py',
        'add_future_imports.py',
        'profile_startup.py',
        'analyze_thread_safety.py',
        'generate_coverage_report.py'
    }
    
    python_files = [
        f for f in python_files 
        if f.name not in exclude_files
        and 'venv' not in str(f)  # Skip virtual env
        and '__pycache__' not in str(f)  # Skip cache
    ]
    
    print(f"{'DRY RUN: ' if dry_run else ''}Modernizing {len(python_files)} Python files...")
    
    modified_count = 0
    for filepath in sorted(python_files):
        changes = process_file(filepath, dry_run)
        if changes:
            modified_count += 1
            print(f"\n{filepath.relative_to(project_dir)}:")
            for change in changes:
                print(f"  - {change}")
    
    print(f"\n{'Would modify' if dry_run else 'Modified'} {modified_count}/{len(python_files)} files")
    
    if dry_run:
        print("\nRun without --dry-run to apply changes")


if __name__ == "__main__":
    main()