# VFX Environment Assumptions and Reality

This document captures the actual behavior of the BlueBolt VFX pipeline environment,
correcting and clarifying assumptions made in the Shotbot launcher code.

## Shell Initialization Chain

When a user opens a terminal or the launcher runs `bash -ilc`, the following chain executes:

```
~/.bashrc
  └→ /etc/bashrc
       └→ /etc/profile.d/*.sh
       └→ /software/bluebolt/vfxplatform/startup/current/bashrc.env
            └→ /shows/bluebolt/config/env.sh
            └→ $SHOW_CONFIG_PATH/show_config.sh (if exists)
            └→ $SHOW_CONFIG_PATH/tools_config.sh (if exists)
            └→ $SHOW_CONFIG_PATH/bluebolt_platform.sh (if exists)
                 └→ /software/bluebolt/vfxplatform/scripts/switch_scripts/setbbplatform ${BLUEBOLT_PLATFORM}
                      └→ REZ SETUP HAPPENS HERE (sets REZ_USED, rez packages, app paths)
```

## The `ws` Command

### Definition
```bash
ws → alias to `workspace`

workspace() {
    ws_file=$($WRAPPERS/write_workspace_file "$@")
    if [[ -f $ws_file ]]; then
        source $ws_file
        if command -v add_wrappers_to_path &> /dev/null; then
            add_wrappers_to_path
        fi
        [ -z "$KEEP_TEMP_WORKSPACE_FILES" ] && /bin/rm -r $(dirname $ws_file)
    else
        echo "[ERROR] no workspace file written: $ws_file"
    fi
    unset ws_file
}
```

### What `ws` Actually Does

1. **Generates a temp workspace file** via `$WRAPPERS/write_workspace_file`
2. **Sources that file** into the current shell (NOT a subshell)
3. **Adds wrappers to PATH** if `add_wrappers_to_path` function exists
4. **Cleans up** the temp file (unless `KEEP_TEMP_WORKSPACE_FILES=1`)

### Generated Workspace File Contents

Example for `ws jack_ryan GG_134 GG_134_1080`:

```bash
# Clear previous workspace state
unset SHOW EPISODE SEQUENCE SHOT BUILD_GROUP BUILD
unset SHOW_PATH EPISODE_PATH SEQUENCE_PATH SHOT_PATH BUILD_GROUP_PATH BUILD_PATH
unset WORKSPACE_PATH WORKSPACE_TYPE WORKSPACE

# Set new workspace environment
export SHOW=jack_ryan
export SHOW_PATH=/shows/jack_ryan
export WORKSPACE=GG_134_1080
export WORKSPACE_PATH=/shows/jack_ryan/shots/GG_134/GG_134_1080
export WORKSPACE_TYPE=shot
export SEQUENCE=GG_134
export SEQUENCE_PATH=/shows/jack_ryan/shots/GG_134
export SHOT=GG_134_1080
export SHOT_PATH=/shows/jack_ryan/shots/GG_134/GG_134_1080
export WORKSPACE_ORDER=/shows/bluebolt:/shows/jack_ryan:/shows/jack_ryan/shots/GG_134:/shows/jack_ryan/shots/GG_134/GG_134_1080

# Source hierarchical configs (may set shot-specific env vars)
source /shows/jack_ryan/config/env.sh
source /shows/jack_ryan/shots/GG_134/config/env.sh
source /shows/jack_ryan/shots/GG_134/GG_134_1080/config/env.sh

# Change to workspace directory
cd /shows/jack_ryan/shots/GG_134/GG_134_1080
export PWD=/shows/jack_ryan/shots/GG_134/GG_134_1080
```

### What `ws` Does NOT Do

- Does NOT call `rez env`
- Does NOT resolve Rez packages
- Does NOT wrap commands in a Rez environment
- Does NOT set `REZ_USED` (already set by platform init)

## Rez Setup: When and Where

### Timeline
```
1. Shell starts
2. /etc/bashrc sources bashrc.env
3. bashrc.env sources setbbplatform
4. setbbplatform initializes Rez environment  ← REZ_USED set here
5. User/launcher runs `ws show seq shot`      ← Workspace vars set here
6. User/launcher runs application             ← Runs with Rez + workspace env
```

### Key Insight
Rez is initialized at **shell startup**, not by the `ws` command. By the time `ws` runs,
the shell is already in a Rez environment with `REZ_USED` set.

## Code Assumption Corrections

### `REZ_ALREADY_AVAILABLE=True` (config.py:103)

**Previous name**: `WS_HANDLES_REZ` (renamed 2025-11-26)

**What it means**: Skip outer Rez wrapping because Rez is already available from shell init.

**Reality**: `ws` does NOT handle Rez. It sets workspace context variables.
Rez is already set up by shell initialization before `ws` runs.

**Why the code works**: The launcher checks `REZ_USED` env var to detect
an existing Rez environment and skips outer Rez wrapping. This is correct behavior.

**Configuration values**:
- `True` (default): Shell init provides Rez, skip outer wrapping
- `False`: Apply Rez wrapping (for environments that don't init Rez at startup)

### `bash -ilc` Requirement

**Why it's required**:
- `-i` (interactive): Loads `.bashrc` which defines `workspace` function
- `-l` (login): Ensures `/etc/bashrc` and full init chain runs
- `-c`: Execute the command

Without `-i`, the `ws` alias and `workspace` function won't exist.

### REZ_AUTO_DETECT Logic (environment_manager.py:95)

```python
if config.REZ_AUTO_DETECT and os.environ.get("REZ_USED") and not config.REZ_FORCE_WRAP:
    return False  # Skip Rez wrapping
```

**This is correct**: When `REZ_USED` is set (from shell init), skip outer Rez wrap.

## Environment Variables Reference

### Set by Shell Init (setbbplatform)
- `REZ_USED` - Indicates Rez environment is active
- `BLUEBOLT_PLATFORM` - Platform version (e.g., "BLUEBOLT_MASTER-4.0.34")
- App paths added to `PATH` (nuke, maya, 3de, etc.)

### Set by bashrc.env
- `COMPANY_CONFIG_PATH=/shows/bluebolt`
- `SHOW_ROOT_PATH=/shows/$project`
- `SHOW_PATH=/shows/$project`
- `SHOW_TOOLS_PATH`, `SHOW_CONFIG_PATH`
- `OCIO`, `OCIO_PATH`, `OCIO_ACTIVE_VIEWS`, `OCIO_ACTIVE_DISPLAYS`
- `ENABLE_LAUNCH=1`, `ENABLE_SGTK=1`

### Set by `ws` Command
- `SHOW` - Show name (e.g., "jack_ryan")
- `SHOW_PATH` - Show root path
- `SEQUENCE` - Sequence name
- `SEQUENCE_PATH` - Sequence path
- `SHOT` - Shot name
- `SHOT_PATH` - Shot path
- `WORKSPACE` - Current workspace name (usually same as shot)
- `WORKSPACE_PATH` - Full path to workspace
- `WORKSPACE_TYPE` - "shot" or "build"
- `WORKSPACE_ORDER` - Colon-separated config lookup order
- `PWD` - Changed to workspace path

## Debugging Tips

### See workspace file contents
```bash
DEBUG=1 KEEP_TEMP_WORKSPACE_FILES=1 ws <show> <seq> <shot>
# Check /disk1/tmp/ws-*/ws.sh
```

### Check if Rez is active
```bash
echo $REZ_USED
rez context  # Shows current Rez packages
```

### Check ws function definition
```bash
type ws        # Shows alias
type workspace # Shows function definition
```

### Check full environment after ws
```bash
ws <show> <seq> <shot>
env | grep -E '^(SHOW|SEQUENCE|SHOT|WORKSPACE|REZ_)'
```

## Launcher Command Flow

When launcher runs: `bash -ilc "ws jack_ryan GG_134 GG_134_1080 && nuke"`

```
1. bash -il starts
   → ~/.bashrc runs
   → /etc/bashrc runs
   → setbbplatform runs (Rez initialized, REZ_USED set)
   → workspace function defined

2. ws jack_ryan GG_134 GG_134_1080 runs
   → Generates /disk1/tmp/ws-XXXXX/ws.sh
   → Sources ws.sh (sets SHOW, SHOT, etc.)
   → Sources show/seq/shot env.sh files
   → CDs to workspace

3. && nuke runs
   → nuke binary found via PATH (set by Rez)
   → Inherits all env vars (Rez + workspace)
   → Opens in workspace context
```

## Files Referenced

| Path | Purpose |
|------|---------|
| `~/.bashrc` | User shell init |
| `/etc/bashrc` | System shell init |
| `/software/bluebolt/vfxplatform/startup/current/bashrc.env` | VFX platform init |
| `/software/bluebolt/vfxplatform/scripts/switch_scripts/setbbplatform` | Rez/platform setup |
| `/shows/bluebolt/config/env.sh` | Company-wide config |
| `/shows/<show>/config/env.sh` | Show-level config |
| `/shows/<show>/shots/<seq>/config/env.sh` | Sequence-level config |
| `/shows/<show>/shots/<seq>/<shot>/config/env.sh` | Shot-level config |
| `$WRAPPERS/write_workspace_file` | Generates workspace env file |
