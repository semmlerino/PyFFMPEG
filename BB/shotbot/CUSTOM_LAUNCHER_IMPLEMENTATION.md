# Custom Launcher Implementation Summary

This document summarizes the implementation of the custom launcher feature for ShotBot, which allows users to define and execute shell commands in new terminal windows.

## Implementation Overview

### Phase 1: Design & Architecture ✅
- **UI/UX Design**: Complete launcher management dialog with search, preview, and CRUD operations
- **Architecture Design**: Robust data models, persistence layer, and cross-platform terminal execution
- **Documentation**: Comprehensive API and user documentation created

### Phase 2: Core Implementation ✅
1. **Data Model & Configuration** (`launcher_model.py`, `launcher_config.py`)
   - `Launcher` and `LauncherParameter` dataclasses with validation
   - Cross-platform configuration storage with atomic writes and backups
   - JSON schema validation and migration support

2. **Terminal Execution** (`terminal_launcher.py`)
   - Multi-platform terminal detection (Linux, macOS, Windows)
   - Safe command substitution with security validation
   - Environment variable and working directory support
   - Qt signal integration for status updates

3. **Business Logic** (`launcher_manager.py`)
   - Complete CRUD operations with validation
   - Shot context variable substitution
   - Qt signals for UI updates
   - Thread-safe execution management

### Phase 3: UI Implementation ✅
1. **Launcher Dialog UI** (`launcher_dialog.py`)
   - Main dialog with list view and preview panel
   - Edit dialog for creating/modifying launchers
   - Real-time validation and search functionality
   - Full keyboard navigation support

2. **Main Window Integration** (updated `main_window.py`)
   - Tools menu with "Manage Custom Launchers..." (Ctrl+L)
   - Dynamic custom launcher submenu
   - Context-aware launcher execution
   - Signal connections for status updates

3. **Testing** (`test_launcher_dialog.py`, `test_launcher_integration.py`)
   - Comprehensive unit tests for UI components
   - Integration test script for manual testing
   - Mock-based testing for isolation

## Key Features Implemented

### 1. Launcher Management
- **Add**: Create new launchers with name, command, description, and category
- **Edit**: Modify existing launchers with validation
- **Delete**: Remove launchers with confirmation dialog
- **Search**: Real-time filtering by name or command

### 2. Terminal Configuration
- **Environment Types**: Support for bash, rez, and conda environments
- **Terminal Settings**: Option to keep terminal open after execution
- **Platform Support**: Automatic terminal detection on all platforms

### 3. Variable Substitution
Shot context variables available in commands:
- `{show}` - Show name
- `{sequence}` - Sequence name
- `{shot}` - Shot number
- `{full_name}` - Full shot name (e.g., seq001_0010)
- `{workspace_path}` - Shot workspace path

### 4. User Interface
- **Keyboard Shortcuts**:
  - `Ctrl+L` - Open launcher manager
  - `Ctrl+N` - Add new launcher
  - `F2` - Edit selected launcher
  - `Delete` - Delete selected launcher
  - `Enter` - Launch selected
  - `Ctrl+F` - Focus search
  - `Escape` - Close dialog

- **Visual Design**:
  - Consistent with ShotBot's cyan/dark theme
  - Clear visual feedback for validation
  - Drag-and-drop reordering support
  - Responsive layout with splitter

### 5. Security & Validation
- Command syntax validation
- Dangerous pattern detection (rm -rf, sudo, etc.)
- Path existence checking
- Name uniqueness enforcement

## Example Usage

### Creating a Launcher
```python
launcher_id = manager.create_launcher(
    name="Launch Nuke",
    command="nuke --nc {workspace_path}/nuke/{shot}_v001.nk",
    description="Open Nuke with shot file",
    category="Applications",
    environment=LauncherEnvironment(type="rez", packages=["nuke"]),
    persist_terminal=False
)
```

### Example Launcher Configurations

1. **ShotBot Debug Mode**
   ```json
   {
     "name": "ShotBot Debug Mode",
     "command": "rez env PySide6_Essentials pillow Jinja2 -- python3 '/path/to/shotbot.py' --debug --shot={full_name}",
     "category": "Debug",
     "environment": {"type": "rez", "packages": ["PySide6_Essentials", "pillow", "Jinja2"]},
     "persist_terminal": true
   }
   ```

2. **Plate Validation Script**
   ```json
   {
     "name": "Check Plate",
     "command": "python3 /tools/check_plate.py --shot {full_name} --workspace {workspace_path}",
     "category": "Scripts"
   }
   ```

## File Structure

```
shotbot/
├── launcher_model.py          # Data models and validation
├── launcher_config.py         # Configuration persistence
├── launcher_manager.py        # Business logic and Qt integration
├── terminal_launcher.py       # Terminal execution layer
├── launcher_dialog.py         # UI components
├── test_launcher_integration.py    # Manual test script
├── tests/unit/
│   └── test_launcher_dialog.py    # Unit tests
└── docs/
    └── CUSTOM_LAUNCHER_DOCUMENTATION.md  # User/developer docs
```

## Integration Points

1. **Main Window**:
   - Menu integration in Tools menu
   - Dynamic launcher submenu
   - Status bar updates
   - Shot context awareness

2. **Configuration**:
   - Stored in `~/.shotbot/custom_launchers.json` (cross-platform)
   - Automatic backups maintained
   - Settings persist across sessions

3. **Signals & Events**:
   - `launchers_changed` - Updates UI menus
   - `execution_started/finished` - Status feedback
   - `validation_error` - User notifications

## Testing

Run the integration test:
```bash
python test_launcher_integration.py
```

Run unit tests:
```bash
python run_tests.py tests/unit/test_launcher_dialog.py
```

## Future Enhancements

1. **Parameter UI**: Dynamic forms for launcher parameters
2. **Import/Export**: Share launcher configurations
3. **Icons**: Custom icons for launchers
4. **Groups**: Better organization with collapsible groups
5. **History**: Track launcher execution history
6. **Templates**: Pre-defined launcher templates

## Conclusion

The custom launcher feature is fully implemented and integrated into ShotBot, providing users with a flexible way to define and execute custom commands within their VFX pipeline context. The implementation follows Qt best practices, maintains the application's visual consistency, and provides comprehensive error handling and validation.