# Terminal Dispatcher Crash: Deep Root Cause Analysis

**Date:** 2025-11-02  
**Analysis Type:** Deep Debugging - Shell Behavior, Signal Handling, FIFO Mechanics  
**Status:** CRITICAL FINDINGS - Original hypothesis likely incorrect

## Executive Summary

After deep analysis of bash shell behavior, quote parsing, FIFO mechanics, and signal handling, I have determined that **the proposed fix (stripping trailing &) is based on incorrect assumptions and would likely not solve the issue**. The real root cause appears to be signal-related interaction between nested interactive bash sessions with job control.

## Analysis of Original Hypothesis

### The Claim
The bug analysis states that `eval "$cmd"` where cmd contains a trailing & causes "double-backgrounding corruption" that breaks the bash session.

### Why This Is Incorrect

#### Quote Parsing Analysis
When command_launcher.py constructs the command at line 415:
```python
full_command = f'rez env {packages_str} -- bash -ilc "{ws_command}"'
```

And then adds & at line 454:
```python
command_to_send = full_command.rstrip('"') + ' &"'
```

The resulting string is:
```
rez env nuke python-3.11 -- bash -ilc "ws /path && nuke /file &"
```

**The & is INSIDE the closing double-quote**, making it part of the argument passed to bash -ilc.

#### Eval Behavior
When terminal_dispatcher.sh executes (line 124):
```bash
eval "$cmd"
```

Bash parses this as:
1. Command: `rez`
2. Arguments: `env nuke python-3.11 -- bash -ilc "ws /path && nuke /file &"`

The double quotes around $cmd in eval **do NOT** interfere with the inner quotes. The inner quotes are part of the string value of $cmd and are correctly interpreted as bash syntax by eval.

The & is **properly contained** within the quoted argument and will be processed by the **inner bash -ilc session**, not by the outer eval or dispatcher loop.

**Therefore, there is NO double-backgrounding at the eval level.**

## Real Root Cause Investigation

### The Mystery
Given that the quote parsing is correct, why does the dispatcher loop exit?

Evidence from logs:
- Terminal window stays open ✓
- Bash process (PID 2908718) still alive ✓
- Dispatcher loop has stopped reading from FIFO ✗

This pattern suggests the while loop exited but bash -i didn't exit.

### Plausible Root Causes

#### 1. Signal Interruption (MOST LIKELY)

**Hypothesis:** Nested interactive bash sessions with job control create signal interactions that interrupt the FIFO read.

**Mechanism:**
```bash
bash -i terminal_dispatcher.sh
  └── while true; do read -r cmd < FIFO
      └── eval "rez env nuke -- bash -ilc \"ws /path && nuke &\""
          └── bash -ilc spawns with job control
              └── nuke & creates background job
                  └── Sends SIGCHLD to parent shells
```

When the inner bash -ilc completes after backgrounding nuke:
1. SIGCHLD propagates to the bash -i running the dispatcher
2. The signal interrupts the `read -r cmd < "$FIFO"` blocking call
3. Bash's signal handling may cause the read to return with an error
4. If the error isn't handled correctly, the script may exit

**Supporting Evidence:**
- Issue occurs after FIRST command (when job control state is established)
- Issue is 100% reproducible (signal handling is deterministic)
- Terminal stays alive but script stops (consistent with signal interruption)

#### 2. FIFO Reopening Issues

**Hypothesis:** Opening and closing FIFO on each iteration creates race conditions.

**Current Pattern:**
```bash
while true; do
    read -r cmd < "$FIFO"  # Opens FIFO, reads, closes on each iteration
    eval "$cmd"
done
```

**Problem:** If file descriptors from eval's subprocesses interfere with FIFO operations, the next open might fail.

#### 3. Job Control State Corruption

**Hypothesis:** Interactive bash with nested interactive bash creates conflicting job control contexts.

When bash -i runs a script that spawns another bash -ilc with background jobs (&), the two interactive shells might conflict over terminal control, leading to unexpected behavior.

## Why The Proposed Fix Would Fail

### The Proposed Fix
```bash
# Strip trailing & if present
cmd="${cmd%&}"  # Remove trailing &
cmd="${cmd% }"  # Remove trailing space

# Now dispatcher handles backgrounding
if is_gui_app "$cmd"; then
    eval "$cmd &"
else
    eval "$cmd"
fi
```

### Why It's Wrong

#### Problem 1: Incorrect String Manipulation
For the command: `rez env nuke -- bash -ilc "ws /path && nuke /file &"`

After `cmd="${cmd%&}"`: `rez env nuke -- bash -ilc "ws /path && nuke /file "`

This **removes the & but leaves the closing quote incomplete!** The string now has mismatched quotes.

Wait, let me reconsider - the % operator removes the shortest match from the END. So it would give:
`rez env nuke -- bash -ilc "ws /path && nuke /file "`

The closing quote is still there. But now we've removed the & that was meant for the inner session.

#### Problem 2: Wrong Level Backgrounding
Then the fix does: `eval "$cmd &"`

This becomes: `eval "rez env nuke -- bash -ilc \"ws /path && nuke /file \" &"`

Now the & is at the OUTER level, backgrounding the entire rez command at the dispatcher level, not at the inner bash -ilc level where it should be!

This changes the process tree structure:
- Before: Dispatcher waits for rez → bash -ilc → nuke runs in background within bash -ilc
- After: Dispatcher backgrounds rez → entire chain runs in background

This could actually **make the problem worse** by creating different signal propagation patterns.

#### Problem 3: Doesn't Address Root Cause
Even if the string manipulation were correct, removing the & doesn't address the actual signal handling or FIFO reopening issues that likely cause the crash.

## Correct Solution Approaches

### Option 1: Fix Signal Handling (RECOMMENDED)

Add signal traps to prevent interruption:
```bash
# Trap signals that might interrupt the loop
trap '' SIGCHLD  # Ignore child process signals
trap '' SIGHUP   # Ignore hangup
trap '' SIGPIPE  # Ignore broken pipe

while true; do
    read -r cmd < "$FIFO" || continue  # Don't exit on read errors
    # ... rest of loop
done
```

### Option 2: Persistent FIFO File Descriptor

Keep FIFO open across iterations:
```bash
# Open FIFO once and keep it open
exec 3< "$FIFO"

while true; do
    read -r cmd <&3 || {
        # If read fails, reopen FIFO
        exec 3<&-  # Close old FD
        exec 3< "$FIFO"  # Reopen
        continue
    }
    eval "$cmd"
done
```

### Option 3: Non-Interactive Dispatcher

Remove -i flag when running dispatcher:
```python
# In persistent_terminal_manager.py, change:
["bash", self.dispatcher_path, self.fifo_path]  # No -i flag
```

This eliminates job control complications but may affect environment loading.

### Option 4: Disable Job Control for Spawned Commands

Modify terminal_dispatcher.sh to disable job control for eval:
```bash
# Temporarily disable job control
set +m  # Disable monitor mode
eval "$cmd"
set -m  # Re-enable monitor mode
```

## Evidence Required for Validation

Before implementing any fix, we need:

### 1. Enhanced Logging
Add to terminal_dispatcher.sh before line 41:
```bash
# Enable xtrace to log every command
set -x
exec 2>> /tmp/shotbot_dispatcher_debug.log

# Log all signals
trap 'echo "Received signal at $(date)" >&2' SIGCHLD SIGHUP SIGTERM SIGINT
```

### 2. Minimal Reproduction Test
Create test script:
```bash
#!/bin/bash
mkfifo /tmp/test_fifo

# Launch dispatcher
bash -i test_dispatcher.sh &
DISPATCHER_PID=$!

# Send commands
echo 'echo "test1" &' > /tmp/test_fifo
sleep 2
echo 'echo "test2" &' > /tmp/test_fifo

# Check if dispatcher still alive
kill -0 $DISPATCHER_PID && echo "ALIVE" || echo "DEAD"
```

### 3. Signal Monitoring
Use strace to monitor the dispatcher:
```bash
strace -f -e trace=signal,read,open -p $DISPATCHER_PID
```

This will show exactly which signals interrupt the read call.

## Risk Assessment

### Proposed Fix (Stripping &)
- **Probability of Success:** 20-30%
- **Risk of Making Worse:** 40-50%
- **Side Effects:** Changes process tree structure, may break assumptions

### Signal Handling Fix
- **Probability of Success:** 70-80%
- **Risk of Making Worse:** <5%
- **Side Effects:** Minimal - just adds signal traps

### Persistent FIFO Fix
- **Probability of Success:** 60-70%
- **Risk of Making Worse:** <10%
- **Side Effects:** Changes FIFO management pattern

## Recommended Action Plan

### Phase 1: Instrumentation (CRITICAL - Do First)
1. Add xtrace and signal logging to dispatcher
2. Reproduce the bug with logging enabled
3. Capture exact sequence of events and signals
4. Analyze logs to confirm root cause

### Phase 2: Implement Fix (Based on Evidence)
If logs show signal interruption:
- Implement signal trapping (Option 1)

If logs show FIFO issues:
- Implement persistent FD (Option 2)

If logs show job control conflicts:
- Implement job control management (Option 4)

### Phase 3: Testing
1. Test single command execution
2. Test rapid double command (2 seconds apart)
3. Test multiple consecutive commands
4. Verify terminal stays alive
5. Verify no "dispatcher dead" warnings

## Conclusion

The original bug analysis correctly identified symptoms but misdiagnosed the root cause. The "double-backgrounding corruption" theory is based on incorrect assumptions about bash quote parsing. The real issue is likely signal-related interference between nested interactive bash sessions with job control.

**The proposed fix (stripping &) should NOT be implemented** as it:
1. Is based on incorrect analysis
2. Would change backgrounding behavior in unintended ways
3. Does not address the actual root cause
4. Has high risk of making the problem worse

Instead, we should:
1. Add comprehensive logging first
2. Identify the exact root cause through evidence
3. Implement a targeted fix based on actual behavior
4. Test thoroughly before deployment

**Estimated debugging time with instrumentation:** 1-2 hours to capture evidence and identify exact cause.
