# ShotBot Test Suite

## 🎯 Overview

The ShotBot test suite contains **775+ tests** across unit, integration, and performance categories. All tests have been fixed and are syntactically correct.

## ⚡ Quick Start (WSL Optimized)

Due to WSL filesystem performance limitations on `/mnt/c`, we provide optimized test runners:

```bash
# Quick validation (no pytest overhead)
python3 quick_test.py

# Run fast tests only (~30 seconds)
python3 run_tests_wsl.py --fast

# Run critical tests only
python3 run_tests_wsl.py --critical

# Test a single file (minimal I/O)
python3 run_tests_wsl.py --file tests/unit/test_utils.py

# Run tests matching a pattern
python3 run_tests_wsl.py -k test_shot_model
```

## 📊 Test Categories

Tests are categorized for efficient execution:

- **Fast Tests (31 files)**: Basic unit tests that run quickly
- **Slow Tests (16 files)**: Integration and threading tests
- **Critical Tests (12 files)**: Core functionality that must work
- **Qt Tests (21 files)**: Tests requiring Qt event loop

Run `python3 mark_test_speed.py` to see the categorization report.

## 🏥 Health Check

Check the test suite status:

```bash
./test_health_check.sh
```

## ⚠️ WSL Performance Note

The test suite experiences significant slowdowns on WSL when accessing Windows drives (`/mnt/c`). This is a known WSL limitation. For best performance:

1. **Run tests during low system load** (evenings/weekends)
2. **Use the optimized runners** provided (`run_tests_wsl.py`)
3. **Test single files** to minimize I/O operations
4. **Consider moving to native Linux filesystem** (`~/projects/`) for 10-100x speedup

## 🔧 Test Infrastructure Status

### ✅ Completed Fixes
- Fixed 52 files with incorrect pytest import ordering
- Fixed 30+ files with malformed docstrings
- Fixed 70+ files with missing imports
- Fixed all type annotation issues
- All 775+ tests are now syntactically correct and collectible

### 📝 Known Issues
- **WSL filesystem performance**: Tests may timeout on `/mnt/c` due to slow I/O
- **Signal race conditions**: Some tests in `test_previous_shots_worker.py` need fixing
- **Excessive mocking**: ~60% of mocks can be replaced with real components per UNIFIED_TESTING_GUIDE

## 🚀 Running Full Test Suite

When system load is low, you can run the full suite:

```bash
# Run all tests in batches (recommended for WSL)
python3 run_tests_wsl.py --all

# Standard pytest (may timeout on WSL)
uv run pytest tests/unit -v --tb=short

# With coverage
uv run pytest tests/ --cov=. --cov-report=html
```

## 📁 Test Structure

```
tests/
├── unit/           # 59 unit test files
├── integration/    # 6 integration test files  
├── performance/    # 4 performance test files
├── threading/      # 2 threading test files
├── conftest.py     # Shared fixtures
└── README.md       # This file
```

## 🛠️ Configuration Files

- `pytest.ini`: Standard pytest configuration
- `pytest_wsl.ini`: Optimized for WSL with reduced I/O
- `pytest_fast.ini`: Minimal configuration for speed
- `pytest_minimal.ini`: Bare minimum for debugging
- `pytest_optimized.ini`: Balanced performance config

## 💡 Tips for Test Development

1. **Mark new tests appropriately**:
   ```python
   pytestmark = [pytest.mark.fast, pytest.mark.unit]
   ```

2. **Follow UNIFIED_TESTING_GUIDE principles**:
   - Test behavior, not implementation
   - Use real components instead of mocks where possible
   - Mock only at system boundaries (subprocess, network, filesystem)

3. **Avoid Qt threading violations**:
   - Never use QPixmap in threads (use QImage instead)
   - Use QSignalSpy for signal testing
   - Set up signal waiters BEFORE triggering actions

4. **Keep tests fast**:
   - Avoid `time.sleep()` - use `qtbot.wait()` or signals
   - Use small test data sets
   - Mock expensive operations (network, large file I/O)

## 📈 Test Coverage

Current test distribution:
- **Unit Tests**: 59 files covering core components
- **Integration Tests**: 6 files testing component interactions
- **Performance Tests**: 4 files for regression testing
- **Threading Tests**: 2 files for concurrency

Target coverage: 80%+ for critical components

## 🔄 Continuous Testing

For development, use the quick test runner:

```bash
# After making changes
python3 quick_test.py  # Instant feedback

# Before committing
python3 run_tests_wsl.py --fast  # ~30 seconds

# Before merging
python3 run_tests_wsl.py --all  # Full validation
```

## 📚 Further Reading

- [UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md](../UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md) - Testing best practices
- [run_tests.py](../run_tests.py) - Standard test runner
- [run_tests_wsl.py](../run_tests_wsl.py) - WSL-optimized test runner