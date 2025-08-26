#!/usr/bin/env python3
"""Fix multi-line string assignment issues in test files."""

import re
from pathlib import Path

def fix_multiline_strings(file_path):
    """Fix multi-line string issues in a file."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    changes_made = False
    
    # Pattern 1: Fix mangled multi-line string assignments
    # """variable = """ -> variable = """
    pattern1 = re.compile(r'"""(\w+)\s*=\s*"""')
    if pattern1.search(content):
        content = pattern1.sub(r'\1 = """', content)
        changes_made = True
    
    # Pattern 2: Fix closing quotes on wrong line
    # .strip()""" -> """.strip()
    pattern2 = re.compile(r'\.strip\(\)"""')
    if pattern2.search(content):
        content = pattern2.sub(r'""".strip()', content)
        changes_made = True
    
    # Pattern 3: Fix multiple consecutive triple quotes
    # """""""" -> """
    pattern3 = re.compile(r'"""{2,}')
    if pattern3.search(content):
        content = pattern3.sub('"""', content)
        changes_made = True
    
    # Pattern 4: Fix misplaced triple quotes in assignments
    # output1 = workspace -> output1 = """workspace
    lines = content.split('\n')
    fixed_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check for pattern like: """variable = content"""
        match = re.match(r'^(\s+)"""(\w+)\s*=\s*(.*)"""$', line)
        if match:
            indent = match.group(1)
            var_name = match.group(2)
            content_start = match.group(3)
            fixed_lines.append(f'{indent}{var_name} = """{content_start}"""')
            changes_made = True
        # Check for pattern like: variable = content""" (missing opening quotes)
        elif re.match(r'^(\s+)(\w+)\s*=\s*([^"]+)"""$', line):
            match = re.match(r'^(\s+)(\w+)\s*=\s*([^"]+)"""$', line)
            indent = match.group(1)
            var_name = match.group(2)
            content_val = match.group(3)
            fixed_lines.append(f'{indent}{var_name} = """{content_val}"""')
            changes_made = True
        else:
            fixed_lines.append(line)
        i += 1
    
    if changes_made:
        content = '\n'.join(fixed_lines)
        with open(file_path, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    """Fix all test files."""
    test_dir = Path(__file__).parent / "tests"
    
    fixed_files = []
    for test_file in test_dir.rglob("*.py"):
        if fix_multiline_strings(test_file):
            fixed_files.append(test_file)
    
    if fixed_files:
        print(f"Fixed {len(fixed_files)} files:")
        for f in fixed_files:
            print(f"  - {f.relative_to(Path.cwd())}")
    else:
        print("No files needed fixing")

if __name__ == "__main__":
    main()