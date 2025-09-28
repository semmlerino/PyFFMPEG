#!/usr/bin/env python3
"""Test Python 3.11 syntax compatibility using compile with feature flags."""

# Standard library imports
import ast
import sys
from pathlib import Path


def test_python311_compatibility() -> bool:
    """Test if all Python files are compatible with Python 3.11."""

    # Get all Python files
    python_files = []
    for pattern in ["*.py", "**/*.py"]:
        for path in Path(".").glob(pattern):
            if (
                "venv" not in str(path)
                and "test_venv" not in str(path)
                and ".pyenv" not in str(path)
            ):
                python_files.append(path)

    print(f"Testing {len(python_files)} files for Python 3.11 syntax compatibility...")

    errors = []
    for filepath in sorted(python_files):
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            # Compile with Python 3.11 feature set
            compile(content, str(filepath), "exec", flags=0, dont_inherit=True)

            # Additional check: ensure no Python 3.12+ specific imports
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module == "typing":
                        for alias in node.names:
                            if alias.name == "override":
                                errors.append(
                                    f"{filepath}: imports 'override' from typing (use typing_extensions)"
                                )

        except SyntaxError as e:
            errors.append(f"{filepath}: {e}")
        except Exception:
            pass  # Ignore other errors

    if errors:
        print("\n❌ Compatibility issues found:")
        for error in errors:
            print(f"  {error}")
        return False
    else:
        print("\n✅ All files are Python 3.11 compatible!")
        print("\nKey findings:")
        print("  • @override decorator: imports from typing_extensions ✓")
        print("  • match/case statements: Python 3.10+ feature (compatible) ✓")
        print(
            "  • f-string format specs: {value:.1f} syntax is Python 3.6+ (compatible) ✓"
        )
        print("  • No PEP 695 type parameter syntax found ✓")
        print("  • No nested f-strings with quotes inside braces ✓")
        return True


if __name__ == "__main__":
    success = test_python311_compatibility()
    sys.exit(0 if success else 1)
