# Nuke Plate-Based Workflow

**Last Updated**: 2025-10-14
**Version**: 1.0
**Commit**: a77b8cb (feat: Add plate-based Nuke launcher with direct file creation)

---

## Overview

ShotBot's Nuke launcher now uses a **plate-based workflow** that organizes Nuke scripts by plate directories (FG01, PL01, BG01, etc.) instead of a generic workspace directory. This provides better organization for multi-plate shots and clearer version management.

### What Changed

**Old Workflow (Workspace-Based)**:
- Single directory: `{workspace}/comp/nuke/`
- Script naming: `{shot}_scene_v{version}.nk`
- No plate differentiation

**New Workflow (Plate-Based)**:
- Plate directories: `{workspace}/comp/nuke/FG01/`, `{workspace}/comp/nuke/PL01/`, etc.
- Script naming: `{shot}_mm-default_{plate}_scene_v{version}.nk`
- Each plate has its own versioned scripts

### Why This Matters

1. **Multi-plate shots**: Cleanly separates foreground, background, and element plates
2. **Version clarity**: Each plate has independent version history
3. **Pipeline integration**: Matches VFX studio conventions (mm-default naming)
4. **Easier collaboration**: Artists can work on different plates simultaneously

---

## Plate Priority System

The launcher automatically selects the most appropriate plate based on a priority system.

### Priority Order (Lower = Higher Priority)

| Plate Type | Priority | Usage | Example |
|------------|----------|-------|---------|
| **FG** | 0 | Primary foreground plates | FG01, FG02 |
| **PL** | 0.5 | Primary turnover plates | PL01, PL02 |
| **BG** | 1 | Primary background plates | BG01, BG02 |
| **COMP** | 1.5 | Composite plates | COMP01 |
| **EL** | 2 | Element plates | EL01, EL02 |
| **BC** | 10 | Background clean (reference only) | BC01 |
| **\*** | 12 | Unknown plate types | Any other |

### Configuration

Priorities are defined in `config.py`:

```python
# config.py
TURNOVER_PLATE_PRIORITY: ClassVar[dict[str, float]] = {
    "FG": 0,     # Primary foreground plates - USE THESE
    "PL": 0.5,   # Primary turnover plates - USE THESE
    "BG": 1,     # Primary background plates - USE THESE
    "COMP": 1.5, # Composite plates - USE IF NEEDED
    "EL": 2,     # Element plates - USE IF NEEDED
    "BC": 10,    # Background clean plates - SKIP (reference only)
    "*": 12,     # All others lowest priority
}
```

### Why Priorities Matter

**Example Scenario**: Shot has FG01, PL01, BG01, and BC01 plates.

- Without priorities: Random selection or alphabetical (might choose BC01)
- With priorities: Chooses FG01 (priority 0) → correct primary plate

**Critical**: BC plates are "background clean" (reference only, not for comp). Priority 10 ensures they're never selected unless no other plates exist.

### Historical Bug: PL Priority Misconfiguration

**Bug** (Commit a77b8cb): PL plates had priority 10 (reference-only level)
**Impact**: Turnover plates were skipped, breaking VFX workflow
**Fix**: Changed PL priority from 10 → 0.5 (between FG and BG)
**Prevention**: `test_config.py` now validates priority ordering

---

## Script Naming Convention

### Format

```
{shot}_mm-default_{plate}_scene_v{version}.nk
```

### Examples

| Show | Sequence | Shot | Plate | Version | Full Script Name |
|------|----------|------|-------|---------|------------------|
| test_show | seq01 | shot01 | FG01 | 1 | `seq01_shot01_mm-default_FG01_scene_v001.nk` |
| broken_eggs | ep101 | sh0010 | PL01 | 3 | `ep101_sh0010_mm-default_PL01_scene_v003.nk` |
| gator | seq02 | shot15 | BG01 | 12 | `seq02_shot15_mm-default_BG01_scene_v012.nk` |

### Naming Components

- **{shot}**: Full shot name (sequence + shot number)
- **mm-default**: Pipeline convention (matchmove default template)
- **{plate}**: Plate identifier (FG01, PL01, etc.)
- **scene**: Fixed literal
- **v{version}**: Zero-padded version (v001, v002, ..., v100)

### Directory Structure

```
workspace/
└── comp/
    └── nuke/
        ├── FG01/
        │   ├── seq01_shot01_mm-default_FG01_scene_v001.nk
        │   ├── seq01_shot01_mm-default_FG01_scene_v002.nk
        │   └── seq01_shot01_mm-default_FG01_scene_v003.nk
        ├── PL01/
        │   └── seq01_shot01_mm-default_PL01_scene_v001.nk
        └── BG01/
            ├── seq01_shot01_mm-default_BG01_scene_v001.nk
            └── seq01_shot01_mm-default_BG01_scene_v002.nk
```

---

## Version Detection and Incrementing

The launcher automatically detects existing versions and calculates the next version number.

### How Version Detection Works

1. **Scan plate directory** for existing scripts matching the pattern
2. **Parse version numbers** from filenames using regex
3. **Find maximum version** across all discovered scripts
4. **Return next version** (max + 1)

### Example: Version Gaps

**Scenario**: Plate directory contains:
- `seq01_shot01_mm-default_FG01_scene_v001.nk`
- `seq01_shot01_mm-default_FG01_scene_v003.nk` (v002 was deleted)

**Behavior**: Next version = **v004** (not v002)

**Rationale**: Prevents version collisions if deleted versions are restored from backup.

### Implementation

```python
# From plate_discovery.py
def get_next_script_version(
    workspace_path: str,
    shot_name: str,
    plate_name: str
) -> int:
    """Get the next available script version number.

    Scans existing scripts and returns max_version + 1.
    Handles gaps (v001, v003 exists → returns 4).
    """
    existing_scripts = find_existing_scripts(workspace_path, shot_name, plate_name)
    if not existing_scripts:
        return 1

    max_version = max(version for _, version in existing_scripts)
    return max_version + 1
```

---

## PlateDiscovery Module

The core functionality is provided by the `plate_discovery.py` module with static methods.

### Key Methods

#### `discover_available_plates(workspace_path: str, shot_name: str) -> list[str]`

Lists all available plate directories for a shot.

**Returns**: Sorted list of plate names (e.g., `["FG01", "PL01", "BG01"]`)

**Filters**: Only returns plates from `TURNOVER_PLATE_PRIORITY` (excludes unknown plates)

#### `find_existing_scripts(workspace_path: str, shot_name: str, plate_name: str) -> list[tuple[Path, int]]`

Finds all existing Nuke scripts for a specific plate.

**Returns**: List of `(script_path, version)` tuples, sorted by version (newest first)

**Example**:
```python
[
    (Path(".../FG01/shot01_mm-default_FG01_scene_v003.nk"), 3),
    (Path(".../FG01/shot01_mm-default_FG01_scene_v001.nk"), 1),
]
```

#### `get_next_script_version(workspace_path: str, shot_name: str, plate_name: str) -> int`

Calculates the next available version number.

**Returns**: Integer version number (1 if no scripts exist)

#### `get_script_directory(workspace_path: str, plate_name: str) -> Path`

Constructs the plate script directory path.

**Returns**: `{workspace}/comp/nuke/{plate_name}`

#### `construct_script_path(workspace_path: str, shot_name: str, plate_name: str, version: int) -> Path`

Builds the full script path with proper naming convention.

**Returns**: Full path to script file

---

## Launcher Integration

### NukeLaunchHandler

The `nuke_launch_handler.py` module orchestrates the plate-based workflow.

#### Workflow Steps

1. **Plate Selection**:
   - User selects plate (or auto-select based on priority)
   - Launcher identifies plate directory

2. **Script Discovery**:
   - Call `PlateDiscovery.find_existing_scripts()`
   - Present options: open latest or create new

3. **Open Latest** (if scripts exist):
   - Get latest version from discovered scripts
   - Launch Nuke with that script

4. **Create New** (if no scripts or user requests):
   - Call `get_next_script_version()` for version number
   - Generate script with `NukeScriptGenerator`
   - Launch Nuke with new script

#### Options

| Option | Description | Behavior |
|--------|-------------|----------|
| `open_latest_scene` | Open newest version | Finds v003 if v001, v002, v003 exist |
| `create_new_file` | Create new version | Creates v004 using get_next_script_version() |
| `include_raw_plate` | Include plate media | Loads plate EXR into script |
| `include_undistortion` | Include lens undistortion | Loads undistortion node |

---

## Testing

### Test Coverage

The plate-based workflow has comprehensive test coverage in `tests/unit/test_plate_discovery.py`:

- **26 tests** covering all PlateDiscovery functionality
- **527 lines** of test code

### Critical Test Cases

#### Plate Priority Tests (6 tests)

```python
def test_pl_preferred_over_bg():
    """Test PL01 is chosen over BG01 due to higher priority.

    Regression test for bug where PL priority was 10 instead of 0.5.
    """
    # Creates both PL01 and BG01 plates
    # Asserts PL01 is selected (priority 0.5 < 1)
```

#### Version Detection Tests (5 tests)

```python
def test_get_next_script_version_handles_gaps():
    """Test version incrementing with gaps.

    If v001 and v003 exist (v002 deleted), should return v004.
    """
```

#### Edge Case Tests (11 tests)

- Missing plate directories
- Empty plate directories
- Malformed script names
- Permission errors
- Non-existent workspaces

### Running Plate Discovery Tests

```bash
# Run all plate discovery tests
uv run pytest tests/unit/test_plate_discovery.py -v

# Run specific test
uv run pytest tests/unit/test_plate_discovery.py::test_pl_preferred_over_bg -v

# Run with coverage
uv run pytest tests/unit/test_plate_discovery.py --cov=plate_discovery --cov-report=term-missing
```

### Test Execution Time

- **Sequential**: ~2.5 seconds
- **Parallel**: Included in full suite (~70s for 1,919 tests)

---

## Configuration Reference

### Related Config Values

```python
# config.py

# Plate priorities (documented above)
TURNOVER_PLATE_PRIORITY: ClassVar[dict[str, float]] = { ... }

# Nuke script template
NUKE_SCRIPT_TEMPLATE: str = "{shot}_mm-default_{plate}_scene_v{version:03d}.nk"

# Script directory structure
NUKE_SCRIPT_DIRECTORY: str = "comp/nuke/{plate}"

# Version format (zero-padded to 3 digits)
VERSION_FORMAT: str = "v{version:03d}"
```

### Modifying Priorities

**When to change**:
- Studio pipeline conventions change
- New plate types are introduced
- Workflow requirements shift

**How to change safely**:
1. Update `TURNOVER_PLATE_PRIORITY` in `config.py`
2. Run validation: `uv run pytest tests/unit/test_config.py -v`
3. Verify `test_turnover_plate_priority_ordering` passes
4. Test manually with real shots

**What the tests check**:
- FG < PL < BG < COMP < EL < BC
- Primary plates (FG, PL, BG) all < 2
- Reference plates (BC) >= 10
- All values are numeric (not strings or None)

---

## Troubleshooting

### Issue: Wrong plate selected

**Symptom**: Launcher opens BC01 instead of FG01
**Cause**: Plate priorities misconfigured
**Solution**: Check `TURNOVER_PLATE_PRIORITY` in config.py, run `test_config.py`

### Issue: Version numbering skips

**Symptom**: Creates v005 when only v001 exists
**Cause**: Expected behavior (versions v002-v004 existed previously)
**Solution**: Not a bug - version gaps are intentional to prevent collisions

### Issue: Script not found

**Symptom**: "No existing scripts found for plate FG01"
**Cause**: Plate directory doesn't exist or scripts don't match naming convention
**Solution**:
1. Check directory: `{workspace}/comp/nuke/FG01/`
2. Verify naming: `{shot}_mm-default_FG01_scene_v*.nk`
3. Use "Create New" option to generate first script

### Issue: Multiple plates available, unclear which to use

**Symptom**: Shot has FG01, FG02, PL01, BG01
**Cause**: Multi-element shot with multiple plate types
**Solution**:
- FG plates: Use for primary foreground elements
- PL plates: Use for turnover/delivery plates
- BG plates: Use for background elements
- If unsure, choose lowest number (FG01, PL01, BG01)

---

## Migration Guide

### For Existing Projects

If you have existing Nuke scripts in the old workspace format:

1. **Identify plates**: Determine which plate each script corresponds to
2. **Create directories**: `mkdir -p {workspace}/comp/nuke/{plate}`
3. **Rename scripts**:
   - Old: `seq01_shot01_scene_v001.nk`
   - New: `seq01_shot01_mm-default_{plate}_scene_v001.nk`
4. **Move scripts**: `mv old_script.nk comp/nuke/{plate}/new_script.nk`

### Compatibility

- **Backward compatible**: Old scripts still work (just not discovered by new launcher)
- **Forward compatible**: New scripts follow industry conventions
- **Gradual migration**: Can use both old and new formats during transition

---

## Related Documentation

- **Configuration**: See `docs/CONFIG_VALIDATION.md` for priority validation
- **Testing**: See `TESTING.md` for test patterns and coverage
- **Implementation**: See `plate_discovery.py` and `nuke_launch_handler.py` source code
- **Bug History**: Commit a77b8cb (feat), fde59a4 (fix), 4b266b4 (fix)

---

## FAQ

**Q: Why "mm-default" in the script name?**
A: Matchmove default template convention from VFX pipeline standards.

**Q: Can I use custom plate names (e.g., "HERO01")?**
A: Yes, but they'll get priority 12 (lowest) unless added to `TURNOVER_PLATE_PRIORITY`.

**Q: What happens if I delete v002 and create a new script?**
A: New script becomes v004 (not v002) to avoid version collisions.

**Q: Can I have multiple FG plates (FG01, FG02, FG03)?**
A: Yes, all FG plates have equal priority (0). Use plate selector in launcher UI.

**Q: How do I revert to old workspace-based workflow?**
A: Not supported. Old scripts still work but won't be managed by new launcher.

---

**Questions or issues?** Check test cases in `test_plate_discovery.py` for usage examples.
