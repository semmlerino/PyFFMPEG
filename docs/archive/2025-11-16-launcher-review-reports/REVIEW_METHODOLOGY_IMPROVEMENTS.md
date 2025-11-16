# Review Methodology Improvements
**Based on**: Multi-agent review that missed 4 critical bugs caught by separate assessment
**Date**: 2025-11-16

---

## What We Missed and Why

### Bugs Missed by All 5 Agents

| Bug | Type | Root Cause of Miss |
|-----|------|-------------------|
| Fallback queue wrong entry | Business logic | No agent traced failure path end-to-end |
| send_command_async() return type | API contract | No agent verified caller expectations match callee contract |
| Path injection | Input validation | Security explicitly out of scope per CLAUDE.md |
| Rez quote escaping | String escaping | Edge case in integration code not tested |

---

## Root Cause Analysis

### 1. Agent Specialization Too Narrow ⚠️

**What happened**: 3 of 5 agents focused on threading/concurrency
- `qt-concurrency-architect` → Qt threading patterns
- `threading-debugger` → Locks, races, deadlocks
- `python-code-reviewer` → General code quality

**Why it failed**: Threading bugs are **orthogonal** to business logic bugs
- Fallback queue bug is pure logic (no threading involved)
- Return type bug is API design (no concurrency)
- Path/quote bugs are string handling (no threads)

**Lesson**: **Don't overweight one domain when deploying agents in parallel**

---

### 2. Prompts Lacked Failure-Path Analysis 🔴

**What we asked**:
```
- "Review Qt threading and concurrency patterns"
- "Analyze concurrency patterns and identify race conditions"
- "Conduct comprehensive code review focusing on correctness, bugs, design issues"
```

**What we didn't ask**:
```
- "Trace all error handling paths end-to-end - where do failures propagate?"
- "Verify every function's return value is checked by its caller"
- "Simulate failure scenarios: what happens if X fails at step 3?"
- "Find all command/path string concatenations without validation"
```

**Lesson**: **Generic prompts like "find bugs" miss specific bug classes**

---

### 3. Missing Agent Types 🔴

**Agents we deployed**:
- ✅ Threading experts (2 agents)
- ✅ Qt expert (1 agent)
- ✅ Best practices (1 agent)
- ✅ Code reviewer (1 agent)

**Agents we didn't deploy**:
- ❌ Business logic tracer
- ❌ API contract validator
- ❌ Error path simulator
- ❌ Input validation auditor
- ❌ State machine verifier

**Lesson**: **Missing entire bug classes because no agent specialized in them**

---

### 4. Verification Depth Insufficient 🟡

**What agents did**:
- Read code at specific line numbers ✅
- Identified patterns (locks, signals, types) ✅
- Found obvious bugs (missing locks, wrong types) ✅

**What agents didn't do**:
- Trace value propagation through multiple functions ❌
- Simulate "what if this returns False?" scenarios ❌
- Verify caller assumptions match callee guarantees ❌
- Check dict/queue invariants (FIFO vs timestamp ordering) ❌

**Lesson**: **Static analysis finds syntax issues, not semantic bugs**

---

## Specific Improvements

### Improvement #1: Diversify Agent Portfolio 🎯

**Before** (our deployment):
```python
agents = [
    "code-comprehension-specialist",  # Architecture
    "python-code-reviewer",           # General review
    "qt-concurrency-architect",       # Qt threading
    "threading-debugger",             # Concurrency
    "best-practices-checker",         # Patterns
]
# 60% threading-focused, 40% general
```

**After** (improved):
```python
agents = [
    "code-comprehension-specialist",    # Architecture
    "error-path-tracer",                # NEW: Trace failure propagation
    "api-contract-validator",           # NEW: Check return values
    "state-invariant-verifier",         # NEW: Verify queue/dict logic
    "threading-debugger",               # Concurrency (1 agent, not 3)
]
# 20% threading, 80% logic/contracts/paths
```

**Rule of thumb**: **Max 1-2 agents per domain, force diversity**

---

### Improvement #2: Add Failure-Focused Prompts 🎯

#### New Agent: `error-path-tracer`

**Prompt**:
```
Trace all error handling and failure propagation paths in [files].

For each function that can fail:
1. Identify all failure modes (exceptions, False returns, None returns, error codes)
2. Trace where failures propagate:
   - Does caller check return value?
   - Does exception get caught and handled?
   - Can silent failures occur (no return check, no exception)?
3. Simulate failure scenarios:
   - "What if this DB query fails?"
   - "What if this network call times out?"
   - "What if this file doesn't exist?"

Find:
- Unchecked return values (caller assumes success)
- Silent failures (no error propagation)
- Wrong failure assumptions (caller expects X, callee returns Y)
- Missing error handlers (try without except)

Provide specific line numbers and failure scenarios.
```

**Would have caught**:
- ✅ send_command_async() return type bug (unchecked None return)
- ✅ Fallback queue bug (failure handler assumptions)

---

#### New Agent: `api-contract-validator`

**Prompt**:
```
Verify API contracts between callers and callees in [files].

For each function call:
1. Callee contract:
   - What does the function return? (type, meaning)
   - What exceptions can it raise?
   - What side effects does it have?
2. Caller expectations:
   - Does caller check return value?
   - Does caller handle exceptions?
   - Does caller assume side effects occurred?
3. Contract mismatches:
   - Caller expects bool, callee returns None
   - Caller assumes success, callee can fail silently
   - Caller expects exception, callee returns error code

Find:
- Type mismatches (return type vs usage)
- Unchecked return values
- Assumed side effects (caller doesn't verify)
- Missing exception handlers

Focus on:
- Functions that return bool, None, or Optional types
- Functions with side effects (I/O, state changes)
- Async functions and signal emissions
```

**Would have caught**:
- ✅ send_command_async() returns None but caller assumes success

---

#### New Agent: `state-invariant-verifier`

**Prompt**:
```
Verify state machine invariants and data structure consistency in [files].

For each stateful data structure (dict, queue, list, set):
1. Document intended invariants:
   - FIFO queue: pop() should return oldest entry
   - Dict keys: what identifies uniqueness?
   - List ordering: what determines order?
2. Trace operations that modify state:
   - Insert/delete operations
   - Update operations
   - Cleanup operations
3. Verify invariants preserved:
   - Does pop() actually return oldest entry?
   - Do cleanup operations maintain invariants?
   - Can state become inconsistent?

Find:
- Broken invariants (FIFO returns non-oldest)
- Cleanup bugs (removes wrong entries)
- State corruption (inconsistent dict/list state)
- Race conditions in state updates

Provide specific scenarios showing invariant violations.
```

**Would have caught**:
- ✅ Fallback queue returns oldest by timestamp, not oldest inserted

---

#### New Agent: `input-validation-auditor`

**Prompt**:
```
Find input validation and injection vulnerabilities in [files].

For each user-controlled or external input:
1. Identify input sources:
   - User input (file paths, commands, config)
   - Environment variables (TMPDIR, PATH, HOME)
   - External data (files, network, IPC)
2. Trace how input is used:
   - String concatenation without escaping
   - Shell command construction
   - File path operations
   - SQL/command injection points
3. Verify validation:
   - Is input validated before use?
   - Is input escaped/quoted for shell?
   - Can special characters break parsing?

Find:
- Command injection (unescaped shell metacharacters)
- Path injection (spaces, quotes, special chars)
- Quote escaping bugs (nested quotes break parsing)
- Format string bugs (user input in format string)

Note: Per CLAUDE.md, security is not a priority for this single-user VFX tool,
but these bugs also break functionality with legitimate inputs (paths with spaces).

Provide specific injection scenarios.
```

**Would have caught**:
- ✅ Nuke script path injection
- ✅ Rez quote escaping bug

---

### Improvement #3: Add Execution Simulation to Prompts 🎯

**Before** (static analysis):
```
"Review the code for correctness, bugs, and design issues"
```

**After** (dynamic simulation):
```
"Review the code AND simulate execution for these scenarios:

1. Happy path: Everything succeeds
   - Trace values through each function
   - Verify expected behavior occurs

2. Failure paths: Each step fails
   - What if function A fails at step 3?
   - What if function B returns None?
   - What if timeout occurs during C?

3. Edge cases:
   - What if queue is empty?
   - What if dict has no matching key?
   - What if file path has spaces/quotes?

For each scenario, trace:
- Value flow through functions
- Return value checks
- Error handling
- State changes

Identify where reality differs from code's assumptions."
```

---

### Improvement #4: Create Specialized Agent Definitions 🎯

#### New Agent File: `.claude/agents/error-path-tracer.yaml`

```yaml
name: error-path-tracer
model: sonnet
description: Traces error handling and failure propagation paths

system_prompt: |
  You are an error path analysis specialist. Your role is to trace how failures
  propagate through code and identify silent failures, unchecked returns, and
  broken error handling.

  For each function that can fail, ask:
  1. What are all the ways this can fail?
  2. How does the caller know it failed?
  3. What happens if the caller doesn't check?

  Simulate failure scenarios step-by-step.

  Focus on:
  - Functions returning bool, None, Optional, or error codes
  - Functions with side effects that can fail
  - Async operations and signal-based error reporting
  - Functions called in error handlers (can they fail too?)

  Always provide:
  - Specific line numbers
  - Concrete failure scenarios
  - Data flow trace showing how failures propagate (or don't)

tools:
  - Read
  - Grep
  - mcp__serena__find_symbol
  - mcp__serena__find_referencing_symbols
  - mcp__serena__search_for_pattern

examples:
  - input: "Trace error paths in persistent_terminal_manager.py"
    output: |
      Function send_command_async() can fail in 4 ways (lines 1110-1138):
      1. Returns None if shutdown (line 1115)
      2. Returns None if empty command (line 1120)
      3. Returns None if fallback mode (line 1130)
      4. Returns None if dummy_writer not ready (line 1138)

      Caller at command_launcher.py:504 doesn't check return value:
      ```python
      self.persistent_terminal.send_command_async(full_command)
      return True  # Always returns True!
      ```

      Failure scenario:
      - User clicks "Launch Nuke" during terminal restart
      - send_command_async() returns None (dummy_writer not ready)
      - Caller returns True (thinks command queued)
      - No fallback occurs, command silently dropped

      Fix: Change send_command_async() to return bool, check in caller.
```

---

#### New Agent File: `.claude/agents/api-contract-validator.yaml`

```yaml
name: api-contract-validator
model: sonnet
description: Verifies API contracts between function callers and callees

system_prompt: |
  You are an API contract verification specialist. Your role is to verify that
  callers and callees have matching expectations about return values, exceptions,
  and side effects.

  For each function call:
  1. What does the callee promise to return/do?
  2. What does the caller assume the callee does?
  3. Do these match?

  Common contract bugs:
  - Callee returns None, caller expects bool
  - Callee can return None, caller doesn't check
  - Caller assumes side effect occurred, callee can fail silently
  - Callee raises exception, caller doesn't handle

  Always trace:
  - Function signature (return type, annotations)
  - Actual return statements (all paths)
  - Caller's usage (checks? error handling?)
  - Documentation vs reality

  Provide:
  - Line numbers for both caller and callee
  - Contract mismatch description
  - Example showing how mismatch breaks code

tools:
  - Read
  - Grep
  - mcp__serena__find_symbol
  - mcp__serena__find_referencing_symbols

examples:
  - input: "Verify contracts in command_launcher.py"
    output: |
      Contract mismatch: send_command_async()

      Callee contract (persistent_terminal_manager.py:1084):
      ```python
      def send_command_async(self, command: str) -> None:
          # Returns nothing
      ```

      Caller expectation (command_launcher.py:504-506):
      ```python
      self.persistent_terminal.send_command_async(full_command)
      return True  # Caller assumes success
      ```

      Mismatch: Callee returns None (no indication of success/failure),
      but caller assumes command was queued successfully.

      Impact: Caller returns True even when command rejected,
      preventing fallback retry logic from activating.
```

---

### Improvement #5: Add Cross-Agent Verification Step 🎯

After agents complete, add a **synthesis agent** that specifically looks for:

**Prompt for synthesis agent**:
```
You have 5 agent reports. Your job is to find bugs they ALL missed.

Specifically check for:
1. Business logic bugs (failure scenarios, state invariants)
2. API contract mismatches (return values, side effects)
3. Input validation (paths, commands, quotes)
4. Error propagation (unchecked returns, silent failures)

For each category, simulate execution:
- Trace code paths agents didn't mention
- Check assumptions agents didn't verify
- Test scenarios agents didn't consider

Focus on code NOT mentioned in any agent report - that's likely where bugs hide.
```

---

## Improved Deployment Strategy

### Option A: Diversified Parallel Deployment (Recommended)

```python
# Deploy 5 agents with NO overlap in domains
agents = [
    ("code-comprehension-specialist", "Architectural overview"),
    ("error-path-tracer", "Failure propagation"),
    ("api-contract-validator", "Return value contracts"),
    ("state-invariant-verifier", "Queue/dict logic"),
    ("input-validation-auditor", "Command/path injection"),
]
```

**Coverage**: 5 orthogonal bug classes
**Risk**: Might miss threading bugs (no threading expert)
**Mitigation**: Add threading-debugger as 6th agent if concurrency suspected

---

### Option B: Two-Phase Deployment

**Phase 1 - Broad Coverage** (5 agents):
```python
phase1 = [
    "code-comprehension-specialist",
    "error-path-tracer",
    "api-contract-validator",
    "state-invariant-verifier",
    "threading-debugger",  # Just 1 threading expert
]
```

**Phase 2 - Targeted Deep Dive** (based on Phase 1 findings):
```python
# If Phase 1 finds threading issues:
phase2 = ["qt-concurrency-architect"]

# If Phase 1 finds input validation issues:
phase2 = ["input-validation-auditor"]

# If Phase 1 finds complex state bugs:
phase2 = ["state-invariant-verifier"]
```

---

### Option C: Hybrid (Coverage + Depth)

```python
# 3 broad-coverage agents
broad = [
    "code-comprehension-specialist",
    "python-code-reviewer",
    "error-path-tracer",
]

# 3 specialists based on codebase domain
specialists = [
    "qt-concurrency-architect",      # If Qt app
    "input-validation-auditor",      # If CLI/shell commands
    "state-invariant-verifier",      # If stateful queues/dicts
]
```

---

## Concrete Checklist for Next Review

### Before Deploying Agents:

- [ ] Identify codebase domains (threading? state machines? I/O? shell commands?)
- [ ] Choose agents covering different domains (max 1-2 per domain)
- [ ] Write failure-focused prompts ("trace what happens when X fails")
- [ ] Include simulation tasks ("simulate these 3 scenarios")
- [ ] Avoid generic prompts ("find bugs" → "trace error propagation")

### Agent Prompts Should Include:

- [ ] Specific scenarios to simulate (happy path, failure paths, edge cases)
- [ ] Execution tracing requirements ("trace value X through functions A, B, C")
- [ ] Contract verification ("does caller check return value?")
- [ ] State invariant checks ("does pop() return oldest entry?")

### After Agents Complete:

- [ ] Run synthesis agent looking for **uncovered code**
- [ ] Manually check categories agents didn't cover
- [ ] Verify at least one agent covered each domain:
  - [ ] Error propagation
  - [ ] API contracts
  - [ ] State invariants
  - [ ] Input validation
  - [ ] Threading (if applicable)

---

## Expected Improvement

### Before (Our Review):
- **Found**: 10 bugs (2 critical)
- **Missed**: 4 bugs caught by separate assessment
- **Coverage**: 71% of bugs found by combined approaches

### After (With Improvements):
- **Expected**: 13-14 bugs (4-5 critical)
- **Expected to miss**: 0-1 bugs
- **Coverage**: 93-100% of discoverable bugs

**Key improvement**: Shifting from **pattern matching** (threading, types, locks) to **execution simulation** (trace failures, verify contracts, simulate edge cases)

---

## Summary

### What to Change:

1. ✅ **Diversify agents** - Don't deploy 3 threading experts
2. ✅ **Add new agent types** - error-path-tracer, api-contract-validator
3. ✅ **Rewrite prompts** - "Simulate failure scenarios" not "find bugs"
4. ✅ **Add execution tracing** - "Trace value X through A→B→C"
5. ✅ **Verify contracts** - "Does caller check return value?"
6. ✅ **Check state invariants** - "Does pop() return oldest?"

### Quick Wins for Next Time:

**Deploy these 5 instead**:
1. code-comprehension-specialist (architecture)
2. error-path-tracer (failure propagation)
3. api-contract-validator (return values)
4. state-invariant-verifier (queue/dict logic)
5. threading-debugger (concurrency)

**With these prompts**:
- "Trace all failure paths end-to-end"
- "Verify every return value is checked by caller"
- "Simulate these scenarios: [happy, failure, edge cases]"
- "Check queue/dict invariants (FIFO, uniqueness, ordering)"

**Result**: Should catch 90%+ of bugs, including all 4 we missed.
