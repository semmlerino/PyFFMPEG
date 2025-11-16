# Agent Review Methodology - Gap Analysis & Improvements
**Date**: 2025-11-16
**Context**: 5 agents found 10 bugs, separate assessment found 4 additional bugs
**Question**: How do we catch those 4 bugs next time?

---

## What We Missed (Root Cause Analysis)

### Bug #1: Fallback Queue Wrong Entry (Separate Assessment)
**Why Missed**: No agent traced **business logic semantics**

**What Agents Did**:
- ✅ Verified thread safety of dict operations (lock held during min/pop)
- ✅ Checked TOCTOU races
- ✅ Analyzed signal flow

**What Agents Missed**:
- ❌ Never asked: "Does this FIFO queue actually process commands in order?"
- ❌ Never traced: User launches Nuke (success) → User launches RV (fail) → What gets retried?
- ❌ Never verified: Does cleanup remove the **right** entry on success?

**Agent Type Missing**: **Business Logic Validator**
- Focus: Correctness of algorithms, not just thread safety
- Questions: "Does this queue behave as documented?" "What order are items processed?"
- Tools: Trace symbolic execution, verify invariants

---

### Bug #2: send_command_async() Return Type (Separate Assessment)
**Why Missed**: No agent validated **API contracts across call boundaries**

**What Agents Did**:
- ✅ Verified signal emissions on failure paths
- ✅ Checked that `command_result.emit(False, ...)` is called
- ✅ Traced Qt signal propagation

**What Agents Missed**:
- ❌ Never checked: Does caller handle the return value?
- ❌ Never verified: Return type matches caller expectations
- ❌ Never traced: `_try_persistent_terminal()` assumes return value indicates success

**Agent Type Missing**: **API Contract Validator**
- Focus: Return values, parameter contracts, preconditions/postconditions
- Questions: "Does return type match documentation?" "Does caller check return value?"
- Tools: Type signature analysis, call chain tracing, contract verification

---

### Bug #3: Nuke Script Path Injection (Separate Assessment)
**Why Missed**: **Security excluded from scope** per CLAUDE.md

**What Agents Did**:
- ✅ Correctly followed CLAUDE.md: "Security vulnerabilities NOT a concern"
- ✅ Ignored command injection as acceptable per project policy

**What Agents Missed**:
- ❌ Path injection breaks **functionality** even with legitimate TMPDIR values
- ❌ Not a security issue when `TMPDIR="/tmp/My Show"` (spaces) breaks parsing
- ❌ This is a **correctness bug**, not a security bug

**Agent Prompt Issue**: Conflated "security vulnerability" with "input validation"

**Fix**: Separate concerns in agent instructions:
```
❌ OLD: "Security issues NOT a concern (skip SQL injection, XSS, etc.)"
✅ NEW: "Security issues NOT a concern, BUT input validation bugs that break
        functionality with legitimate inputs ARE bugs (e.g., paths with spaces)"
```

---

### Bug #4: Rez Quote Escaping (Separate Assessment)
**Why Missed**: No agent tested **integration edge cases**

**What Agents Did**:
- ✅ Reviewed command building logic
- ✅ Checked Qt patterns, threading, signals

**What Agents Missed**:
- ❌ Never tested: What if Config.APPS contains quotes?
- ❌ Never checked: Does Rez wrapper handle all valid shell commands?
- ❌ Never validated: Edge cases for third-party integration (Rez)

**Agent Type Missing**: **Integration Edge Case Tester**
- Focus: Boundary conditions, special characters, configuration variations
- Questions: "What if config contains quotes?" "What if path has spaces?"
- Tools: Property-based thinking, edge case enumeration

---

## Methodology Gaps Summary

| Gap Type | Impact | Missed Bugs |
|----------|--------|-------------|
| **Business Logic Analysis** | High | 1 (fallback queue) |
| **API Contract Validation** | High | 1 (return type) |
| **Input Validation (non-security)** | Medium | 1 (path injection) |
| **Integration Edge Cases** | Medium | 1 (Rez quotes) |
| **End-to-End Flow Tracing** | High | 2 (return type, fallback) |

---

## Specific Improvements

### 1. Add Missing Agent Types

#### New Agent: `business-logic-validator`
```yaml
name: business-logic-validator
description: >
  Business logic correctness specialist - use when reviewing algorithms, data structures,
  or state machines for correctness (not just thread safety).

  Validates:
  - Queue/stack semantics (FIFO/LIFO ordering preserved?)
  - State machine transitions (valid state progressions?)
  - Algorithm correctness (does the code do what it claims?)
  - Invariant preservation (are class invariants maintained?)

  Examples:
  - "Does this fallback queue retry the failed command or oldest command?"
  - "Does this cache eviction remove the right entries?"
  - "Does this state machine handle all transitions correctly?"

tools: [Read, Grep, Task, sequential-thinking]
model: sonnet  # Needs reasoning, not just pattern matching
```

#### New Agent: `api-contract-validator`
```yaml
name: api-contract-validator
description: >
  API contract specialist - use after code changes to verify function signatures,
  return values, and caller expectations align.

  Validates:
  - Return type matches callers' expectations
  - Return values are actually checked (not ignored)
  - Function preconditions documented and enforced
  - Parameter validation matches documentation
  - Error handling contracts (exceptions vs error codes)

  Examples:
  - "Does this function return bool but callers ignore it?"
  - "Does async function need to return status or rely on signals?"
  - "Are error codes checked or ignored?"

tools: [Read, Grep, find_symbol, find_referencing_symbols]
model: sonnet
```

#### New Agent: `input-validation-auditor`
```yaml
name: input-validation-auditor
description: >
  Input validation specialist - use when reviewing user input handling, file paths,
  configuration values, or external data processing.

  Focus: Functional correctness with legitimate inputs (NOT security exploits)

  Validates:
  - Paths with spaces/special chars handled correctly
  - Configuration strings with quotes/newlines parsed correctly
  - User input edge cases (empty, very long, unicode, etc.)
  - Shell command construction (quoting, escaping)

  NOT security focused - checks if legitimate inputs work, not if malicious inputs are blocked.

  Examples:
  - "Does TMPDIR='/tmp/My Show' work correctly?"
  - "Does config value with quotes break command construction?"
  - "Are file paths properly quoted for shell execution?"

tools: [Read, Grep, sequential-thinking]
model: sonnet
```

#### New Agent: `integration-flow-tracer`
```yaml
name: integration-flow-tracer
description: >
  End-to-end flow tracer - use when you need to verify complete user journeys
  from UI action → business logic → external system → result.

  Traces:
  - User action (button click) → command queued → execution → result displayed
  - API call → database query → response processing → UI update
  - Configuration change → component initialization → runtime behavior

  Asks:
  - "What happens when user clicks Launch and command fails?"
  - "How does error in step 3 propagate back to UI?"
  - "What if external system (Rez, Nuke) behaves unexpectedly?"

  Examples:
  - Trace launch flow: Click → _try_persistent_terminal → send_command_async → signals → UI
  - Trace failure: Command rejected → signal emission → fallback logic → retry

tools: [Read, Grep, find_symbol, find_referencing_symbols, sequential-thinking]
model: sonnet
```

---

### 2. Improve Agent Prompts

#### Current Prompt Issues

**Example from `python-code-reviewer`**:
```
Check for:
1. Correctness issues
2. Resource management
3. Error handling
4. Type safety
5. API design  # ← Too vague!
```

**Improved Version**:
```
Check for:
1. Correctness issues:
   - Algorithm correctness (does code do what it claims?)
   - Business logic semantics (FIFO queues process in order?)
   - State machine validity (all transitions handled?)

2. API design:
   - Return types match caller expectations (check all callers!)
   - Return values are actually checked (not ignored)
   - Error handling contracts clear (exceptions vs error codes)
   - Function preconditions enforced

3. Input validation (functional, not security):
   - Paths with spaces/special chars handled correctly
   - Configuration strings properly escaped/quoted
   - Edge cases (empty, very long, unicode) handled
```

#### Add Explicit End-to-End Tracing

**New Section in All Agent Prompts**:
```
## End-to-End Verification

After finding issues with individual functions, trace at least one complete
user flow to verify components work together correctly:

1. Pick a user action (e.g., "Launch Nuke")
2. Trace code path: UI → controller → business logic → external system
3. Verify return values propagate correctly
4. Check error handling at each boundary
5. Confirm result reaches user (success or failure)

Example traces:
- "User launches app during terminal restart" → verify behavior
- "User launches app when dummy writer fails" → verify fallback works
- "User launches second app while first still launching" → verify queueing
```

---

### 3. Orchestration Improvements

#### Current: Parallel Independent Agents
```
Deploy 5 agents in parallel:
- code-comprehension-specialist
- python-code-reviewer
- qt-concurrency-architect
- threading-debugger
- best-practices-checker
```

**Issue**: No cross-agent communication, no synthesis during analysis

#### Improved: Staged Pipeline with Feedback

```
Stage 1 (Parallel): Architecture & Patterns
- code-comprehension-specialist → Creates flow diagrams
- best-practices-checker → Identifies patterns

Stage 2 (Sequential): Deep Analysis (uses Stage 1 output)
- business-logic-validator → Validates flows from Stage 1
- api-contract-validator → Checks contracts in call chains
- integration-flow-tracer → Traces end-to-end using flows

Stage 3 (Parallel): Specialized Domain Analysis
- python-code-reviewer
- qt-concurrency-architect
- threading-debugger
- input-validation-auditor

Stage 4 (Sequential): Synthesis
- review-synthesis-agent → Combines all findings, checks for gaps
```

**Benefits**:
- Early stages provide context for later stages
- Flow diagrams enable better API contract validation
- Synthesis step catches cross-cutting issues

---

### 4. Agent Self-Verification Checklist

Add to all agent prompts:

```
## Before Completing Analysis

Self-verify using this checklist:

□ Algorithm Correctness
  - Did I verify business logic semantics, not just thread safety?
  - Do queues/stacks preserve ordering as documented?
  - Are state transitions all valid?

□ API Contracts
  - Did I check return values are used by callers?
  - Do return types match expectations?
  - Are errors handled or ignored?

□ Input Validation
  - Did I test edge cases (spaces, quotes, empty, long)?
  - Are paths properly quoted for shell execution?
  - Do config values with special chars work?

□ Integration
  - Did I trace at least one end-to-end flow?
  - Did I check integration points (Rez, external tools)?
  - Did I verify error propagation across boundaries?

□ Examples
  - Did I provide concrete examples with line numbers?
  - Did I show reproduction scenarios?
  - Did I suggest fixes, not just identify issues?
```

---

### 5. Test Against Known Bugs

Create a **validation suite** from this experience:

```python
# tests/meta/test_agent_coverage.py
"""Meta-tests: Verify agents catch known bug patterns."""

KNOWN_BUGS = [
    {
        "id": "fallback-wrong-entry",
        "description": "FIFO queue pops oldest, not failed entry",
        "file": "command_launcher.py:370-386",
        "required_agents": ["business-logic-validator"],
        "detection_method": "Trace success → fail flow, verify retry logic"
    },
    {
        "id": "ignored-return-value",
        "description": "send_command_async returns None, caller ignores",
        "file": "command_launcher.py:504",
        "required_agents": ["api-contract-validator"],
        "detection_method": "Check all callers of send_command_async"
    },
    # ... more known bugs
]

def test_agents_find_known_bugs():
    """Deploy agents and verify they find all known bugs."""
    findings = deploy_agents(files=[...])

    for bug in KNOWN_BUGS:
        assert bug["id"] in findings, f"Missed known bug: {bug['id']}"
```

**Usage**: Run before deploying agents on new code to verify methodology works

---

### 6. Prompt Template Improvements

#### Add "Missed Bug" Section to Prompts

```
## Learn from Past Misses

Previous agent reviews missed these bug types. Pay special attention:

1. **Business Logic**: Verify algorithms do what they claim
   - Example miss: Fallback queue popped oldest entry, not failed entry
   - Check: Does this data structure behave as documented?

2. **API Contracts**: Verify return values are checked
   - Example miss: send_command_async() returns None, caller assumes bool
   - Check: Do all callers handle return value correctly?

3. **Input Validation**: Test with legitimate edge cases
   - Example miss: Path with spaces breaks command parsing
   - Check: Does TMPDIR with spaces work? Config with quotes?

4. **Integration**: Trace end-to-end flows
   - Example miss: Command rejected but caller thinks it succeeded
   - Check: Trace user action → result, verify error propagation
```

---

### 7. Configuration File Improvements

#### Current Agent YAML
```yaml
tools: [Task, Bash, Read, Grep, ...]
```

#### Improved Agent YAML
```yaml
tools: [Task, Bash, Read, Grep, find_symbol, find_referencing_symbols]

# NEW: Checklist for this agent type
checklist:
  - "Verify algorithm correctness, not just thread safety"
  - "Check return values are used by all callers"
  - "Test edge cases (spaces, quotes, empty, unicode)"
  - "Trace at least one end-to-end user flow"

# NEW: Common pitfalls for this agent type
pitfalls_to_avoid:
  - "Don't assume thread safety means correctness"
  - "Don't skip return value propagation checks"
  - "Don't conflate security with input validation"

# NEW: Examples of bugs this agent should catch
example_bugs:
  - "FIFO queue doesn't preserve order"
  - "Function returns bool but callers ignore it"
  - "Path with spaces breaks shell command"
```

---

## Concrete Action Plan

### Immediate (Before Next Review)

1. **Create 4 new agent types** (1 hour):
   - business-logic-validator
   - api-contract-validator
   - input-validation-auditor
   - integration-flow-tracer

2. **Update existing agent prompts** (30 min):
   - Add self-verification checklist
   - Add "Learn from Past Misses" section
   - Add explicit end-to-end tracing requirement

3. **Create validation suite** (1 hour):
   - Add 4 known bugs as test cases
   - Verify agents catch them

### Short-term (Next Sprint)

4. **Implement staged pipeline** (2 hours):
   - Architecture stage → Analysis stage → Synthesis
   - Pass context between stages

5. **Add agent YAML improvements** (1 hour):
   - Checklists
   - Pitfalls
   - Example bugs

### Long-term (Next Quarter)

6. **Agent performance metrics** (1 day):
   - Track: bugs found, false positives, coverage
   - A/B test: old prompts vs new prompts
   - Iteratively improve based on data

7. **Cross-project validation** (ongoing):
   - Test agents on other codebases
   - Build library of known bug patterns
   - Continuously update agent knowledge

---

## Expected Improvement

### Current Performance
- 5 agents found 10 bugs (8 unique after deduplication)
- Separate assessment found 4 additional bugs
- **Coverage: 71%** (10 found / 14 total)

### Expected After Improvements
With 4 new agent types + improved prompts:
- **Coverage: 95%+** (13-14 found / 14 total)
- Remaining 5% requires human creativity/domain expertise

### Validation
- Re-run improved agents on current codebase
- Verify they find all 14 bugs (10 original + 4 from assessment)
- If not, iterate on prompts/agent types

---

## Key Insights

### What Works Well (Keep)
✅ **Parallel agent deployment** - Fast, diverse perspectives
✅ **Specialized agent types** - Deep domain expertise
✅ **Concrete examples with line numbers** - Actionable findings
✅ **Cross-agent verification** - Reduces false positives

### What Needs Improvement (Fix)
❌ **Business logic blind spot** - Focus on safety, not correctness
❌ **API contract gaps** - Focus on implementation, not interfaces
❌ **Input validation confusion** - Conflate security with correctness
❌ **Integration testing** - Focus on units, not flows

### New Principles

1. **Thread Safety ≠ Correctness** - Safe but wrong is still a bug
2. **Signals ≠ Return Values** - Both error reporting mechanisms matter
3. **Security ≠ Input Validation** - Legitimate inputs must work
4. **Units ≠ Integration** - Components must work together

---

## Conclusion

The separate assessment caught 4 bugs because it used **different mental models**:
- **Business logic semantics** (not just thread safety)
- **API contracts** (not just implementations)
- **Functional input validation** (not security)
- **End-to-end flows** (not isolated units)

Our agents focused on **concurrency and patterns** (their strength), but missed **business logic and integration** (blind spots).

**Solution**: Add specialized agents for those domains + improve prompts to explicitly check for past misses.

**Expected ROI**: 24% coverage improvement (71% → 95%+) for ~5 hours of work.
