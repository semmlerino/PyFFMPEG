# ShotBot - Development Standards (Extended Reference)

> **Note**: See `CLAUDE.md` for canonical development standards. This memory contains additional details for quick AI context loading.

---

## Critical Import Rule

**ALWAYS** import `override` from `typing_extensions`, NOT `typing`:

```python
# CORRECT (Python 3.11 compatible)
from typing_extensions import override

# WRONG (Python 3.12+ only - will fail!)
from typing import override
```

---

## Ruff Disabled Rules Quick Reference

| Rule | Reason |
|------|--------|
| E501 | Line length handled by formatter |
| SLF001 | Private member access common in Qt |
| ARG002 | Qt callbacks often have unused args |
| T201 | Print statements intentional |
| G004 | Logging f-strings are readable |
| D | Using our own docstring style |
| PLR0913 | Qt widgets need many arguments |
| FBT001/002/003 | Boolean args common in GUI |

**Test-specific ignores**: S101 (asserts), ARG001 (fixtures), PLR2004 (magic values)

---

## Architecture Patterns Summary

- **Distinct Data Sources**: Each tab has own model stack
- **Generic Base Classes**: `BaseItemModel[T]` for 70-80% code reuse
- **Worker Pattern**: QThread for background operations
- **Dependency Injection**: Factory pattern for testability
- **Singleton**: ProcessPoolManager for subprocess management
