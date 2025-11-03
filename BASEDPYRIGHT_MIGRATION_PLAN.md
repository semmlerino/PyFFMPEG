# Basedpyright Configuration Migration Plan

## Current State Analysis

### Problems
1. ❌ **Duplicate configs**: `pyproject.toml` + `pyrightconfig.json` conflict
2. ❌ **Wrong Python version**: Config says 3.12, actual is 3.13.3
3. ❌ **Wrong paths**: Points to Windows mount `/mnt/c/...` instead of Linux
4. ❌ **Contradictory rules**: Include and exclude lists conflict
5. ❌ **Too permissive**: 7 important checks disabled → bugs slip through
6. ❌ **Legacy files**: References non-existent files from old project

### Current Result
```bash
$ basedpyright
0 errors, 0 warnings, 0 notes
```

**BUT**: Many real issues are hidden because checks are disabled!

---

## Three Configuration Options

### Option 1: Gradual Transition (RECOMMENDED)
**File**: `pyproject.toml.gradual`

**Characteristics:**
- Type checking mode: `standard` (between basic and recommended)
- Critical errors: Still fail build (undefined variables, missing imports)
- New checks: Enabled as **warnings** (informational, won't block)
- Path to strictness: Clear upgrade path

**Expected Result:**
```bash
$ basedpyright
0 errors, 50-150 warnings, 0 notes
```

**Pros:**
- ✅ Won't break existing workflow
- ✅ Gradually surfaces issues
- ✅ Can fix warnings incrementally
- ✅ Clear path to stricter checking

**Cons:**
- ⚠️ Warnings may be ignored
- ⚠️ Takes longer to achieve full type safety

**Best for:** Teams that want to improve gradually without disruption

---

### Option 2: Aggressive (Full Strictness)
**File**: `pyproject.toml.proposed`

**Characteristics:**
- Type checking mode: `recommended`
- All checks: Enabled as **errors**
- No mercy: Everything must be fixed

**Expected Result:**
```bash
$ basedpyright
50-200 errors, 0 warnings, 0 notes
```

**Pros:**
- ✅ Immediately finds all issues
- ✅ Enforces best practices from day 1
- ✅ Maximum type safety

**Cons:**
- ❌ Will block current development
- ❌ Requires immediate fix sprint
- ❌ May find false positives

**Best for:** New projects or teams committed to fixing everything immediately

---

### Option 3: Keep Current (NOT RECOMMENDED)
**File**: `pyproject.toml` (current)

**Characteristics:**
- Type checking mode: `basic`
- Most checks: Disabled
- Status quo: No changes

**Expected Result:**
```bash
$ basedpyright
0 errors, 0 warnings, 0 notes
```

**Pros:**
- ✅ No work required
- ✅ No disruption

**Cons:**
- ❌ Bugs slip through
- ❌ Technical debt accumulates
- ❌ Config still has problems (wrong paths, conflicts)

**Best for:** Nothing - this option is not recommended

---

## Recommended Migration Path

### Phase 1: Fix Config Issues (Week 1)
**Choose Option 1 (Gradual)**

1. **Backup current configs**:
   ```bash
   cp pyproject.toml pyproject.toml.backup.$(date +%Y%m%d)
   cp pyrightconfig.json pyrightconfig.json.backup.$(date +%Y%m%d)
   ```

2. **Apply gradual config**:
   ```bash
   cp pyproject.toml.gradual pyproject.toml
   ```

3. **Remove duplicate config**:
   ```bash
   mv pyrightconfig.json pyrightconfig.json.old
   # Keep tests/pyrightconfig.json - it's separate
   ```

4. **Test new configuration**:
   ```bash
   ~/.local/bin/uv run basedpyright 2>&1 | tee basedpyright_new_issues.txt
   ```

5. **Review output**:
   - Count errors (should be 0)
   - Count warnings (expected 50-150)
   - Identify most common warning types

### Phase 2: Fix Critical Issues (Week 2)
**Focus on errors only**

1. **Undefined variables** (critical):
   ```bash
   grep "reportUndefinedVariable" basedpyright_new_issues.txt
   ```
   Fix immediately - these are real bugs!

2. **Missing imports** (critical):
   ```bash
   grep "reportMissingImports" basedpyright_new_issues.txt
   ```
   Fix immediately - these break at runtime!

3. **Verify 0 errors**:
   ```bash
   ~/.local/bin/uv run basedpyright | grep "0 errors"
   ```

### Phase 3: Categorize Warnings (Week 3)
**Understand warning types**

```bash
# Count warning types
~/.local/bin/uv run basedpyright 2>&1 | \
  grep "warning" | \
  sed 's/.*\[\(.*\)\]/\1/' | \
  sort | uniq -c | sort -rn
```

**Typical breakdown:**
```
  45 reportOptionalMemberAccess   # Most common - None checks
  32 reportUnknownMemberType      # Type inference issues
  21 reportUnusedVariable         # Cleanup needed
  15 reportUnknownParameterType   # Missing type hints
  12 reportOptionalCall           # None checks
   8 reportPrivateUsage           # Accessing _ methods
   5 reportUnannotatedClassAttribute
```

### Phase 4: Fix High-Value Warnings (Weeks 4-6)
**Prioritize by bug-finding value**

**Priority 1: Optional checks** (prevent None crashes)
```bash
# Fix these first - they find real bugs
reportOptionalMemberAccess
reportOptionalCall
reportOptionalSubscript
```

**Priority 2: Type mismatches** (catch type errors)
```bash
reportUnknownMemberType
reportUnknownParameterType
reportUnknownArgumentType
```

**Priority 3: Code quality** (cleanup)
```bash
reportUnusedVariable
reportUnusedImport
reportPrivateUsage
```

### Phase 5: Promote Warnings to Errors (Week 7)
**After fixing warnings in a category, make them errors**

Edit `pyproject.toml`:
```toml
# Before
reportOptionalMemberAccess = "warning"

# After fixing all warnings
reportOptionalMemberAccess = "error"
```

**Gradual promotion order:**
1. `reportUndefinedVariable` = "error" (already done)
2. `reportMissingImports` = "error" (already done)
3. `reportOptionalMemberAccess` = "error"
4. `reportOptionalCall` = "error"
5. `reportUnknownMemberType` = "error"
6. ... continue ...

### Phase 6: Move to Recommended Mode (Week 8+)
**Once all current warnings are fixed**

Edit `pyproject.toml`:
```toml
typeCheckingMode = "recommended"  # From "standard"
```

Run and fix any new issues that appear.

---

## Quick Start Commands

### Apply Recommended Configuration
```bash
# 1. Backup
cp pyproject.toml pyproject.toml.backup.$(date +%Y%m%d)
cp pyrightconfig.json pyrightconfig.json.backup.$(date +%Y%m%d)

# 2. Apply gradual config
cp pyproject.toml.gradual pyproject.toml

# 3. Archive old config
mv pyrightconfig.json pyrightconfig.json.old

# 4. Test
~/.local/bin/uv run basedpyright | tee basedpyright_output.txt

# 5. Review
less basedpyright_output.txt
```

### Revert if Needed
```bash
cp pyproject.toml.backup.YYYYMMDD pyproject.toml
mv pyrightconfig.json.old pyrightconfig.json
```

---

## Expected Timeline

| Phase | Duration | Effort | Output |
|-------|----------|--------|--------|
| 1. Apply config | 1 hour | Low | New warnings visible |
| 2. Fix critical errors | 2-4 hours | Medium | 0 errors |
| 3. Categorize warnings | 1 hour | Low | Priority list |
| 4. Fix high-value warnings | 2-3 weeks | Medium-High | 50-150 bugs prevented |
| 5. Promote to errors | 1 week | Low | Stricter checks |
| 6. Recommended mode | 1 week | Medium | Full type safety |
| **TOTAL** | **6-8 weeks** | **Medium** | **Type-safe codebase** |

---

## Benefits After Migration

### Bugs Prevented
- ✅ None-related crashes (OptionalMemberAccess)
- ✅ Attribute typos (UnknownMemberType)
- ✅ Type mismatches (UnknownParameterType)
- ✅ Import errors (MissingImports)
- ✅ Undefined variables (UndefinedVariable)

### Code Quality
- ✅ Better type hints throughout
- ✅ Clearer function signatures
- ✅ Reduced technical debt
- ✅ Easier refactoring

### Developer Experience
- ✅ Better IDE autocomplete
- ✅ Earlier error detection
- ✅ Fewer runtime surprises
- ✅ Self-documenting code

---

## Decision Required

**Choose one:**

1. ✅ **Apply gradual config** (`pyproject.toml.gradual`)
   - Start with warnings
   - Fix incrementally
   - Promote to errors over time

2. ⚡ **Apply strict config** (`pyproject.toml.proposed`)
   - Immediate strictness
   - Fix sprint required
   - Maximum type safety

3. ❌ **Keep current** (not recommended)
   - No changes
   - Technical debt continues

---

## Next Steps

After you decide, I can:
1. Apply the configuration
2. Run basedpyright and analyze output
3. Create priority list of issues to fix
4. Help fix critical issues first

**What would you like to do?**
