# Basedpyright Migration Results

**Date:** 2025-11-02
**Configuration:** Gradual transition (standard mode)

---

## Summary

✅ **Configuration successfully applied!**

### Current Status
```
4 errors, 878 warnings, 0 notes
```

### Before vs After

| Metric | Before (Basic Mode) | After (Standard Mode) | Change |
|--------|---------------------|----------------------|---------|
| Errors | 0 | 4 | +4 |
| Warnings | 0 | 878 | +878 |
| Type Checking Mode | basic | standard | ↑ |
| Hidden Issues | ~200-500 | 0 | Found! |

---

## Error Analysis (4 CRITICAL)

All 4 errors are in the same file: `threede_recovery_dialog.py`

### Issues Found

```python
# Line 34 - ThreeDERecoveryDialog
error: Base classes define method "closeEvent" in incompatible way
error: Base classes define method "keyPressEvent" in incompatible way

# Line 279 - ThreeDERecoveryResultDialog
error: Base classes define method "closeEvent" in incompatible way
error: Base classes define method "keyPressEvent" in incompatible way
```

**Root Cause:** Multiple inheritance conflict
- Classes inherit from both `QtWidgetMixin` and `QDialog`
- Both define `closeEvent` and `keyPressEvent` with incompatible signatures
- Method Resolution Order (MRO) is ambiguous

**Fix Required:** Resolve the inheritance conflict

**Priority:** 🔴 HIGH - These are real design issues

---

## Warning Breakdown (878 TOTAL)

### By Category

| Category | Count | % of Total | Priority |
|----------|-------|------------|----------|
| `reportUnannotatedClassAttribute` | 750 | 85.4% | 🟡 Medium |
| `reportUnknownVariableType` | 29 | 3.3% | 🟠 High |
| `reportUnnecessaryTypeIgnoreComment` | 16 | 1.8% | 🟢 Low |
| `reportUnknownMemberType` | 10 | 1.1% | 🟠 High |
| `reportOptionalMemberAccess` | 2 | 0.2% | 🔴 Critical |
| `reportUnusedVariable` | 1 | 0.1% | 🟢 Low |
| `reportUnknownParameterType` | 1 | 0.1% | 🟠 High |
| Other (uncategorized) | 69 | 7.8% | Various |

---

## Priority 1: Fix Critical Errors (4 errors)

### File: `threede_recovery_dialog.py`

**Problem:** Multiple inheritance with incompatible method signatures

**Two solutions:**

#### Option A: Use Composition Instead of Multiple Inheritance
```python
# Current (broken)
class ThreeDERecoveryDialog(QtWidgetMixin, QDialog):
    # Multiple inheritance causes MRO conflict
    pass

# Fixed - Use composition
class ThreeDERecoveryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Manually integrate QtWidgetMixin functionality
        self._widget_helper = QtWidgetMixin()
        # Copy needed methods from mixin
```

#### Option B: Fix Method Signatures to Match
```python
class QtWidgetMixin:
    def closeEvent(self, event: QCloseEvent) -> None:  # Match QDialog signature
        # Implementation

    def keyPressEvent(self, event: QKeyEvent) -> None:  # Match QDialog signature
        # Implementation
```

**Recommendation:** Option B - Fix the mixin signatures to match Qt's expectations

**Estimated Time:** 1-2 hours

---

## Priority 2: Fix High-Value Warnings

### 2.1 Optional Member Access (2 warnings) - PREVENTS CRASHES

These catch potential `None` errors:

```python
# Example issue
obj = get_optional_thing()  # Returns Thing | None
obj.method()  # ❌ Warning: obj might be None!

# Fix
if obj is not None:
    obj.method()  # ✅ Safe
```

**Impact:** HIGH - Prevents runtime crashes
**Effort:** LOW - Usually 1-2 line fixes
**Time:** 15 minutes

---

### 2.2 Unknown Variable Types (29 warnings)

These indicate type inference failures:

```python
# Example
data = json.loads(content)  # Type is Unknown
data["key"]  # ❌ Warning: type is unknown

# Fix - Add type annotation
data: dict[str, Any] = json.loads(content)
# OR use TypedDict
data: MyDataType = json.loads(content)
```

**Impact:** MEDIUM - Type checking stops working for these variables
**Effort:** MEDIUM - Need to add proper type hints
**Time:** 2-4 hours

---

### 2.3 Unknown Member Types (10 warnings)

Similar to above, but for object attributes:

```python
# Example
obj.attribute  # ❌ Warning: type of attribute is unknown

# Fix - Add type hints to class
class MyClass:
    attribute: str  # ✅ Now type is known
```

**Impact:** MEDIUM
**Effort:** MEDIUM
**Time:** 1-2 hours

---

## Priority 3: Code Cleanup

### 3.1 Unnecessary Type Ignore Comments (16 warnings)

These `# type: ignore` comments are no longer needed:

**Files affected:**
- `capture_vfx_structure.py` (3 warnings)
- `base_item_model.py` (1 warning)
- Others...

**Action:** Remove or update to specific rules
```python
# Bad
result = something()  # type: ignore

# Good (if still needed)
result = something()  # type: ignore[specific-rule]

# Best (if no longer needed)
result = something()  # No comment needed!
```

**Time:** 1 hour

---

### 3.2 Unused Variables (1 warning)

Self-explanatory - remove unused variable.

**Time:** 5 minutes

---

## Priority 4: Unannotated Class Attributes (750 warnings)

### The Big One: 85% of All Warnings

**Pattern:**
```python
class MyClass:
    def __init__(self):
        self.attribute = value  # ❌ Warning: no type annotation
```

**Why This Happens:**
The new `reportUnannotatedClassAttribute` setting requires explicit type annotations on all class attributes.

**Two Approaches:**

#### Approach A: Add Type Annotations (Recommended)
```python
class MyClass:
    attribute: str  # ✅ Type annotation

    def __init__(self):
        self.attribute = "value"
```

#### Approach B: Use @final Decorator
```python
from typing import final

@final
class MyClass:  # ✅ @final classes don't need attribute annotations
    def __init__(self):
        self.attribute = "value"
```

**Recommendation:** Approach A for most classes, Approach B for small utility classes

**Estimated Time:**
- Quick pass (add annotations): 8-12 hours
- Thorough (with review): 2-3 weeks

**Strategy:**
1. Start with most-used classes (Config, managers, models)
2. Do 50-100 per day
3. Use automated tools where possible

---

## Quick Win Opportunities

### Fix These First (< 2 hours total)

1. **4 errors in threede_recovery_dialog.py** (1-2 hours)
   - Fix method signature conflicts

2. **2 OptionalMemberAccess warnings** (15 min)
   - Add None checks

3. **16 unnecessary type: ignore comments** (1 hour)
   - Remove or update

4. **1 unused variable** (5 min)
   - Remove it

**Total Quick Wins:** ~3 hours → **23 issues fixed**

---

## Gradual Rollout Plan

### Week 1: Critical Issues
- [ ] Fix 4 errors in threede_recovery_dialog.py
- [ ] Fix 2 OptionalMemberAccess warnings
- [ ] Remove 16 unnecessary type: ignore
- [ ] Remove 1 unused variable

**Result:** 0 errors, 855 warnings

---

### Week 2: Type Inference Issues
- [ ] Fix 29 UnknownVariableType warnings
- [ ] Fix 10 UnknownMemberType warnings
- [ ] Fix 1 UnknownParameterType warning

**Result:** 0 errors, 815 warnings

---

### Weeks 3-6: Class Annotations (200/week)
- [ ] Week 3: Annotate Config class + core models (200)
- [ ] Week 4: Annotate controllers (200)
- [ ] Week 5: Annotate managers + utilities (200)
- [ ] Week 6: Remaining classes (150)

**Result:** 0 errors, ~0 warnings

---

### Week 7: Promote to Recommended Mode

Once all warnings are fixed, update config:

```toml
# pyproject.toml
[tool.basedpyright]
typeCheckingMode = "recommended"  # Up from "standard"

# Promote warnings to errors
reportOptionalMemberAccess = "error"
reportUnknownMemberType = "error"
# ... etc
```

---

## Automation Opportunities

### Script to Add Class Attribute Annotations

```python
# add_annotations.py
import ast
import re

def add_class_attribute_annotations(filepath):
    """Add type annotations to class attributes."""
    with open(filepath, 'r') as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Find __init__ and extract attribute assignments
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    # Analyze self.x = value patterns
                    # Generate type annotations
                    pass

    # Write back with annotations
```

**Note:** This is complex - would need careful implementation

---

## Configuration Notes

### What Changed

**Before (pyproject.toml - basic mode):**
```toml
typeCheckingMode = "basic"
pythonVersion = "3.12"  # Wrong - should be 3.11!
reportMissingImports = false
reportUnknownMemberType = false
# ... 6 more disabled checks
```

**After (pyproject.toml.gradual - standard mode):**
```toml
typeCheckingMode = "standard"
pythonVersion = "3.11"  # Correct for VFX workstation!
reportMissingImports = "error"
reportUnknownMemberType = "warning"
# ... checks enabled as warnings
```

**Conflicts Resolved:**
- ✅ Removed duplicate pyrightconfig.json
- ✅ Fixed Python version mismatch
- ✅ Fixed venvPath to Linux filesystem
- ✅ Cleaned up include/exclude lists

---

## Expected Benefits

### After Full Migration

**Bugs Prevented:**
- ✅ None-related crashes (OptionalMemberAccess)
- ✅ Attribute typos caught at type-check time
- ✅ Type mismatches caught before runtime
- ✅ Better refactoring safety

**Code Quality:**
- ✅ Self-documenting type hints
- ✅ Better IDE autocomplete
- ✅ Clearer interfaces
- ✅ Easier onboarding for new developers

**Development Speed:**
- ✅ Catch errors in editor (not at runtime)
- ✅ Faster debugging
- ✅ Confident refactoring
- ✅ Less time reading code to understand types

---

## Rollback Instructions

If you need to revert:

```bash
# Restore old configs
cp pyproject.toml.backup.20251102 pyproject.toml
mv pyrightconfig.json.old pyrightconfig.json

# Verify rollback
~/.local/bin/uv run basedpyright
# Should show: 0 errors, 0 warnings
```

---

## Next Steps

**Choose your path:**

1. **Quick wins first** (Recommended)
   - Fix 4 errors + 19 warnings in < 3 hours
   - Get to 0 errors immediately

2. **Aggressive**
   - Fix everything in 2 weeks
   - Requires dedicated sprint

3. **Very gradual**
   - Fix 10-20 warnings per week
   - Low disruption over 2-3 months

**My recommendation:** Start with quick wins (Week 1 plan), then do 50-100 class annotations per week.

---

## Commands

### Check current status
```bash
~/.local/bin/uv run basedpyright | tee status.txt
```

### Count warnings by type
```bash
grep "warning:" basedpyright_output.txt | \
  sed 's/.*(\(report[^)]*\)).*/\1/' | \
  sort | uniq -c | sort -rn
```

### Find specific warning type
```bash
grep "reportOptionalMemberAccess" basedpyright_output.txt
```

### Re-run after fixes
```bash
~/.local/bin/uv run basedpyright --watch
```

---

**Status:** ✅ Configuration successfully applied and analyzed!
**Next:** Fix the 4 critical errors in threede_recovery_dialog.py
