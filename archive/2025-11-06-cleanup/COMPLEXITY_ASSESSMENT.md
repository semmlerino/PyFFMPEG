# Complexity Assessment

## Top 10 Worst Offenders (Truly Problematic)

### 🔴 Critical - Need Refactoring

1. **persistent_bash_session.py:104** - `_start_session()`
   - 167 statements, 53 branches, complexity 49
   - Verdict: God function - needs urgent refactoring

2. **command_launcher.py:266** - `launch_app()`
   - 130 statements, 41 branches, complexity 35, 11 returns
   - Verdict: God function - needs urgent refactoring

3. **nuke_undistortion_parser.py:252** - `_parse_standard_format()`
   - 109 statements, 30 branches, complexity 28
   - Verdict: Parsing logic - could extract sub-parsers

4. **command_launcher.py:582** - `launch_app_with_scene()`
   - 101 statements, 33 branches, complexity 28, 10 returns
   - Verdict: Complex launch logic - needs decomposition

5. **transfer_cli.py:128** - `main()`
   - 99 statements, 30 branches, complexity 26
   - Verdict: CLI main - could extract handlers

### 🟡 Moderate - Consider Refactoring

6. **nuke_undistortion_parser.py:67** - `_parse_copy_paste_format()`
   - 96 statements, 28 branches, complexity 26
   - Verdict: Parser - similar to #3

7. **persistent_bash_session.py:533** - `_read_with_backoff()`
   - 91 statements, 36 branches, complexity 33
   - Verdict: Complex I/O logic with retry - could simplify

8. **command_launcher.py:790** - `launch_app_with_scene_context()`
   - 86 statements, 26 branches, complexity 21, 8 returns
   - Verdict: Another launch variant - pattern emerging

9. **scene_discovery_coordinator.py:538** - `find_all_scenes_in_shows_truly_efficient_parallel()`
   - 78 statements, 19 branches, complexity 27
   - Verdict: Parallel coordination - could extract workers

10. **main_window.py:177** - `__init__()`
    - 78 statements, 16 branches
    - Verdict: Qt UI initialization - common but could extract setup methods

## Arguments Analysis (PLR0913)

**6 arguments** - 22 occurrences (mostly tests and templates)
- Verdict: Acceptable for Qt widgets and test fixtures

**7-8 arguments** - 10 occurrences
- Verdict: Border-line, review case-by-case

**9+ arguments** - 3 occurrences
- `launcher_manager.py:283` - 9 args
- `nuke_script_templates.py:88` - 11 args ⚠️
- Verdict: Too many, should use config objects

## Return Statements (PLR0911)

Most are 7-8 returns (validation/parsing) - likely acceptable
- `base_item_model.py:188` - 15 returns ⚠️
- `launcher/models.py:100` - 14 returns ⚠️
- Verdict: Review these two

## Recommendations

### Immediate Action (Critical Files)
1. Refactor `persistent_bash_session.py:_start_session()` 
2. Refactor `command_launcher.py` three main functions
3. Consider splitting `nuke_undistortion_parser.py` parsers

### Per-File Ignores (Acceptable Cases)
- Test files with 6 args (pytest fixtures)
- Qt UI `__init__` methods with 50-60 statements
- Simple parsing with 7-8 returns

### Threshold Adjustments
Consider:
```toml
max-args = 7              # Allow up to 7 (catch 9+)
max-branches = 20         # Allow up to 20 (catch 30+)  
max-statements = 70       # Allow up to 70 (catch 90+)
max-returns = 10          # Allow up to 10 (catch 14+)
```
