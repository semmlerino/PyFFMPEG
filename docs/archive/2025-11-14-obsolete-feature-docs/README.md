# Obsolete Feature Documentation Archive

**Archive Date**: 2025-11-14
**Reason**: Documentation superseded by current implementation or consolidated into other docs

---

## Archived Documentation

### Feature Documentation (Obsolete)

1. **SIMPLE_VS_COMPLEX_NUKE_LAUNCH.md** (4.7K)
   - Historical "before/after" comparison of Nuke launcher refactoring
   - Compared over-engineered 1,500+ line implementation with simplified approach
   - Obsolete: Refactoring complete, simplified approach is now the standard

2. **NUKE_PLATE_WORKFLOW.md** (16K)
   - Documented transition from workspace-based to plate-based Nuke workflow
   - Last updated: 2025-10-14 (commit a77b8cb)
   - Obsolete: Feature implemented and integrated into main codebase

3. **QT_WARNING_DETECTION.md** (7.9K)
   - Described Qt warning detection system in testing
   - Three-layer detection: unit tests, integration tests, CI enforcement
   - Obsolete: Functionality covered in `UNIFIED_TESTING_V2.MD`

### Analysis Reports (Obsolete)

4. **ERROR_HANDLING_ANALYSIS.md** (28K)
   - Analysis of launcher/terminal/command system error handling
   - Analysis date: 2025-11-14
   - Identified 5 critical issues in error propagation and recovery
   - Obsolete: All issues fixed in Phase 1-6 (see `Terminal_Issue_History_DND.md`)

### System Documentation (Redundant/Obsolete)

5. **AUTO_PUSH_SYSTEM.md** (2.9K)
   - Documented the post-commit hook auto-push system
   - Obsolete: Fully covered in `CLAUDE.md` Auto-Push System section

6. **POST_COMMIT_BUNDLE_GUIDE.md** (36K)
   - Comprehensive setup guide for post-commit bundling system
   - Obsolete: Essential information consolidated into `CLAUDE.md`

7. **SECURITY_CONTEXT.md** (1.5K)
   - Documented security stance for the VFX pipeline tool
   - Obsolete: Information merged into `CLAUDE.md` Security Posture section

8. **CUSTOM_LAUNCHER_DOCUMENTATION.md** (70K)
   - Comprehensive documentation for CustomLauncherManager feature
   - Obsolete: Feature exists only in examples/tests, not production code
   - Custom launcher functionality limited to example implementations

### Refactoring History (Obsolete)

9. **refactoring_history/APPLICATION_IMPROVEMENT_PLAN.md** (8.5K)
   - Historical improvement plan from early refactoring phase
   - Obsolete: Refactoring completed, plan fully executed

10. **refactoring_history/COMPREHENSIVE_AGENT_REPORT.md** (6.3K)
    - Agent analysis report from refactoring phase
    - Obsolete: Findings incorporated into codebase

11. **refactoring_history/TEST_REFACTORING_SUMMARY.md** (11K)
    - Summary of test refactoring efforts
    - Obsolete: Test suite fully refactored and documented in `UNIFIED_TESTING_V2.MD`

---

## Current Active Documentation

### Main Documentation (Keep Active)
- `CLAUDE.md` - Project instructions and development guide
- `UNIFIED_TESTING_V2.MD` - Comprehensive testing documentation
- `README.md` - Project overview

### Active Feature Documentation (Keep Active)
- `docs/Terminal_Issue_History_DND.md` - Terminal bug tracking and resolution history

### Previous Archives
- `docs/archive/2025-11-14-multi-agent-analysis/` - Multi-agent analysis (pre-Phase 1-6 fixes)
- `docs/analysis-archive/2025-01-14-threading-fixes/` - Threading fix analysis
- `docs/analysis-archive/2025-11-13-previous-fixes/` - Previous bug fix documentation

---

## Archive Policy

Documentation is archived when:
- Feature is fully implemented and stabilized
- Analysis/findings fully incorporated into codebase
- Content superseded by more comprehensive documentation
- Historical context no longer needed for active development

Archived docs are preserved for historical reference but not maintained.
