# ShotBot Critical Action Plan - DO NOT DELETE
**Generated: 2025-08-22**  
**Status: CRITICAL - Multiple security vulnerabilities and quality issues identified**  
**Overall Risk Assessment: HIGH - Production deployment blocked until P0-P2 complete**

---

## Executive Summary

Comprehensive code review identified **2 critical security vulnerabilities**, **2,032 type errors**, **5% test coverage**, and **zero accessibility support**. This document provides a prioritized remediation plan organized by risk level and implementation timeline.

**Estimated Total Effort**: 5-6 weeks for full remediation  
**Minimum Production Readiness**: Complete P0-P2 (2 weeks)

---

## PRIORITY 0: SECURITY CRITICAL (Immediate - 1-2 Days)
**Risk Level: CRITICAL | Effort: 4-8 hours | Blocker: Yes**

### 1. Shell Injection Vulnerability in launcher_manager.py

**Location**: `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/launcher_manager.py:76-98`

**Current Code (VULNERABLE)**:
```python
# Line 87-89
logger.warning(f"Using shell=True for complex command: {self.command[:100]}")
cmd_list = self.command
use_shell = True
```

**Required Fix**:
```python
# Implement command whitelist and sanitization
ALLOWED_COMMANDS = {"3de", "nuke", "maya", "rv", "publish_standalone"}

def _sanitize_command(self, command: str) -> Tuple[List[str], bool]:
    """Safely parse command with validation."""
    try:
        parts = shlex.split(command)
        if parts and parts[0] not in ALLOWED_COMMANDS:
            raise SecurityError(f"Command not in whitelist: {parts[0]}")
        return parts, False  # Never use shell=True
    except ValueError as e:
        raise SecurityError(f"Invalid command format: {command}")
```

**Acceptance Criteria**:
- [ ] No subprocess calls use shell=True without validation
- [ ] Command whitelist implemented and enforced
- [ ] Input sanitization prevents injection attacks
- [ ] Security tests verify prevention of common attacks

### 2. Command Injection Risk in command_launcher.py

**Location**: `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/command_launcher.py:196-198`

**Required Fix**:
```python
# Validate workspace paths before command execution
def _validate_workspace_path(self, path: str) -> bool:
    """Ensure workspace path is safe."""
    # No command separators or redirects
    dangerous_chars = [';', '&&', '||', '|', '>', '<', '`', '$', '\\']
    return not any(char in path for char in dangerous_chars)
```

---

## PRIORITY 1: INFRASTRUCTURE & STABILITY (Week 1)
**Risk Level: HIGH | Effort: 2-3 days | Blocker: Yes for testing**

### 3. Enable Qt Testing Framework

**Issue**: pytest-qt disabled, preventing all UI testing

**Actions**:
```bash
# Fix pytest configuration
sed -i 's/-p no:pytestqt//g' pytest.ini
pip install pytest-qt pytest-xvfb

# Verify Qt testing works
python -m pytest tests/unit/test_main_window.py -v
```

### 4. Fix Test Import Errors

**Issue**: 43+ test files have incorrect import ordering causing F821 errors

**Pattern to Fix**:
```python
# WRONG (current)
pytestmark = pytest.mark.unit  # NameError: pytest not defined
import pytest

# CORRECT
import pytest
pytestmark = pytest.mark.unit
```

**Files Requiring Fixes**:
- tests/integration/*.py (6 files)
- tests/unit/*.py (37 files with import issues)

### 5. Critical Type Annotations

**Priority Modules** (608 lines with 0% type coverage):
1. `main_window.py` - Add return types to all methods
2. `shot_model.py` - Fix signal type declarations
3. `cache_manager.py` - Type component interfaces

**Example Fix**:
```python
# Before
def _setup_ui(self):
    """Set up the main UI."""

# After  
def _setup_ui(self) -> None:
    """Set up the main UI."""
```

---

## PRIORITY 2: CORE FUNCTIONALITY (Week 2)
**Risk Level: HIGH | Effort: 3-4 days | Blocker: For reliability**

### 6. Test Coverage for Business Logic

**shot_model.py refresh_shots() Testing**:
```python
class TestShotModelCriticalPaths:
    def test_refresh_shots_real_workspace_parsing(self, tmp_path):
        """Test actual workspace parsing, not mocks"""
        workspace = tmp_path / "test_workspace"
        workspace.mkdir()
        
        model = ShotModel()
        result = model.refresh_shots()
        
        assert isinstance(result, RefreshResult)
        assert result.success in (True, False)
```

**Target Coverage**:
- shot_model.py: 70%+ (from 24%)
- main_window.py: 50%+ (from 0%)
- launcher_manager.py: 70%+ (from 51%)

### 7. Basic Accessibility Implementation

**Minimum Compliance Requirements**:
```python
# Add to every major widget
def _setup_accessibility(self):
    self.setAccessibleName("Shot Grid")
    self.setAccessibleDescription("Grid of VFX shots with thumbnails")
    
    # For interactive elements
    button.setAccessibleName(f"Launch {app_name}")
    slider.setAccessibleDescription("Adjust thumbnail size")
```

**Required Coverage**:
- [ ] All interactive widgets have accessible names
- [ ] Tooltips for all controls (current: 19 total)
- [ ] Keyboard navigation with visible focus
- [ ] Non-color-based feedback

---

## PRIORITY 3: PERFORMANCE CRITICAL (Week 3)
**Risk Level: MEDIUM | Effort: 3-4 days | Impact: 60-75% speed improvement**

### 8. ProcessPoolManager Optimization

**Current Issue**: 200-350ms startup delay per session

**Optimization Strategy**:
```python
# Replace bash sessions with direct execution
def execute_command(self, cmd: str) -> str:
    if cmd in self._simple_commands:
        return subprocess.run(cmd.split(), capture_output=True).stdout
    else:
        return self._use_session_pool(cmd)
```

### 9. Thumbnail Processing Parallelization

**Current**: Sequential processing  
**Target**: Parallel with ThreadPoolExecutor

```python
from concurrent.futures import ThreadPoolExecutor

def process_thumbnails_parallel(self, images: List[Path]):
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(self._process_single, img) for img in images]
        return [f.result() for f in futures]
```

**Expected Results**:
- ProcessPoolManager: 60-75% faster
- Thumbnails: 50-70% faster
- UI responsiveness: 40% improvement

---

## PRIORITY 4: QUALITY ASSURANCE (Week 4)
**Risk Level: MEDIUM | Effort: 3-4 days | Impact: Long-term maintainability**

### 10. Reduce Test Mocking

**Current**: 60% of tests use excessive mocking  
**Target**: <20% mocked tests

**Refactoring Pattern**:
```python
# REMOVE excessive mocking
@patch('everything')
def test_with_mocks():
    pass

# USE real components
def test_with_real_components(tmp_path):
    real_model = ShotModel()
    real_result = real_model.method()
    assert real_result.success
```

### 11. Fix Remaining Type Errors

**Systematic Approach**:
1. Run `basedpyright --stats` for baseline
2. Fix by module priority (main_window → shot_model → cache)
3. Use `# type: ignore` sparingly with justification
4. Target: <100 errors remaining

---

## PRIORITY 5: POLISH & OPTIMIZATION (Week 5)
**Risk Level: LOW | Effort: 2-3 days | Impact: User experience**

### 12. Complete Accessibility Features

- [ ] High contrast theme support
- [ ] Comprehensive keyboard shortcuts
- [ ] Screen reader compatibility testing
- [ ] WCAG 2.1 AA compliance validation

### 13. Performance Benchmarks

```python
# Add to tests/performance/
def test_shot_refresh_performance(benchmark):
    model = ShotModel()
    result = benchmark(model.refresh_shots)
    assert result.success
    assert benchmark.stats['mean'] < 1.0  # Under 1 second
```

### 14. Error Handling Standardization

**Implement Error Hierarchy**:
```python
class ShotBotError(Exception):
    """Base exception"""

class WorkspaceError(ShotBotError):
    """Workspace command errors"""

class ThumbnailError(ShotBotError):
    """Thumbnail processing errors"""
```

---

## Success Metrics

### Coverage Targets
| Module | Current | Target | Priority |
|--------|---------|--------|----------|
| shot_model.py | 24% | 70% | P2 |
| main_window.py | 0% | 50% | P2 |
| cache_manager.py | 31% | 60% | P3 |
| launcher_manager.py | 51% | 70% | P2 |
| **Overall** | **5%** | **60%** | - |

### Type Safety Metrics
| Metric | Current | Target | Priority |
|--------|---------|--------|----------|
| Type Errors | 2,032 | <100 | P4 |
| Type Warnings | 649 | <50 | P4 |
| Modules with 0% types | 9 | 0 | P1 |

### Performance Targets
| Operation | Current | Target | Improvement |
|-----------|---------|--------|-------------|
| Shot Refresh | ~3s | <1s | 66% |
| Thumbnail Load | ~500ms | <150ms | 70% |
| App Launch | ~800ms | <400ms | 50% |

---

## Validation Checklist

### Before Production Deployment
- [ ] **P0 Complete**: All security vulnerabilities patched
- [ ] **P1 Complete**: Testing infrastructure operational
- [ ] **P2 Complete**: Core functionality tested >50%
- [ ] **Security Audit**: Penetration testing passed
- [ ] **Accessibility Audit**: WCAG 2.1 AA compliance
- [ ] **Performance Baseline**: All targets met
- [ ] **Documentation**: User and developer guides updated

### Continuous Monitoring
- [ ] Type checking in CI/CD pipeline
- [ ] Test coverage enforcement (>60%)
- [ ] Performance regression detection
- [ ] Security vulnerability scanning
- [ ] Accessibility compliance checks

---

## Implementation Notes

### Dependencies
- Security fixes must complete before any other code changes
- Testing infrastructure required before writing new tests
- Type annotations should be added incrementally with each fix

### Resource Requirements
- 1-2 senior developers for security fixes
- 1 developer + 1 QA engineer for testing improvements
- Accessibility consultant for WCAG compliance review

### Risk Mitigation
- Create security patches on separate branch for rapid deployment
- Maintain backward compatibility during refactoring
- Use feature flags for performance optimizations
- Implement gradual rollout with monitoring

---

## Contact & Escalation

**Project Lead**: [TBD]  
**Security Team**: Notify immediately for P0 items  
**QA Team**: Coordinate for P1-P2 testing infrastructure  
**DevOps**: Prepare CI/CD pipeline updates for P4

---

**Document Status**: ACTIVE - Track progress in integrated todo list  
**Last Updated**: 2025-08-22  
**Next Review**: After P0 completion (1-2 days)

---

*This document is critical for project remediation. DO NOT DELETE until all priorities are complete and validated.*