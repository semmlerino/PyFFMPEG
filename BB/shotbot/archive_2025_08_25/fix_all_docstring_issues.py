#!/usr/bin/env python3
"""Fix all docstring issues in test files."""

import re
from pathlib import Path

def fix_docstring_issues(file_path):
    """Fix various docstring issues in a file."""
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    fixed_lines = []
    i = 0
    changes_made = False
    
    while i < len(lines):
        line = lines[i]
        
        # Check for patterns that need fixing
        # Pattern 1: Missing opening triple quote (line has just text and closing triple quotes)
        if i > 0 and '    ' in lines[i-1] and not '"""' in lines[i-1]:
            # Check if current line looks like a docstring without opening quotes
            match = re.match(r'^(\s+)([^"#\s].+)"""$', line)
            if match:
                indent = match.group(1)
                text = match.group(2)
                fixed_lines.append(f'{indent}"""{text}"""\n')
                changes_made = True
                i += 1
                continue
        
        # Pattern 2: Line that ends with a period and has """ but missing opening quotes
        match = re.match(r'^(\s+)([A-Z][^"]*\.)"""$', line)
        if match:
            indent = match.group(1)
            text = match.group(2)
            fixed_lines.append(f'{indent}"""{text}"""\n')
            changes_made = True
            i += 1
            continue
        
        # Pattern 3: Line with word followed by tests or similar and .""" at end
        match = re.match(r'^(\s+)(\w+\s+[^"]+\.)"""$', line)
        if match:
            indent = match.group(1)
            text = match.group(2)
            fixed_lines.append(f'{indent}"""{text}"""\n')
            changes_made = True
            i += 1
            continue
            
        fixed_lines.append(line)
        i += 1
    
    if changes_made:
        with open(file_path, 'w') as f:
            f.writelines(fixed_lines)
        return True
    return False

def main():
    """Fix all test files."""
    test_dir = Path(__file__).parent / "tests"
    
    fixed_files = []
    for test_file in test_dir.rglob("*.py"):
        if fix_docstring_issues(test_file):
            fixed_files.append(test_file)
    
    if fixed_files:
        print(f"Fixed {len(fixed_files)} files:")
        for f in fixed_files:
            print(f"  - {f.relative_to(Path.cwd())}")
    else:
        print("No files needed fixing")

if __name__ == "__main__":
    main()