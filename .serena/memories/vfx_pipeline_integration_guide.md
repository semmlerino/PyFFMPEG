# VFX Pipeline Integration Guide

**Purpose:** This guide documents VFX pipeline requirements for Shotbot, ensuring proper Rez environment setup, workspace integration, and VFX tool launching.

**Audience:** Any agent working on launcher system, VFX tool integration, or environment management.

---

## 🎯 Critical Requirements Overview

### **MANDATORY for ALL VFX Application Launches:**
1. ✅ **Rez environment wrapper** (if `Config.USE_REZ_ENVIRONMENT = True`)
2. ✅ **Workspace context** (execute in workspace directory via `ws` command)
3. ✅ **Pipeline environment variables** (SHOT, SHOT_WORKSPACE, SHOW minimum)
4. ✅ **Tool-specific paths** (NUKE_PATH, MAYA_MODULE_PATH, etc.)

### **Failure Mode Without These:**
- VFX applications can't find pipeline plugins
- Python modules unavailable to tool scripts
- Workspace-relative paths break
- Studio tooling unavailable (render queue, asset browser, etc.)

---

## 🔧 Rez Environment Management

### What is Rez?

Rez is a cross-platform package manager used in VFX studios to manage software dependencies and environments. It ensures consistent tool versions and library configurations across the pipeline.

**Documentation:** https://github.com/AcademySoftwareFoundation/rez

### Configuration

**File:** `config.py`

```python
class Config:
    # Rez Integration
    USE_REZ_ENVIRONMENT = True  # Line 93 - ENABLED BY DEFAULT
    
    # Package definitions per application
    REZ_PACKAGES = {
        "nuke": ["nuke-13.2", "studio_nuke_plugins", "pipeline_core"],
        "maya": ["maya-2024", "studio_maya_plugins", "pipeline_core"],
        "3de": ["3de-7.0", "pipeline_core"],
    }
```

### Correct Launch Pattern (Legacy System)

**File:** `command_launcher.py` lines 520-569

```python
def launch_app(self, app_name: str, context: LaunchContext | None = None) -> bool:
    """Legacy launcher - CORRECT Rez integration."""
    
    # Get base command from config
    base_command = Config.APPS[app_name]
    
    # Wrap with Rez if enabled
    if Config.USE_REZ_ENVIRONMENT:
        rez_packages = Config.REZ_PACKAGES.get(app_name, [])
        if rez_packages:
            # Build Rez wrapper: rez-env <packages> -- <command>
            command = f"rez-env {' '.join(rez_packages)} -- {base_command}"
        else:
            command = base_command
    else:
        command = base_command
    
    # Get workspace context
    workspace_path = self.execute_ws_command("ws -sg")
    
    # Execute in workspace directory
    full_command = f"cd {workspace_path} && {command}"
    
    return self._execute_in_terminal(full_command, env)
```

### Incorrect Pattern (SimplifiedLauncher - BROKEN)

**File:** `simplified_launcher.py` lines 138-165

```python
def launch_vfx_app(self, app_name: str, ...) -> bool:
    """SimplifiedLauncher - BROKEN Rez integration."""
    
    # ❌ WRONG: Gets base command directly, no Rez wrapper
    base_command = Config.APPS.get(app_name)
    
    # ❌ WRONG: Only injects 3 env vars, no Rez environment
    env = os.environ.copy()
    env["SHOT"] = shot.name
    env["SHOT_WORKSPACE"] = workspace_path
    env["SHOW"] = shot.show
    
    # ❌ WRONG: Executes with minimal environment
    return self._execute_in_terminal(base_command, env)
```

**Why This Fails:**
1. No `rez-env` wrapper → tool uses system PATH, not studio packages
2. Studio plugins not in NUKE_PATH/MAYA_MODULE_PATH
3. Python modules from Rez packages unavailable
4. Version conflicts with system-installed tools

### Required Fix for SimplifiedLauncher

```python
def launch_vfx_app(self, app_name: str, ...) -> bool:
    """Corrected SimplifiedLauncher with Rez integration."""
    
    # Get base command
    base_command = Config.APPS.get(app_name)
    if not base_command:
        self.logger.error(f"Unknown app: {app_name}")
        return False
    
    # Build command with Rez wrapper if enabled
    if Config.USE_REZ_ENVIRONMENT:
        rez_packages = Config.REZ_PACKAGES.get(app_name, [])
        if rez_packages:
            # Wrap command with Rez environment
            command = f"rez-env {' '.join(rez_packages)} -- {base_command}"
        else:
            self.logger.warning(f"No Rez packages defined for {app_name}")
            command = base_command
    else:
        command = base_command
    
    # Get workspace path
    workspace_result = self.execute_ws_command("ws -sg", cache=True)
    if not workspace_result:
        self.logger.error("Failed to get workspace path")
        return False
    
    workspace_path = workspace_result.strip()
    
    # Build environment with pipeline variables
    env = os.environ.copy()
    env["SHOT"] = shot.name
    env["SHOT_WORKSPACE"] = workspace_path
    env["SHOW"] = shot.show
    
    # Execute in workspace context
    full_command = f"cd {workspace_path} && {command}"
    
    return self._execute_in_terminal(full_command, env)
```

---

## 📁 Workspace Integration

### What is the `ws` Command?

`ws` is a studio workspace manager that provides:
- Show/shot directory structure
- Workspace paths for current context
- Standardized directory layout

### Common `ws` Commands

```bash
ws -sg              # Get current shot workspace (most common)
ws -show SHOW       # Get show root directory
ws -seq SHOW SEQ    # Get sequence directory
ws -shot SHOW SEQ SHOT  # Get shot directory
```

### Integration Pattern

**Always execute VFX tools in workspace directory:**

```python
# 1. Get workspace path
workspace_path = self.execute_ws_command("ws -sg", cache=True, timeout=30)

# 2. Change to workspace before launching tool
full_command = f"cd {workspace_path} && {command}"

# 3. Execute
self._execute_in_terminal(full_command, env)
```

### Why Workspace Context Matters

**Workspace-relative paths:**
```python
# Nuke scripts reference relative paths:
Read {
    file "../plates/shot_0010_v001.%04d.exr"  # Relative to workspace
}

# Maya scenes reference relative textures:
file -r -type "mayaAscii" "../assets/prop_table.ma";

# Without workspace context, these paths break!
```

**Workspace-specific config:**
```bash
# Workspace may contain .nuke/, .maya/, tool config
{workspace}/.nuke/init.py
{workspace}/.maya/prefs/
{workspace}/.3de/startup.py

# Tools look for these in current directory
```

---

## 🌍 Environment Variables

### Required Pipeline Variables

**Minimum set (always required):**

```python
env = {
    "SHOT": "shot_0010",           # Shot name
    "SHOT_WORKSPACE": "/path/to/workspace",  # Workspace directory
    "SHOW": "PROJECT_NAME",        # Show/project name
}
```

### Tool-Specific Variables

#### Nuke
```python
env["NUKE_PATH"] = ":".join([
    f"{workspace}/nuke",           # Workspace Nuke scripts
    "/studio/pipeline/nuke",       # Studio plugins
    # Rez will add package paths automatically
])

env["NUKE_TEMP_DIR"] = f"{workspace}/.nuke/tmp"
```

#### Maya
```python
env["MAYA_MODULE_PATH"] = ":".join([
    f"{workspace}/maya/modules",
    "/studio/pipeline/maya/modules",
])

env["MAYA_SCRIPT_PATH"] = ":".join([
    f"{workspace}/maya/scripts",
    "/studio/pipeline/maya/scripts",
])

env["PYTHONPATH"] = ":".join([
    f"{workspace}/maya/python",
    "/studio/pipeline/python",
    # Existing PYTHONPATH
    env.get("PYTHONPATH", ""),
])
```

#### 3DEqualizer
```python
env["TDE4_ROOT"] = "/opt/3de/7.0"
env["TDE4_USER_SCRIPTS"] = f"{workspace}/3de/scripts"
env["TDE4_PLUGIN_PATH"] = "/studio/pipeline/3de/plugins"
```

### Environment Variable Best Practices

**✅ DO:**
- Copy existing environment: `env = os.environ.copy()`
- Add to paths (don't replace): `env["PATH"] = new_path + ":" + env["PATH"]`
- Use colon separators for paths: `":".join([path1, path2])`
- Let Rez handle most environment setup automatically

**❌ DON'T:**
- Replace entire environment: `env = {"SHOT": ...}`
- Overwrite system PATH completely
- Hardcode absolute paths (use workspace-relative)
- Skip Rez wrapper and try to set everything manually

---

## 🎬 VFX Tool-Specific Integration

### Nuke Integration

**Key Files:**
- `nuke_launch_handler.py` - Nuke command preparation
- `nuke_script_generator.py` - Nuke script generation
- `nuke_script_templates.py` - Script templates
- `nuke_undistortion_parser.py` - 3DE lens undistortion

**Correct Launch Flow:**

```python
# 1. Prepare Nuke command with options
command = nuke_launch_handler.prepare_nuke_command(
    shot=shot,
    workspace_path=workspace_path,
    selected_plate="/path/to/plate.exr",  # IMPORTANT: Must pass plate!
    include_raw_plate=True,
    create_new_file=False,  # Key name: "create_new_file" (not "create_new")
)

# 2. Wrap with Rez
if Config.USE_REZ_ENVIRONMENT:
    rez_packages = Config.REZ_PACKAGES.get("nuke", [])
    command = f"rez-env {' '.join(rez_packages)} -- {command}"

# 3. Execute in workspace
full_command = f"cd {workspace_path} && {command}"
```

**Critical Bug in SimplifiedLauncher:**

```python
# ❌ BROKEN: SimplifiedLauncher doesn't accept selected_plate parameter
def launch_app(self, app_name: str, 
               include_raw_plate: bool = True,  # Only booleans!
               ...):
    # selected_plate is LOST - can't pass to NukeLaunchHandler

# NukeLaunchHandler receives selected_plate=None
# Hits guard: "Error: No plate selected"
# Returns base nuke command without workspace script
```

**Required Fix:**

```python
def launch_app(
    self,
    app_name: str,
    selected_plate: str | None = None,  # ← ADD THIS PARAMETER
    include_raw_plate: bool = True,
    open_latest_threede: bool = False,
    create_new_file: bool = False,  # ← Consistent naming
) -> bool:
    """Launch application with full parameter support."""
    
    if app_name == "nuke":
        # Pass ALL parameters to NukeLaunchHandler
        command = self.nuke_handler.prepare_nuke_command(
            shot=shot,
            workspace_path=workspace_path,
            selected_plate=selected_plate,  # ← Now available!
            include_raw_plate=include_raw_plate,
            create_new_file=create_new_file,  # ← Correct key name
        )
```

### Maya Integration

**Key Files:**
- `maya_latest_finder.py` - Find latest Maya files
- `maya_latest_finder_refactored.py` - Refactored version

**Launch Pattern:**

```python
# 1. Find latest Maya file in workspace
maya_finder = MayaLatestFinder(workspace_path)
latest_file = maya_finder.find_latest_scene("animation")  # or "rigging", "lighting"

# 2. Build Maya command
if latest_file:
    command = f"maya -file {latest_file}"
else:
    command = "maya"

# 3. Wrap with Rez and execute
if Config.USE_REZ_ENVIRONMENT:
    rez_packages = Config.REZ_PACKAGES.get("maya", [])
    command = f"rez-env {' '.join(rez_packages)} -- {command}"

full_command = f"cd {workspace_path} && {command}"
```

### 3DEqualizer Integration

**Key Files:**
- `threede_controller.py` - 3DE launch controller
- `threede_scene_finder.py` - Find .3de files
- `threede_scene_model.py` - Scene data model
- `threede_scanner_integration.py` - Filesystem scanning

**Launch Pattern:**

```python
# 1. Find latest .3de scene
threede_finder = ThreeDESceneFinder()
latest_scene = threede_finder.find_latest_scene(shot)

# 2. Build 3DE command
if latest_scene and open_latest_scene:
    command = f"3de {latest_scene.path}"
else:
    command = "3de"

# 3. Wrap with Rez and execute
if Config.USE_REZ_ENVIRONMENT:
    rez_packages = Config.REZ_PACKAGES.get("3de", [])
    command = f"rez-env {' '.join(rez_packages)} -- {command}"

full_command = f"cd {workspace_path} && {command}"
```

---

## 🧪 Testing VFX Pipeline Integration

### Environment Validation Test

```python
def test_rez_environment_setup():
    """Verify Rez environment is properly configured."""
    launcher = SimplifiedLauncher()
    shot = Shot("TEST", "seq01", "0010", "/shows/TEST/shots/seq01/seq01_0010")
    launcher.set_current_shot(shot)
    
    with patch('subprocess.Popen') as mock_popen:
        result = launcher.launch_vfx_app("nuke")
        
        # Verify Rez wrapper present
        call_args = mock_popen.call_args[0][0]
        if Config.USE_REZ_ENVIRONMENT:
            assert "rez-env" in call_args, "Missing Rez wrapper"
            
            # Verify packages listed
            rez_packages = Config.REZ_PACKAGES.get("nuke", [])
            for package in rez_packages:
                assert package in call_args, f"Missing Rez package: {package}"
        
        # Verify workspace context
        assert "cd" in call_args and "ws" in call_args, "Missing workspace context"
        
        assert result is True
```

### Workspace Integration Test

```python
def test_workspace_integration():
    """Verify commands execute in workspace directory."""
    launcher = SimplifiedLauncher()
    shot = Shot("TEST", "seq01", "0010", "/shows/TEST/shots/seq01/seq01_0010")
    launcher.set_current_shot(shot)
    
    with patch.object(launcher, 'execute_ws_command') as mock_ws:
        mock_ws.return_value = "/shows/TEST/shots/seq01/seq01_0010/workspace"
        
        with patch('subprocess.Popen') as mock_popen:
            launcher.launch_vfx_app("maya")
            
            # Verify workspace command executed
            mock_ws.assert_called_with("ws -sg", cache=True)
            
            # Verify cd to workspace in command
            call_args = mock_popen.call_args[0][0]
            assert "cd /shows/TEST/shots/seq01/seq01_0010/workspace" in call_args
```

### Environment Variable Test

```python
def test_pipeline_environment_variables():
    """Verify required environment variables are set."""
    launcher = SimplifiedLauncher()
    shot = Shot("TEST", "seq01", "0010", "/shows/TEST/shots/seq01/seq01_0010")
    launcher.set_current_shot(shot)
    
    with patch('subprocess.Popen') as mock_popen:
        launcher.launch_vfx_app("nuke")
        
        # Extract environment from Popen call
        env = mock_popen.call_args[1]['env']
        
        # Verify required variables
        assert env.get("SHOT") == "seq01_0010"
        assert env.get("SHOW") == "TEST"
        assert "SHOT_WORKSPACE" in env
        
        # Verify original environment preserved
        assert "PATH" in env
        assert "HOME" in env
```

### Plate Forwarding Test

```python
def test_nuke_selected_plate_forwarded():
    """Verify selected plate reaches NukeLaunchHandler."""
    launcher = SimplifiedLauncher()
    shot = Shot("TEST", "seq01", "0010", "/shows/TEST/shots/seq01/seq01_0010")
    launcher.set_current_shot(shot)
    
    plate_path = "/shows/TEST/shots/seq01/seq01_0010/plates/plate_v001.%04d.exr"
    
    with patch.object(NukeLaunchHandler, 'prepare_nuke_command') as mock_prepare:
        mock_prepare.return_value = "nuke -t script.nk"
        
        # Launch with selected plate
        launcher.launch_app("nuke", selected_plate=plate_path)
        
        # Verify plate was passed to handler
        call_kwargs = mock_prepare.call_args[1]
        assert call_kwargs.get('selected_plate') == plate_path, \
            "selected_plate parameter not forwarded to NukeLaunchHandler"
```

### Create New File Test

```python
def test_create_new_file_option_respected():
    """Verify create_new_file toggle is honored."""
    launcher = SimplifiedLauncher()
    shot = Shot("TEST", "seq01", "0010", "/shows/TEST/shots/seq01/seq01_0010")
    launcher.set_current_shot(shot)
    
    with patch.object(NukeLaunchHandler, 'prepare_nuke_command') as mock_prepare:
        mock_prepare.return_value = "nuke -t script.nk"
        
        # Launch with create_new_file=True
        launcher.launch_app("nuke", create_new_file=True)
        
        # Verify parameter was passed correctly
        call_kwargs = mock_prepare.call_args[1]
        assert call_kwargs.get('create_new_file') is True, \
            "create_new_file parameter not forwarded correctly"
```

---

## 🚨 Common Pitfalls and Anti-Patterns

### ❌ Anti-Pattern 1: No Rez Wrapper

```python
# WRONG - Launches tool with system environment
command = "nuke"
subprocess.Popen(["/bin/bash", "-c", command])

# Result: Tool can't find studio plugins, wrong Python version
```

### ❌ Anti-Pattern 2: No Workspace Context

```python
# WRONG - Launches in wrong directory
command = "rez-env nuke-13.2 -- nuke"
subprocess.Popen(["/bin/bash", "-c", command])

# Result: Relative paths break, tool config not found
```

### ❌ Anti-Pattern 3: Replacing Environment

```python
# WRONG - Loses system environment
env = {
    "SHOT": shot.name,
    "SHOW": shot.show,
}
subprocess.Popen(["/bin/bash", "-c", command], env=env)

# Result: Missing PATH, HOME, USER, etc. - tool may not start
```

### ❌ Anti-Pattern 4: Parameter Name Mismatches

```python
# WRONG - Key name doesn't match what's consumed
options["create_new"] = True  # Controller stores this

# Later...
create_new_file = options.get("create_new_file")  # Looks for different key!

# Result: Option silently ignored, user frustrated
```

### ❌ Anti-Pattern 5: Hardcoded Paths

```python
# WRONG - Not portable across shots/shows
command = "nuke /shows/SHOW_A/shots/seq01/seq01_0010/nuke/comp_v001.nk"

# Result: Breaks when shot changes, not reusable
```

---

## ✅ Correct Patterns Summary

### Complete Launch Function Template

```python
def launch_vfx_app(
    self,
    app_name: str,
    shot: Shot,
    selected_plate: str | None = None,
    include_raw_plate: bool = True,
    create_new_file: bool = False,
    open_latest_file: bool = False,
) -> bool:
    """
    Launch VFX application with proper Rez/workspace integration.
    
    This is the CORRECT pattern for VFX tool launching.
    """
    # 1. Validate inputs
    if not shot:
        self.logger.error("No shot context set")
        return False
    
    base_command = Config.APPS.get(app_name)
    if not base_command:
        self.logger.error(f"Unknown app: {app_name}")
        return False
    
    # 2. Get workspace path
    workspace_result = self.execute_ws_command("ws -sg", cache=True, timeout=30)
    if not workspace_result:
        self.logger.error("Failed to get workspace path")
        return False
    workspace_path = workspace_result.strip()
    
    # 3. Prepare tool-specific command
    if app_name == "nuke":
        command = self.nuke_handler.prepare_nuke_command(
            shot=shot,
            workspace_path=workspace_path,
            selected_plate=selected_plate,
            include_raw_plate=include_raw_plate,
            create_new_file=create_new_file,
        )
    elif app_name == "maya":
        command = self._prepare_maya_command(workspace_path, open_latest_file)
    elif app_name == "3de":
        command = self._prepare_3de_command(shot, open_latest_file)
    else:
        command = base_command
    
    # 4. Wrap with Rez environment if enabled
    if Config.USE_REZ_ENVIRONMENT:
        rez_packages = Config.REZ_PACKAGES.get(app_name, [])
        if rez_packages:
            command = f"rez-env {' '.join(rez_packages)} -- {command}"
        else:
            self.logger.warning(f"No Rez packages defined for {app_name}")
    
    # 5. Build environment with pipeline variables
    env = os.environ.copy()  # Preserve existing environment
    env.update({
        "SHOT": shot.name,
        "SHOT_WORKSPACE": workspace_path,
        "SHOW": shot.show,
    })
    
    # 6. Execute in workspace context
    full_command = f"cd {workspace_path} && {command}"
    
    self.logger.info(f"Launching {app_name} with command: {full_command[:100]}...")
    return self._execute_in_terminal(full_command, env)
```

---

## 📚 References

### Key Files to Review

**Launcher System:**
- `launcher/simplified_launcher.py` - Current (broken) launcher
- `launcher/command_launcher.py` - Legacy (correct) launcher
- `controllers/launcher_controller.py` - Launch orchestration

**VFX Integration:**
- `nuke_launch_handler.py` - Nuke command preparation
- `threede_controller.py` - 3DE launch controller
- `maya_latest_finder_refactored.py` - Maya file discovery

**Configuration:**
- `config.py` - Rez packages, app commands, settings

**Testing:**
- `tests/unit/test_simplified_launcher_nuke.py` - Nuke launch tests
- `tests/integration/test_threede_scanner_integration.py` - 3DE tests

### External Documentation

- **Rez:** https://github.com/AcademySoftwareFoundation/rez
- **VFX Reference Platform:** https://vfxplatform.com/
- **Nuke Python API:** https://learn.foundry.com/nuke/developers/
- **Maya Python API:** https://help.autodesk.com/view/MAYAUL/2024/ENU/

---

## 🎯 Checklist for VFX Launch Implementation

When implementing or fixing VFX application launchers, verify:

### Environment Setup
- [ ] Rez wrapper applied if `Config.USE_REZ_ENVIRONMENT = True`
- [ ] Correct Rez packages from `Config.REZ_PACKAGES[app_name]`
- [ ] Workspace path retrieved via `ws -sg` command
- [ ] Command executes in workspace directory (`cd {workspace}`)
- [ ] Environment variables include SHOT, SHOT_WORKSPACE, SHOW minimum
- [ ] Original environment preserved (`os.environ.copy()`)

### Parameter Handling
- [ ] `selected_plate` parameter accepted and forwarded (Nuke)
- [ ] `create_new_file` key name consistent (not `create_new`)
- [ ] All boolean options properly passed through
- [ ] Tool-specific handlers receive all required parameters

### Testing
- [ ] Unit test verifies Rez wrapper in command
- [ ] Unit test verifies workspace context (`cd` command)
- [ ] Unit test verifies environment variables set
- [ ] Integration test launches actual tool (if feasible)
- [ ] Parameter forwarding tests for all options

### Error Handling
- [ ] Graceful failure if workspace path unavailable
- [ ] Clear error message if Rez packages undefined
- [ ] Logging of full command (for debugging)
- [ ] Return False on any setup failure

---

## 📝 Version History

- **v1.0** (2025-11-13): Initial creation
  - Documented Rez integration requirements
  - Workspace integration patterns
  - Tool-specific launch patterns
  - Common pitfalls and correct patterns
  - Testing guidelines
  - Based on findings from deep-debugger and threading-debugger analysis

---

**END OF VFX PIPELINE INTEGRATION GUIDE**