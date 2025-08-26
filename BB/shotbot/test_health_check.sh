#!/bin/bash
# Quick health check for the test suite

echo "🏥 ShotBot Test Suite Health Check"
echo "=================================="
echo ""

# Check Python and pytest
echo "📦 Environment:"
source venv/bin/activate 2>/dev/null || echo "❌ Virtual environment not activated"
python3 --version
python3 -m pytest --version 2>/dev/null || echo "❌ pytest not installed"
echo ""

# Count test files
echo "📊 Test Statistics:"
total_files=$(find tests -name "test_*.py" | wc -l)
unit_files=$(find tests/unit -name "test_*.py" | wc -l)
integration_files=$(find tests/integration -name "test_*.py" | wc -l)
echo "  Total test files: $total_files"
echo "  Unit tests: $unit_files"
echo "  Integration tests: $integration_files"
echo ""

# Check for common issues
echo "⚠️ Checking for common issues:"

# Check for duplicate imports
duplicate_pytest=$(grep -l "^import pytest" tests/unit/*.py | xargs grep -c "^import pytest" | grep -v ":1" | wc -l)
if [ "$duplicate_pytest" -gt 0 ]; then
    echo "  ❌ Found $duplicate_pytest files with duplicate pytest imports"
else
    echo "  ✅ No duplicate pytest imports"
fi

# Check for malformed docstrings
malformed=$(grep -l '""".*"""' tests/unit/*.py | wc -l)
if [ "$malformed" -gt 0 ]; then
    echo "  ⚠️ Found $malformed files with single-line docstrings (consider multi-line)"
else
    echo "  ✅ Docstrings look good"
fi

# Check for missing __init__.py
if [ ! -f "tests/__init__.py" ]; then
    echo "  ⚠️ Missing tests/__init__.py"
else
    echo "  ✅ tests/__init__.py exists"
fi

echo ""

# Try a minimal import test
echo "🔍 Quick Import Test:"
timeout 5 python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from tests.unit.test_utils import TestPathUtils
    print('  ✅ Can import test classes')
except Exception as e:
    print(f'  ❌ Import failed: {e}')
" 2>&1

echo ""

# Suggest next steps
echo "📝 Recommended Commands:"
echo "  1. Check all imports:  python run_tests_wsl.py --check-imports"
echo "  2. Run fast tests:     python run_tests_wsl.py --fast"
echo "  3. Run critical tests: python run_tests_wsl.py --critical"
echo "  4. Categorize tests:   python mark_test_speed.py"
echo ""
echo "💡 Tip: For best performance in WSL, run tests during low system load"
echo "        or consider moving project to ~/projects/ (native Linux filesystem)"