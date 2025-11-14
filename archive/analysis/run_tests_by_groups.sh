#!/bin/bash
# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"

# Diagnostic script to run tests in smaller groups to identify crash sources
# This helps isolate which test combinations cause crashes

set -e

echo "=== Running diagnostic test groups to isolate crashes ==="
echo "Date: $(date)"
echo "Python: $(python3 --version)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to run test group with error handling
run_test_group() {
    local group_name="$1"
    local test_pattern="$2"
    local timeout_seconds="${3:-120}"  # Default 2 minute timeout

    echo -e "\n${YELLOW}=== Testing Group: $group_name ===${NC}"
    echo "Pattern: $test_pattern"
    echo "Timeout: ${timeout_seconds}s"

    if timeout "$timeout_seconds" uv run pytest "$test_pattern" -v --tb=short; then
        echo -e "${GREEN}✓ Group '$group_name' PASSED${NC}"
        return 0
    else
        local exit_code=$?
        echo -e "${RED}✗ Group '$group_name' FAILED (exit code: $exit_code)${NC}"
        if [ $exit_code -eq 124 ]; then
            echo "  → Test group timed out after ${timeout_seconds} seconds"
        elif [ $exit_code -eq 139 ]; then
            echo "  → Segmentation fault (SIGSEGV)"
        elif [ $exit_code -eq 134 ]; then
            echo "  → Abort signal (SIGABRT)"
        fi
        return $exit_code
    fi
}

# Start with individual problematic test files
echo -e "\n${YELLOW}Phase 1: Individual Test Files${NC}"

run_test_group "Cache Manager Tests" "tests/unit/test_cache_manager.py" 60
run_test_group "MainWindow Unit Tests" "tests/unit/test_main_window.py" 60
run_test_group "MainWindow Fixed Tests" "tests/unit/test_main_window_fixed.py" 60
run_test_group "MainWindow Widgets Tests" "tests/unit/test_main_window_widgets.py" 60

# Test pairs that might interact
echo -e "\n${YELLOW}Phase 2: Test File Pairs${NC}"

run_test_group "Cache + MainWindow" "tests/unit/test_cache_manager.py tests/unit/test_main_window.py" 90
run_test_group "MainWindow Unit + Fixed" "tests/unit/test_main_window.py tests/unit/test_main_window_fixed.py" 90
run_test_group "Cache + EXR Tests" "tests/unit/test_cache_manager.py tests/unit/test_exr_edge_cases.py" 90

# Test integration tests individually
echo -e "\n${YELLOW}Phase 3: Individual Integration Tests${NC}"

run_test_group "Main Window Complete Integration" "tests/integration/test_main_window_complete.py" 120
run_test_group "3DE Parallel Discovery" "tests/integration/test_threede_parallel_discovery.py" 120
run_test_group "User Workflows" "tests/integration/test_user_workflows.py" 120
run_test_group "Main Window Coordination" "tests/integration/test_main_window_coordination.py" 120

# Test categories
echo -e "\n${YELLOW}Phase 4: Test Categories${NC}"

run_test_group "All Unit Tests" "tests/unit/" 180
run_test_group "All Integration Tests" "tests/integration/" 180
run_test_group "All Thread Tests" "tests/thread_tests/" 120

# Test progressively larger combinations
echo -e "\n${YELLOW}Phase 5: Progressive Combinations${NC}"

run_test_group "Unit + Integration (Small)" "tests/unit/test_cache_manager.py tests/integration/test_main_window_complete.py" 120
run_test_group "Core MainWindow Tests" "tests/unit/test_main_window*.py" 150
run_test_group "All MainWindow Related" "tests/unit/test_main_window*.py tests/integration/test_main_window*.py" 200

echo -e "\n${YELLOW}=== Diagnostic Summary ===${NC}"
echo "If specific groups fail, that indicates where the crash is occurring."
echo "If all individual tests pass but combinations fail, it's a resource accumulation issue."
echo "If tests timeout, it's likely a deadlock or infinite loop."
echo "If tests segfault/abort, it's likely a Qt resource management issue."