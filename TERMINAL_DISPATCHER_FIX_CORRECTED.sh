#!/bin/bash
# CORRECTED Fix for Terminal Dispatcher Double-Backgrounding Bug
# This version preserves closing quotes for rez commands

# Original buggy implementation (lines 113-115):
# cmd="${cmd% &\"}"   # ❌ Removes closing quote - causes syntax error
# cmd="${cmd% &}"     
# cmd="${cmd%&}"      

# CORRECTED implementation:
# Strip trailing & patterns while preserving quote structure

if [[ "$cmd" == *' &"' ]]; then
    # Rez command pattern: ends with ' &"'
    # Strip ' &"' and add back the closing '"'
    cmd="${cmd% &\"}\""
    if [ "$DEBUG_MODE" = "1" ]; then
        echo "[DEBUG] Stripped ' &\"' from rez command (preserved closing quote)" >&2
        echo "[DEBUG] Result: $cmd" >&2
    fi
elif [[ "$cmd" == *' &' ]]; then
    # Direct command pattern: ends with ' &'
    # Just strip the ' &'
    cmd="${cmd% &}"
    if [ "$DEBUG_MODE" = "1" ]; then
        echo "[DEBUG] Stripped ' &' from direct command" >&2
        echo "[DEBUG] Result: $cmd" >&2
    fi
elif [[ "$cmd" == *'&' ]]; then
    # Edge case: ends with '&' (no space)
    cmd="${cmd%&}"
    if [ "$DEBUG_MODE" = "1" ]; then
        echo "[DEBUG] Stripped '&' from edge case" >&2
        echo "[DEBUG] Result: $cmd" >&2
    fi
fi

# Verification test
echo ""
echo "=== Testing Corrected Implementation ==="
echo ""

# Test 1: Rez command
echo "Test 1: Rez command with trailing &\""
cmd='rez env nuke python-3.11 -- bash -ilc "ws /shows/TEST/shots/TST_0010 && nuke /path/file.nk &"'
echo "Input:  $cmd"

if [[ "$cmd" == *' &"' ]]; then
    cmd="${cmd% &\"}\""
fi

echo "Output: $cmd"
echo "Expected: rez env nuke python-3.11 -- bash -ilc \"ws /shows/TEST/shots/TST_0010 && nuke /path/file.nk\""
echo ""

# Verify no syntax error
if eval "$cmd &" 2>&1 | grep -q "unexpected.*matching"; then
    echo "❌ FAIL - Syntax error detected"
else
    echo "✅ PASS - No syntax error (command parsed successfully)"
fi

echo ""
echo "─────────────────────────────────────────"
echo ""

# Test 2: Direct command
echo "Test 2: Direct command with trailing &"
cmd='nuke /path/to/file.nk &'
echo "Input:  $cmd"

if [[ "$cmd" == *' &"' ]]; then
    cmd="${cmd% &\"}\""
elif [[ "$cmd" == *' &' ]]; then
    cmd="${cmd% &}"
fi

echo "Output: $cmd"
echo "Expected: nuke /path/to/file.nk"
echo ""

# Verify no syntax error
if eval "$cmd &" 2>&1 | grep -q "unexpected.*matching"; then
    echo "❌ FAIL - Syntax error detected"
else
    echo "✅ PASS - No syntax error (command parsed successfully)"
fi

echo ""
echo "─────────────────────────────────────────"
echo ""

# Test 3: Multiple && operators (should be preserved)
echo "Test 3: Command with && operators and trailing &\""
cmd='rez env -- bash -ilc "cd /path && ws /workspace && nuke /file &"'
echo "Input:  $cmd"

if [[ "$cmd" == *' &"' ]]; then
    cmd="${cmd% &\"}\""
fi

echo "Output: $cmd"
echo ""

# Verify && preserved and no syntax error
if echo "$cmd" | grep -q "&&"; then
    echo "✅ && operators preserved"
else
    echo "❌ && operators lost"
fi

if eval "$cmd &" 2>&1 | grep -q "unexpected.*matching"; then
    echo "❌ FAIL - Syntax error detected"
else
    echo "✅ PASS - No syntax error"
fi

echo ""
echo "=== All Tests Complete ==="
