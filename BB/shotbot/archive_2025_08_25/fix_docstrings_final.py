#!/usr/bin/env python3
"""Fix all remaining docstring issues in test files."""

import ast
from pathlib import Path


def fix_docstring_in_file(filepath: Path) -> bool:
    """Fix malformed docstrings where content is outside triple quotes."""
    try:
        content = filepath.read_text()
        lines = content.splitlines()

        # Try to compile to detect syntax errors
        try:
            ast.parse(content)
            return False  # No syntax error, skip
        except SyntaxError:
            pass  # Has syntax error, try to fix

        # Look for pattern: docstring followed by content that should be inside it
        fixed_lines = []
        in_docstring = False
        docstring_content = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # Start of module docstring
            if i < 5 and line.startswith('"""') and not in_docstring:
                in_docstring = True
                docstring_content = [line]

                # Check if it's a single-line docstring
                if line.count('"""') == 2:
                    in_docstring = False
                    fixed_lines.append(line)
                else:
                    # Multi-line docstring, but might be improperly closed
                    # Look ahead to see if next lines should be in docstring
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j]

                        # If we hit imports or pytestmark, docstring should end
                        if (
                            next_line.startswith("import ")
                            or next_line.startswith("from ")
                            or "pytestmark" in next_line
                            or next_line.startswith("class ")
                            or next_line.startswith("def ")
                        ):
                            # Everything between should be in the docstring
                            for k in range(i + 1, j):
                                if not lines[k].startswith('"""'):
                                    docstring_content.append(lines[k])

                            # Close the docstring
                            docstring_content.append('"""')

                            # Add the properly formatted docstring
                            for doc_line in docstring_content:
                                fixed_lines.append(doc_line)

                            # Skip to the line with imports
                            i = j - 1
                            break

                        # Check if this line closes the docstring
                        if '"""' in next_line:
                            # Normal docstring, just add it
                            for k in range(i, j + 1):
                                fixed_lines.append(lines[k])
                            i = j
                            break

                        j += 1

                    if j >= len(lines):
                        # Reached end without finding imports, just add as is
                        fixed_lines.append(line)
            else:
                # Regular line, add it
                fixed_lines.append(line)

            i += 1

        # Write back if changed
        new_content = "\n".join(fixed_lines)
        if new_content != content:
            filepath.write_text(new_content)
            return True

        return False

    except Exception as e:
        print(f"Error fixing {filepath}: {e}")
        return False


def main():
    """Fix all docstring issues."""

    # Files that likely have docstring issues based on errors
    problem_files = [
        "tests/performance/test_scene_finder_performance.py",
        "tests/performance/test_threede_optimization_coverage.py",
        "tests/unit/test_exr_edge_cases.py",
        "tests/unit/test_exr_parametrized.py",
        "tests/unit/test_failure_tracker.py",
        "tests/unit/test_log_viewer.py",
        "tests/unit/test_main_window_fixed.py",
        "tests/unit/test_memory_manager.py",
        "tests/unit/test_process_pool_manager_simple.py",
        "tests/unit/test_scanner_coverage.py",
        "tests/unit/test_shot_model.py",
        "tests/unit/test_threede_scene_finder.py",
        "tests/unit/test_thumbnail_processor.py",
        "tests/unit/test_thumbnail_processor_thread_safety.py",
        "tests/unit/test_thumbnail_widget_qt.py",
    ]

    for filepath_str in problem_files:
        filepath = Path(filepath_str)
        if filepath.exists():
            if fix_docstring_in_file(filepath):
                print(f"Fixed docstring in {filepath}")

    print("\nDocstring fixes completed!")


if __name__ == "__main__":
    main()
