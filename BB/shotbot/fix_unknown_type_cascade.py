#!/usr/bin/env python3
"""Fix Unknown type cascade by adding proper type annotations to json operations.

This script adds explicit type annotations to json.load/loads calls to prevent
the Unknown type from propagating through the codebase.
"""

import re
from pathlib import Path
from typing import List, Tuple

def fix_json_annotations(content: str, file_path: Path) -> Tuple[str, List[str]]:
    """Add type annotations to json.load/loads calls.
    
    Args:
        content: File content
        file_path: Path to the file being processed
        
    Returns:
        Tuple of (modified content, list of changes made)
    """
    changes = []
    original = content
    
    # Pattern 1: json.load(f) without type annotation
    # Match json.load(f) where the result is assigned to a variable without annotation
    pattern1 = re.compile(
        r'^(\s*)([\w_]+)\s*=\s*json\.load\(([^)]+)\)$',
        re.MULTILINE
    )
    
    def replace_json_load(match):
        indent = match.group(1)
        var_name = match.group(2)
        file_var = match.group(3)
        
        # Determine the appropriate type based on variable name and context
        if 'launcher' in var_name.lower():
            type_hint = "dict[str, Any]"
        elif 'config' in var_name.lower() or 'settings' in var_name.lower():
            type_hint = "dict[str, Any]"
        elif 'data' in var_name.lower():
            type_hint = "dict[str, Any]"
        else:
            type_hint = "dict[str, Any]"
        
        changes.append(f"Added type annotation to {var_name} = json.load()")
        return f"{indent}{var_name}: {type_hint} = json.load({file_var})"
    
    content = pattern1.sub(replace_json_load, content)
    
    # Pattern 2: json.loads(string) without type annotation
    pattern2 = re.compile(
        r'^(\s*)([\w_]+)\s*=\s*json\.loads\(([^)]+)\)$',
        re.MULTILINE
    )
    
    def replace_json_loads(match):
        indent = match.group(1)
        var_name = match.group(2)
        string_var = match.group(3)
        
        type_hint = "dict[str, Any]"
        changes.append(f"Added type annotation to {var_name} = json.loads()")
        return f"{indent}{var_name}: {type_hint} = json.loads({string_var})"
    
    content = pattern2.sub(replace_json_loads, content)
    
    # Pattern 3: for loops over dict.items() without type annotation
    pattern3 = re.compile(
        r'^(\s*)for\s+([\w_]+),\s*([\w_]+)\s+in\s+([\w_]+)\.items\(\):$',
        re.MULTILINE
    )
    
    # Check if we need to add typing imports
    if content != original and 'from typing import' not in content:
        # Add Any import if not present
        if 'import json' in content:
            content = content.replace(
                'import json',
                'import json\nfrom typing import Any',
                1
            )
            changes.append("Added 'from typing import Any' import")
    elif content != original and 'Any' not in content:
        # Add Any to existing typing imports
        typing_import_pattern = re.compile(r'from typing import ([^\n]+)')
        match = typing_import_pattern.search(content)
        if match:
            imports = match.group(1)
            if 'Any' not in imports:
                new_imports = imports.rstrip() + ', Any'
                content = content.replace(
                    f'from typing import {imports}',
                    f'from typing import {new_imports}',
                    1
                )
                changes.append("Added Any to typing imports")
    
    return content, changes


def fix_collection_operations(content: str) -> Tuple[str, List[str]]:
    """Add type annotations to collection operations that propagate Unknown.
    
    Args:
        content: File content
        
    Returns:
        Tuple of (modified content, list of changes made)
    """
    changes = []
    
    # Pattern: results = [] -> results: list[SomeType] = []
    empty_list_pattern = re.compile(
        r'^(\s*)([\w_]+)\s*=\s*\[\]$',
        re.MULTILINE
    )
    
    def replace_empty_list(match):
        indent = match.group(1)
        var_name = match.group(2)
        
        # Determine appropriate type based on variable name
        if 'shot' in var_name.lower():
            type_hint = "list[Shot]"
        elif 'scene' in var_name.lower():
            type_hint = "list[ThreeDESceneDict]"
        elif 'launcher' in var_name.lower():
            type_hint = "list[LauncherDict]"
        elif 'result' in var_name.lower():
            type_hint = "list[Any]"
        elif 'path' in var_name.lower():
            type_hint = "list[Path]"
        elif 'file' in var_name.lower():
            type_hint = "list[Path]"
        else:
            type_hint = "list[Any]"
        
        changes.append(f"Added type annotation to {var_name} = []")
        return f"{indent}{var_name}: {type_hint} = []"
    
    content = empty_list_pattern.sub(replace_empty_list, content)
    
    # Pattern: results = {} -> results: dict[str, Any] = {}
    empty_dict_pattern = re.compile(
        r'^(\s*)([\w_]+)\s*=\s*\{\}$',
        re.MULTILINE
    )
    
    def replace_empty_dict(match):
        indent = match.group(1)
        var_name = match.group(2)
        
        # Determine appropriate type based on variable name
        if 'cache' in var_name.lower():
            type_hint = "dict[str, Any]"
        elif 'config' in var_name.lower():
            type_hint = "dict[str, Any]"
        elif 'data' in var_name.lower():
            type_hint = "dict[str, Any]"
        elif 'result' in var_name.lower():
            type_hint = "dict[str, Any]"
        else:
            type_hint = "dict[str, Any]"
        
        changes.append(f"Added type annotation to {var_name} = " + "{}")
        return f"{indent}{var_name}: {type_hint} = " + "{}"
    
    content = empty_dict_pattern.sub(replace_empty_dict, content)
    
    return content, changes


def process_file(file_path: Path, dry_run: bool = False) -> bool:
    """Process a single Python file to fix Unknown type cascade.
    
    Args:
        file_path: Path to the Python file
        dry_run: If True, only report changes without modifying
        
    Returns:
        True if changes were made/would be made
    """
    try:
        content = file_path.read_text()
        
        # Apply JSON annotation fixes
        new_content, json_changes = fix_json_annotations(content, file_path)
        
        # Apply collection operation fixes
        new_content, collection_changes = fix_collection_operations(new_content)
        
        all_changes = json_changes + collection_changes
        
        if new_content != content:
            print(f"\n{file_path}:")
            for change in all_changes[:10]:
                print(f"  - {change}")
            if len(all_changes) > 10:
                print(f"  ... and {len(all_changes) - 10} more changes")
            
            if not dry_run:
                file_path.write_text(new_content)
                print(f"  ✅ Updated")
            else:
                print(f"  🔍 Would update (dry run)")
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    """Main entry point."""
    import sys
    
    dry_run = "--dry-run" in sys.argv
    
    if dry_run:
        print("DRY RUN MODE - No files will be modified\n")
    
    project_dir = Path(__file__).parent
    
    # Files with json operations that need fixing
    target_files = [
        "cache/storage_backend.py",
        "launcher/config_manager.py",
        "settings_manager.py",
        "settings_dialog.py",
    ]
    
    # Also scan for other Python files with json operations
    additional_files = []
    for py_file in project_dir.glob("*.py"):
        if py_file.name not in ["fix_unknown_type_cascade.py", "modernize_type_hints.py"]:
            content = py_file.read_text()
            if "json.load" in content and str(py_file.relative_to(project_dir)) not in target_files:
                additional_files.append(str(py_file.relative_to(project_dir)))
    
    # Combine all files
    all_files = target_files + additional_files
    python_files = []
    
    for file_path in all_files:
        full_path = project_dir / file_path
        if full_path.exists():
            python_files.append(full_path)
    
    print(f"Processing {len(python_files)} files with json operations...\n")
    
    updated_count = 0
    for file_path in python_files:
        if process_file(file_path, dry_run):
            updated_count += 1
    
    print(f"\n{'Would update' if dry_run else 'Updated'} {updated_count}/{len(python_files)} files")
    
    if dry_run:
        print("\nRun without --dry-run to apply changes")


if __name__ == "__main__":
    main()