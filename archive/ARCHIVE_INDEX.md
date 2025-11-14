# Archive Index - Obsolete Documentation

This directory contains documentation that has been superseded by newer, consolidated guides or represents completed historical work.

**Archive Date:** 2025-11-08
**Reason:** Comprehensive test configuration improvements completed, documentation consolidated

---

## Archive Structure

### `/audits/` - Completed Audit Reports (21 files)

Historical audit reports from systematic codebase reviews. These audits identified issues that have now been fixed.

**Superseded by:**
- Current codebase state (issues resolved)
- UNIFIED_TESTING_V2.MD (testing best practices)
- CONFTEST_IMPROVEMENTS_2025-11-08.md (recent improvements)

**Files:**
- `AUDIT_INDEX.md` - Master audit index
- `AUTOUSE_FIXTURE_AUDIT.md` - Autouse fixture patterns
- `QT_APP_CREATION_AUDIT.md` - QApplication creation patterns
- `QT_AUDIT_INDEX.md` - Qt-specific audit index
- `QT_CLEANUP_AUDIT_INDEX.md` - Qt cleanup audit index
- `QT_CLEANUP_FIXES.md` - Qt cleanup fixes applied
- `QT_RESOURCE_CLEANUP_AUDIT.md` - Resource cleanup audit
- `QT_RESOURCE_CLEANUP_AUDIT_FINAL.md` - Final cleanup audit
- `QT_TESTING_HYGIENE_AUDIT.md` - Testing hygiene audit
- `QT_VIOLATIONS_DETAILED.md` - Detailed violation list
- `QT_WIDGET_PARENT_AUDIT.md` - Widget parent parameter audit
- `README_SYNC_AUDIT.md` - Documentation sync audit
- `SINGLETON_AUDIT_REPORT.md` - Singleton pattern audit
- `STATE_ISOLATION_AUDIT.md` - Test isolation audit
- `SYNCHRONIZATION_AUDIT_REPORT.md` - Synchronization audit
- `SYNC_AUDIT_FINAL_REPORT.md` - Final sync audit
- `SYNC_AUDIT_FINDINGS.md` - Sync audit findings
- `SYNC_AUDIT_INDEX.md` - Sync audit index
- `TEST_ISOLATION_AUDIT.md` - Test isolation analysis
- `TEST_ISOLATION_AUDIT_INDEX.md` - Isolation audit index
- `VIOLATIONS_INDEX.md` - Violation tracking index

### `/quick-references/` - Superseded Quick References (3 files)

Quick reference guides that have been consolidated into comprehensive documentation.

**Superseded by:**
- UNIFIED_TESTING_V2.MD (comprehensive testing guide)
- CLAUDE.md (development guidelines)
- CONFTEST_IMPROVEMENTS_SUMMARY.md (recent improvements summary)

**Files:**
- `QT_QUICK_REFERENCE.md` - Qt testing quick reference
- `STATE_ISOLATION_QUICK_REFERENCE.md` - Test isolation patterns
- `REMEDIATION_README.md` - Remediation guide

### `/testing-guides/` - Superseded Testing Guides (4 files)

Testing guides that have been consolidated into UNIFIED_TESTING_V2.MD or represent completed remediation work.

**Superseded by:**
- UNIFIED_TESTING_V2.MD (canonical testing guide covering WSL, test isolation, Qt testing, etc.)
- CONFTEST_IMPROVEMENTS_2025-11-08.md (recent improvements documentation)

**Files:**
- `WSL-TESTING.md` - WSL-specific testing guide (now covered in UNIFIED_TESTING_V2.MD)
- `TESTING_GUIDE_INDEX.md` - Testing guide index (superseded by UNIFIED_TESTING_V2.MD)
- `TEST_ISOLATION_CASE_STUDIES.md` - Case studies (patterns now in UNIFIED_TESTING_V2.MD)
- `XDIST_REMEDIATION_ROADMAP.md` - Completed remediation roadmap (✅ all phases done)

---

## Active Documentation (Keep These)

### Root Level
- **CLAUDE.md** - Primary development guidelines for Claude Code
- **UNIFIED_TESTING_V2.MD** - Canonical testing guide (replaces all testing-related docs)
- **CONFTEST_IMPROVEMENTS_SUMMARY.md** - Recent test configuration improvements (2025-11-08)
- **README.md** - Project README
- **ACTIVE_DOCUMENTATION.md** - Index of active documentation
- **KNOWN_ISSUES.md** - Current known issues
- **PERFORMANCE_OPTIMIZATIONS.md** - Performance guidance
- **POST_COMMIT_BUNDLE_GUIDE.md** - Bundle deployment system
- **AUTO_PUSH_SYSTEM.md** - Auto-push system documentation
- **AUTO_PUSH_TROUBLESHOOTING_DO_NOT_DELETE.md** - Critical troubleshooting
- **SECURITY_CONTEXT.md** - Security posture documentation

### `/docs/`
- **CONFTEST_IMPROVEMENTS_2025-11-08.md** - Detailed changelog for test improvements
- **CUSTOM_LAUNCHER_DOCUMENTATION.md** - Launcher system documentation
- **NUKE_PLATE_WORKFLOW.md** - Nuke workflow documentation
- **QT_WARNING_DETECTION.md** - Qt warning detection
- **SIMPLE_VS_COMPLEX_NUKE_LAUNCH.md** - Nuke launch patterns

### `/docs/refactoring_history/`
- **APPLICATION_IMPROVEMENT_PLAN.md** - Long-term improvement plans
- **COMPREHENSIVE_AGENT_REPORT.md** - Agent audit report
- **TEST_REFACTORING_SUMMARY.md** - Test refactoring history

---

## Why Archive Now?

**Test configuration improvements completed (2025-11-08):**
- 14 critical improvements to conftest.py
- Comprehensive pyproject.toml updates
- All audits resolved, fixes implemented
- Documentation consolidated into UNIFIED_TESTING_V2.MD

**Benefits of archiving:**
- ✅ Reduced clutter in root directory (21 fewer files)
- ✅ Clear signal of what's active vs. historical
- ✅ Preserved historical context for future reference
- ✅ Easier to find current, authoritative documentation

---

## How to Use Archived Documentation

**When to reference archived docs:**
- Understanding historical context of design decisions
- Investigating why certain patterns exist in the codebase
- Learning from past audit methodologies
- Tracing the evolution of testing practices

**When NOT to reference archived docs:**
- Learning current best practices → Use UNIFIED_TESTING_V2.MD
- Writing new tests → Use UNIFIED_TESTING_V2.MD + CLAUDE.md
- Troubleshooting → Use ACTIVE_DOCUMENTATION.md + current guides
- Onboarding → Start with README.md + CLAUDE.md + UNIFIED_TESTING_V2.MD

---

## Restoration

If any archived documentation needs to be restored to active status:

```bash
# Example: Restore a quick reference
git mv archive/quick-references/QT_QUICK_REFERENCE.md ./
```

However, consider whether the information should instead be:
1. Added to UNIFIED_TESTING_V2.MD (for testing guidance)
2. Added to CLAUDE.md (for development guidelines)
3. Added to a new focused guide (if topic is large enough)

---

**Last Updated:** 2025-11-08
**Archived By:** Comprehensive test configuration improvements project
