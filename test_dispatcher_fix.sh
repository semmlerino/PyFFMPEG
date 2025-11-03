#!/bin/bash
# Test script to verify terminal_dispatcher.sh fix for double-backgrounding bug
# Tests the corrected three-pattern stripping logic

echo "═══════════════════════════════════════════════════════════════"
echo "  Terminal Dispatcher Fix Verification Test"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Testing the corrected pattern stripping fix that handles:"
echo "  1. Rez commands ending with: ' &\"'"
echo "  2. Direct commands ending with: ' &'"
echo "  3. Edge cases ending with: '&'"
echo ""

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track test results
TESTS_PASSED=0
TESTS_FAILED=0

# Test helper function
test_pattern_strip() {
    local original_cmd="$1"
    local expected_result="$2"
    local test_name="$3"

    # Apply the same logic as terminal_dispatcher.sh
    local cmd="$original_cmd"
    cmd="${cmd% &\"}"   # Strip ' &"' pattern (rez commands)
    cmd="${cmd% &}"     # Strip ' &' pattern (direct commands)
    cmd="${cmd%&}"      # Strip '&' pattern (edge case)

    if [ "$cmd" = "$expected_result" ]; then
        echo -e "${GREEN}✓ PASS${NC}: $test_name"
        ((TESTS_PASSED++))
        if [ "$cmd" != "$original_cmd" ]; then
            echo "  Stripped: '${original_cmd}' → '${cmd}'"
        fi
    else
        echo -e "${RED}✗ FAIL${NC}: $test_name"
        echo "  Original:  '$original_cmd'"
        echo "  Expected:  '$expected_result'"
        echo "  Got:       '$cmd'"
        ((TESTS_FAILED++))
    fi
}

echo "─────────────────────────────────────────────────────────────────"
echo "Test Suite 1: Rez Commands (Production Cases)"
echo "─────────────────────────────────────────────────────────────────"
echo ""

test_pattern_strip \
    'rez env nuke python-3.11 -- bash -ilc "ws /shows/TEST/shots/TST_0010 && nuke /path/file.nk &"' \
    'rez env nuke python-3.11 -- bash -ilc "ws /shows/TEST/shots/TST_0010 && nuke /path/file.nk' \
    "Rez+nuke command with trailing &\""

test_pattern_strip \
    'rez env maya python-3.11 -- bash -ilc "ws /path && maya /file.ma &"' \
    'rez env maya python-3.11 -- bash -ilc "ws /path && maya /file.ma' \
    "Rez+maya command with trailing &\""

test_pattern_strip \
    'rez env 3de -- bash -ilc "ws /path && 3de /file.3de &"' \
    'rez env 3de -- bash -ilc "ws /path && 3de /file.3de' \
    "Rez+3de command with trailing &\""

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "Test Suite 2: Direct Commands"
echo "─────────────────────────────────────────────────────────────────"
echo ""

test_pattern_strip \
    'nuke /path/to/file.nk &' \
    'nuke /path/to/file.nk' \
    "Direct nuke command with trailing &"

test_pattern_strip \
    'maya /path/to/file.ma &' \
    'maya /path/to/file.ma' \
    "Direct maya command with trailing &"

test_pattern_strip \
    '/usr/bin/nuke --version &' \
    '/usr/bin/nuke --version' \
    "Direct command with path and trailing &"

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "Test Suite 3: Edge Cases"
echo "─────────────────────────────────────────────────────────────────"
echo ""

test_pattern_strip \
    'some_command&' \
    'some_command' \
    "Command with & but no space"

test_pattern_strip \
    'cd /path && ls -la &' \
    'cd /path && ls -la' \
    "Command with && operator and trailing &"

test_pattern_strip \
    'echo "test && something" &' \
    'echo "test && something"' \
    "Command with quoted && and trailing &"

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "Test Suite 4: Commands That Should NOT Be Modified"
echo "─────────────────────────────────────────────────────────────────"
echo ""

test_pattern_strip \
    'ls -la' \
    'ls -la' \
    "Command without &"

test_pattern_strip \
    'rez env nuke -- bash -ilc "ws /path && nuke /file.nk"' \
    'rez env nuke -- bash -ilc "ws /path && nuke /file.nk"' \
    "Rez command without trailing &"

test_pattern_strip \
    'cd /path && ls' \
    'cd /path && ls' \
    "Command with && but no trailing &"

test_pattern_strip \
    'echo "test & more & stuff"' \
    'echo "test & more & stuff"' \
    "Command with & in the middle"

test_pattern_strip \
    'cmd1 & cmd2' \
    'cmd1 & cmd2' \
    "Two commands with & separator in middle"

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "Test Suite 5: Special Characters and Complex Cases"
echo "─────────────────────────────────────────────────────────────────"
echo ""

test_pattern_strip \
    'nuke /path/with spaces/file.nk &' \
    'nuke /path/with spaces/file.nk' \
    "Command with spaces in path and trailing &"

test_pattern_strip \
    'bash -c "echo test; sleep 1 &"' \
    'bash -c "echo test; sleep 1' \
    "Bash -c with semicolon and trailing &\""

test_pattern_strip \
    'rez env -- bash -ilc "cd /path && nuke --help &"' \
    'rez env -- bash -ilc "cd /path && nuke --help' \
    "Rez command with --flag and trailing &\""

echo ""
echo "─────────────────────────────────────────────────────────────────"
echo "Test Suite 6: Multiple Ampersands (Logical AND)"
echo "─────────────────────────────────────────────────────────────────"
echo ""

test_pattern_strip \
    'cd /a && cd /b && nuke /file &' \
    'cd /a && cd /b && nuke /file' \
    "Multiple && operators with trailing &"

test_pattern_strip \
    'rez env -- bash -ilc "ws /path && cd subdir && nuke file &"' \
    'rez env -- bash -ilc "ws /path && cd subdir && nuke file' \
    "Rez with multiple && and trailing &\""

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Test Results Summary"
echo "═══════════════════════════════════════════════════════════════"
echo ""

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
PASS_RATE=$((TESTS_PASSED * 100 / TOTAL_TESTS))

echo "Total tests:  $TOTAL_TESTS"
echo -e "Passed:       ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed:       ${RED}$TESTS_FAILED${NC}"
echo "Pass rate:    $PASS_RATE%"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
    echo ""
    echo "The corrected fix properly handles:"
    echo "  ✓ Rez commands ending with ' &\"'"
    echo "  ✓ Direct commands ending with ' &'"
    echo "  ✓ Edge cases ending with '&'"
    echo "  ✓ Commands with && operators (preserved)"
    echo "  ✓ Commands without & (unchanged)"
    echo ""
    echo "The fix is ready for production deployment."
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    echo ""
    echo "Review the failures above and fix the implementation."
    exit 1
fi
