# Mocking Refactoring Examples
**Based on pytest and pytest-qt best practices from context7**

## Example 1: Path Operation Mocking → tmp_path

### BEFORE (Anti-pattern)
```python
# tests/unit/test_nuke_media_detector.py:31-56

@patch("pathlib.Path.exists")
@patch("pathlib.Path.iterdir")
def test_detect_frame_range_with_hash_pattern(
    self, mock_iterdir: MagicMock, mock_exists: MagicMock
) -> None:
    """Test frame range detection with #### pattern."""
    # Setup mock directory that exists
    mock_exists.return_value = True

    # Create mock files with frame numbers
    mock_files = []
    for filename in [
        "shot_1001.exr",
        "shot_1050.exr",
        "shot_1100.exr",
        "other_file.txt",
    ]:
        mock_file = MagicMock()
        mock_file.name = filename
        mock_files.append(mock_file)
    mock_iterdir.return_value = mock_files

    first, last = NukeMediaDetector.detect_frame_range("/path/to/shot_####.exr")

    assert first == 1001
    assert last == 1100
```

**Problems**:
- ❌ Mocking Path operations that are cheap and deterministic
- ❌ Creating MagicMock objects for files
- ❌ Doesn't test real filesystem edge cases (permissions, encoding, symlinks)
- ❌ Brittle: breaks if implementation switches from Path to os.path
- ❌ More code to maintain (11 lines of mock setup)

### AFTER (Best practice per pytest docs)
```python
def test_detect_frame_range_with_hash_pattern(tmp_path: Path) -> None:
    """Test frame range detection with #### pattern."""
    # Create real files in temporary directory
    (tmp_path / "shot_1001.exr").touch()
    (tmp_path / "shot_1050.exr").touch()
    (tmp_path / "shot_1100.exr").touch()
    (tmp_path / "other_file.txt").touch()

    pattern = tmp_path / "shot_####.exr"
    first, last = NukeMediaDetector.detect_frame_range(str(pattern))

    assert first == 1001
    assert last == 1100
```

**Benefits**:
- ✅ Tests real filesystem behavior
- ✅ Catches edge cases (permissions, encoding)
- ✅ Less code (8 lines vs 19)
- ✅ No mock setup/teardown
- ✅ tmp_path auto-cleanup
- ✅ Works with any filesystem implementation

**Migration effort**: ~2 minutes per test

---

## Example 2: File Reading with Mocked open() → tmp_path

### BEFORE (Anti-pattern)
```python
# tests/unit/test_nuke_undistortion_parser.py:32-76

@patch("pathlib.Path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_parse_copy_paste_format_detection(
    self, mock_file: MagicMock, mock_exists: MagicMock
) -> None:
    """Test detection of copy/paste format."""
    mock_exists.return_value = True

    # Mock file content
    copy_paste_content = """set cut_paste_input [stack 0]
version 14.0 v5
Constant {
 inputs 0
 channels rgb
 color {0.5 0.5 0.5 1}
 name Constant1
 xpos 100
 ypos 200
}
push $cut_paste_input
"""
    mock_file.return_value.read.return_value = copy_paste_content

    result = NukeUndistortionParser.parse_undistortion_file("/test/file.nk")

    # Verify copy/paste format handling
    assert "set cut_paste_input" not in result
    assert "push $cut_paste_input" not in result
    assert "Constant {" in result
    assert "name Constant1" in result
```

**Problems**:
- ❌ Mocking builtins.open is complex and fragile
- ❌ Doesn't test actual file reading (encoding, EOF, line endings)
- ❌ Mock setup is verbose and error-prone
- ❌ Doesn't test Path.exists interaction with actual file

### AFTER (Best practice per pytest docs)
```python
def test_parse_copy_paste_format_detection(tmp_path: Path) -> None:
    """Test detection of copy/paste format."""
    # Create real test file
    test_file = tmp_path / "test.nk"
    test_file.write_text("""set cut_paste_input [stack 0]
version 14.0 v5
Constant {
 inputs 0
 channels rgb
 color {0.5 0.5 0.5 1}
 name Constant1
 xpos 100
 ypos 200
}
push $cut_paste_input
""")

    result = NukeUndistortionParser.parse_undistortion_file(str(test_file))

    # Verify copy/paste format handling
    assert "set cut_paste_input" not in result
    assert "push $cut_paste_input" not in result
    assert "Constant {" in result
    assert "name Constant1" in result
```

**Benefits**:
- ✅ Tests real file I/O (catches encoding bugs)
- ✅ Tests actual Path.exists behavior
- ✅ Simpler code (no mock_open complexity)
- ✅ Tests file reading edge cases (empty files, missing files)
- ✅ tmp_path handles cleanup automatically

---

## Example 3: When Mocking IS Appropriate (System Boundary)

### CORRECT USAGE: Subprocess Mocking
```python
# tests/unit/test_process_pool_manager.py

def test_workspace_command(test_subprocess):
    """Test workspace command execution."""
    test_subprocess.set_response(b"shot001\nshot002\nshot003")

    result = pool.execute_workspace_command("ws -sg")

    assert "shot001" in result
    assert "shot002" in result
    assert test_subprocess.executed_commands[0] == ["bash", "-i", "-c", "ws -sg"]
```

**Why this is correct**:
- ✅ Mocking external process (system boundary)
- ✅ Can't use real `ws` command in tests (VFX-specific)
- ✅ Using test double, not Mock()
- ✅ Testing behavior (command execution), not implementation

**Per pytest-mock docs**: "Mock at system boundaries, not internal logic"

---

## Example 4: Qt Widget Testing (Already Correct)

### YOUR CURRENT PATTERN (Excellent)
```python
# tests/unit/test_launcher_panel.py

def test_launcher_panel_creation(qtbot):
    """Test launcher panel creates and displays correctly."""
    panel = LauncherPanel()
    qtbot.addWidget(panel)  # Real widget, managed lifecycle

    # Test real widget behavior
    assert panel.app_combo.count() == len(APPS)
    assert panel.launch_button.isEnabled()

    # Trigger real signal
    with qtbot.waitSignal(panel.app_launched):
        panel.launch_button.click()
```

**Why this is correct**:
- ✅ Using real Qt widgets (not mocking QWidget)
- ✅ Using qtbot for lifecycle management
- ✅ Testing real signal emission
- ✅ No Mock() objects for UI components

**Per pytest-qt docs**: "Use real widgets with qtbot, mock only dialog responses"

---

## Example 5: Dialog Mocking (Correct Pattern)

### CORRECT: Mocking Dialog Results
```python
def test_confirmation_dialog(qtbot, monkeypatch):
    """Test code that shows confirmation dialog."""
    # Mock dialog result, not entire dialog widget
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args: QMessageBox.StandardButton.Yes
    )

    widget = FeatureWidget()
    qtbot.addWidget(widget)

    # User clicks delete (would show dialog in production)
    widget.delete_button.click()

    # Verify delete happened (dialog returned Yes)
    assert widget.item_deleted
```

**Why this is correct**:
- ✅ Mocking dialog response (user interaction)
- ✅ Not mocking entire QMessageBox widget
- ✅ Using monkeypatch (pytest built-in)
- ✅ Testing behavior: "if user confirms, delete happens"

**Per pytest-qt docs**: "Mock dialog methods, not widget trees"

---

## Migration Checklist

### For Path Operation Tests
- [ ] Identify tests using `@patch("pathlib.Path.*")`
- [ ] Add `tmp_path` parameter to test function
- [ ] Replace mock setup with real file creation
- [ ] Update assertions to use tmp_path paths
- [ ] Remove `@patch` decorators
- [ ] Run test to verify it still passes

### For File I/O Tests
- [ ] Identify tests using `@patch("builtins.open")`
- [ ] Add `tmp_path` parameter to test function
- [ ] Create real files with `tmp_path / "filename"`
- [ ] Use `.write_text()` or `.write_bytes()` for content
- [ ] Remove mock_open setup
- [ ] Run test to verify file reading works

### For Mock() Audit
- [ ] Find `Mock()` or `MagicMock()` usage
- [ ] Ask: "Is this a system boundary?"
  - Yes → Keep mock, maybe convert to test double
  - No → Consider real object or tmp_path
- [ ] Ask: "Could this be a test double?"
  - Yes → Create or use existing test double
  - No → Use real object
- [ ] Refactor and test

---

## pytest Best Practices Summary (from context7)

### DO Mock:
1. ✅ **External systems**: Databases, APIs, network calls
2. ✅ **Expensive operations**: Heavy computation, large file I/O
3. ✅ **Non-deterministic**: Time, random, external state
4. ✅ **System boundaries**: subprocess, OS operations

### DON'T Mock:
1. ❌ **Your own code**: Test real behavior
2. ❌ **Simple logic**: Pure functions, data transformations
3. ❌ **Filesystem**: Use `tmp_path` fixture
4. ❌ **Qt widgets**: Use real widgets with `qtbot`

### Prefer Test Doubles Over Mock():
```python
# BAD: Mock with magic
mock_subprocess = Mock()
mock_subprocess.run.return_value = Mock(returncode=0, stdout="output")

# GOOD: Test double with behavior
test_subprocess = TestSubprocess()
test_subprocess.set_response("output")
result = test_subprocess.run(["command"])
assert result.returncode == 0
```

---

## Validation

After refactoring, run:
```bash
# Should be 0 after Path mock removal
grep -r "@patch.*pathlib.Path" tests/unit/*.py | wc -l

# Should increase from 5 to 30+
grep -r "def test.*tmp_path" tests/unit/*.py | wc -l

# Should stay high (test doubles are good)
grep -r "TestSubprocess\|TestCompletedProcess" tests/ | wc -l
```

Expected results post-refactor:
- Path mocking: 0 instances (was 17)
- tmp_path usage: 30+ instances (was 5)
- Test doubles: 100+ instances (unchanged, good)
