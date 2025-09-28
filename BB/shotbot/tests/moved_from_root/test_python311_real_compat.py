#!/usr/bin/env python3
"""Real Python 3.11 compatibility test using actual interpreter."""

# Standard library imports
import ast
import sys
from pathlib import Path


def test_file_compatibility(filepath):
    """Test if a Python file is compatible with current interpreter (3.11)."""
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()

        # Try to compile the source code
        compile(source, str(filepath), "exec")

        # Parse AST to check for known compatibility issues
        tree = ast.parse(source)
        issues = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "typing":
                    for alias in node.names:
                        if alias.name == "override":
                            issues.append(
                                f"Line {node.lineno}: imports 'override' from 'typing' (use typing_extensions)"
                            )

        return True, issues

    except SyntaxError as e:
        return False, [f"Syntax error: {e}"]
    except Exception as e:
        return False, [f"Error: {e}"]


def main():
    print("Testing Python 3.11 compatibility with real interpreter...")
    print(f"Using Python {sys.version}")
    print()

    # Get all Python files
    python_files = []
    for pattern in ["*.py", "**/*.py"]:
        for path in Path(".").glob(pattern):
            if (
                "venv" not in str(path)
                and "test_venv" not in str(path)
                and ".pyenv" not in str(path)
                and "build" not in str(path)
            ):
                python_files.append(path)

    print(f"Testing {len(python_files)} Python files...")

    compatible_files = 0
    syntax_errors = []
    compatibility_issues = []

    for filepath in sorted(python_files):
        success, issues = test_file_compatibility(filepath)
        if success:
            compatible_files += 1
            if issues:
                for issue in issues:
                    compatibility_issues.append(f"{filepath}: {issue}")
        else:
            for issue in issues:
                syntax_errors.append(f"{filepath}: {issue}")

    print("\nResults:")
    print(f"✅ Compatible files: {compatible_files}")
    print(f"❌ Files with syntax errors: {len(syntax_errors)}")
    print(f"⚠️  Files with compatibility issues: {len(compatibility_issues)}")

    if syntax_errors:
        print("\n❌ Syntax errors:")
        for error in syntax_errors[:10]:  # Show first 10
            print(f"  {error}")
        if len(syntax_errors) > 10:
            print(f"  ... and {len(syntax_errors) - 10} more")

    if compatibility_issues:
        print("\n⚠️  Compatibility issues:")
        for issue in compatibility_issues:
            print(f"  {issue}")

    if not syntax_errors and not compatibility_issues:
        print(f"\n🎉 All {compatible_files} files are Python 3.11 compatible!")

    return len(syntax_errors) == 0 and len(compatibility_issues) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
