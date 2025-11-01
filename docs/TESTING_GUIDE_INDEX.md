# Testing Guide Index

**Primary Documentation**: All testing guidance is consolidated in one place.

## Main Guide

📖 **[TESTING.md](../TESTING.md)** - The comprehensive testing guide

Contains everything you need:
- Quick Start (running tests)
- Test Isolation and Parallel Execution (critical for reliability)
- Testing Principles (UNIFIED_TESTING_GUIDE philosophy)
- Anti-Pattern Replacements
- Test Patterns by Category
- Debugging Workflow
- Best Practices Summary

## Supplementary Documentation

🔍 **[TEST_ISOLATION_CASE_STUDIES.md](TEST_ISOLATION_CASE_STUDIES.md)** - Deep dive into real debugging examples
- Case Study 1: QTimer Resource Leak
- Case Study 2: Global Config State Contamination  
- Case Study 3: Module-Level Cache Contamination
- Includes before/after code, timelines, and verification

## Archived Documents

📦 **[docs/archive/TESTING_BEST_PRACTICES_2025-10-31.md](archive/TESTING_BEST_PRACTICES_2025-10-31.md)**
- Archived after consolidation into TESTING.md
- Kept for historical reference

## Quick Links

**Most Common Questions**:
- How do I run tests? → [TESTING.md > Quick Start](../TESTING.md#quick-start)
- Tests fail in parallel but pass alone? → [TESTING.md > Test Isolation](../TESTING.md#test-isolation-and-parallel-execution--critical)
- What are anti-patterns to avoid? → [TESTING.md > Anti-Pattern Replacements](../TESTING.md#anti-pattern-replacements)
- How do I debug failures? → [TESTING.md > Debugging](../TESTING.md#debugging-test-failures)
- Real debugging examples? → [TEST_ISOLATION_CASE_STUDIES.md](TEST_ISOLATION_CASE_STUDIES.md)

## Recent Updates

**2025-10-31**: Major consolidation
- Merged three overlapping guides into one authoritative TESTING.md
- Added comprehensive Test Isolation section
- Created detailed case studies document
- Fixed 3 flaky tests with proper isolation
- All 1,975 tests now pass consistently in parallel

---

**When in doubt, start with [TESTING.md](../TESTING.md)**
