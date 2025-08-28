#!/usr/bin/env python3
"""Modernize type hints from Python 3.8 style to Python 3.12 style.

This script updates:
- Optional[T] -> T | None
- Union[A, B] -> A | B
- List[T] -> list[T]
- Dict[K, V] -> dict[K, V]
- Tuple[T, ...] -> tuple[T, ...]
- Set[T] -> set[T]
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


def modernize_type_hints(content: str) -> Tuple[str, List[str]]:
    """Modernize type hints in Python code.
    
    Args:
        content: Original file content
        
    Returns:
        Tuple of (modified content, list of changes made)
    """
    changes = []
    original = content
    
    # Pattern 1: Optional[T] -> T | None
    optional_pattern = re.compile(r'Optional\[([^\[\]]+(?:\[[^\[\]]*\])?[^\[\]]*)\]')
    
    def replace_optional(match):
        inner = match.group(1)
        changes.append(f"Optional[{inner}] -> {inner} | None")
        return f"{inner} | None"
    
    content = optional_pattern.sub(replace_optional, content)
    
    # Pattern 2: Union[A, B] -> A | B (simple two-type unions)
    union_pattern = re.compile(r'Union\[([^,\[\]]+(?:\[[^\[\]]*\])?[^,\[\]]*),\s*([^,\[\]]+(?:\[[^\[\]]*\])?[^,\[\]]*)\]')
    
    def replace_union(match):
        type1 = match.group(1).strip()
        type2 = match.group(2).strip()
        changes.append(f"Union[{type1}, {type2}] -> {type1} | {type2}")
        return f"{type1} | {type2}"
    
    content = union_pattern.sub(replace_union, content)
    
    # Pattern 3: List[T] -> list[T]
    list_pattern = re.compile(r'\bList\[')
    if list_pattern.search(content):
        content = list_pattern.sub('list[', content)
        changes.append("List[...] -> list[...]")
    
    # Pattern 4: Dict[K, V] -> dict[K, V]
    dict_pattern = re.compile(r'\bDict\[')
    if dict_pattern.search(content):
        content = dict_pattern.sub('dict[', content)
        changes.append("Dict[...] -> dict[...]")
    
    # Pattern 5: Tuple[...] -> tuple[...]
    tuple_pattern = re.compile(r'\bTuple\[')
    if tuple_pattern.search(content):
        content = tuple_pattern.sub('tuple[', content)
        changes.append("Tuple[...] -> tuple[...]")
    
    # Pattern 6: Set[T] -> set[T]
    set_pattern = re.compile(r'\bSet\[')
    if set_pattern.search(content):
        content = set_pattern.sub('set[', content)
        changes.append("Set[...] -> set[...]")
    
    # Remove now-unnecessary imports
    if content != original:
        # Remove Optional import if no longer used
        if 'Optional' not in content or 'Optional[' not in content:
            content = re.sub(r',?\s*Optional(?=\s*[,)])', '', content)
            content = re.sub(r'Optional,?\s*', '', content)
            changes.append("Removed unused Optional import")
        
        # Remove Union import if no longer used
        if 'Union' not in content or 'Union[' not in content:
            content = re.sub(r',?\s*Union(?=\s*[,)])', '', content)
            content = re.sub(r'Union,?\s*', '', content)
            changes.append("Removed unused Union import")
        
        # Remove List import if no longer used as type
        if 'List' not in content or 'List[' not in content:
            # But keep if used as variable name or in other contexts
            if not re.search(r'\bList\b(?!\[)', content):
                content = re.sub(r',?\s*List(?=\s*[,)])', '', content)
                content = re.sub(r'List,?\s*', '', content)
                changes.append("Removed unused List import")
        
        # Clean up empty imports
        content = re.sub(r'from typing import\s*\n', '', content)
        content = re.sub(r'from typing import\s*$', '', content, flags=re.MULTILINE)
    
    return content, changes


def process_file(file_path: Path, dry_run: bool = False) -> bool:
    """Process a single Python file.
    
    Args:
        file_path: Path to the Python file
        dry_run: If True, only report changes without modifying
        
    Returns:
        True if changes were made/would be made
    """
    try:
        content = file_path.read_text()
        new_content, changes = modernize_type_hints(content)
        
        if new_content != content:
            print(f"\n{file_path}:")
            for change in changes[:10]:  # Show first 10 changes
                print(f"  - {change}")
            if len(changes) > 10:
                print(f"  ... and {len(changes) - 10} more changes")
            
            if not dry_run:
                file_path.write_text(new_content)
                print("  ✅ Updated")
            else:
                print("  🔍 Would update (dry run)")
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    """Main entry point."""
    dry_run = "--dry-run" in sys.argv
    
    if dry_run:
        print("DRY RUN MODE - No files will be modified\n")
    
    # Find all Python files to process
    project_dir = Path(__file__).parent
    python_files = []
    
    # Core modules to update
    core_modules = [
        "type_definitions.py",
        "shot_model.py", 
        "base_shot_model.py",
        "cache_manager.py",
        "previous_shots_worker.py",
        "accessibility_manager.py",
        "process_pool_manager.py",
    ]
    
    # Add cache directory files
    cache_dir = project_dir / "cache"
    if cache_dir.exists():
        core_modules.extend([f"cache/{f.name}" for f in cache_dir.glob("*.py")])
    
    for module in core_modules:
        file_path = project_dir / module
        if file_path.exists():
            python_files.append(file_path)
    
    print(f"Processing {len(python_files)} files...\n")
    
    updated_count = 0
    for file_path in python_files:
        if process_file(file_path, dry_run):
            updated_count += 1
    
    print(f"\n{'Would update' if dry_run else 'Updated'} {updated_count}/{len(python_files)} files")
    
    if dry_run:
        print("\nRun without --dry-run to apply changes")


if __name__ == "__main__":
    main()