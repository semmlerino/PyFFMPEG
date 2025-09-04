# Mock VFX Environment Setup

This guide explains how to capture the VFX filesystem structure from a production workstation and recreate it locally for development/testing.

## Why This Approach?

Instead of guessing the VFX directory structure or suppressing errors, we:
1. Capture the real structure from the VFX environment
2. Recreate it locally with placeholder files
3. Get realistic testing without needing VFX infrastructure

## Step 1: Capture Structure on VFX Workstation

Run this on your VFX workstation where `ws -sg` works:

```bash
# Simplest usage - auto-generates timestamped filename
python capture_vfx_structure.py
# Creates: vfx_structure_hostname_20240315_143022.json

# Capture specific shows only
python capture_vfx_structure.py --shows gator jack_ryan

# Custom output file
python capture_vfx_structure.py --output my_structure.json
```

This creates a JSON file with:
- Directory structure
- File names and sizes
- Shot paths from `ws -sg`
- No actual file contents (safe to share)
- Timestamped filename for easy tracking

## Step 2: Transfer the JSON File

Copy `vfx_structure.json` to your development machine.

```bash
# Example using scp
scp workstation:/path/to/vfx_structure.json .
```

## Step 3: Recreate Structure Locally

On your development machine:

```bash
# Install dependencies if needed
pip install pillow

# Recreate the structure
python recreate_vfx_structure.py vfx_structure.json

# Or specify a custom location
python recreate_vfx_structure.py vfx_structure.json --root ~/mock_vfx

# Clean and recreate
python recreate_vfx_structure.py vfx_structure.json --clean
```

This creates:
- Complete directory structure matching production
- Placeholder thumbnail images (with gradients and text)
- Mock 3DE scene files
- Sample EXR frame markers
- A `MOCK_VFX_ENVIRONMENT.txt` marker file

## Step 4: Run ShotBot with Mock Environment

The mock launcher automatically detects the recreated filesystem:

```bash
# Run with mock mode - will auto-detect filesystem
./venv/bin/python shotbot_mock.py

# Or use the shell script
./run_shotbot_mock.sh
```

The app will:
- Use the recreated filesystem (no missing path warnings!)
- Load demo shots from `demo_shots.json`
- Show "MOCK MODE" indicator in the UI
- Display placeholder thumbnails

## Directory Structure Created

```
/tmp/mock_vfx/
├── MOCK_VFX_ENVIRONMENT.txt   # Marker file
└── shows/
    ├── gator/
    │   └── shots/
    │       └── 012_DC/
    │           └── 012_DC_1000/
    │               ├── publish/
    │               │   └── editorial/
    │               │       └── cutref/
    │               │           └── v001/
    │               │               └── jpg/
    │               │                   └── 1920x1080/
    │               │                       └── frame.1001.jpg  # Placeholder thumbnail
    │               └── user/
    │                   └── ryan-p/
    │                       └── mm/
    │                           └── 3de/
    │                               └── mm-default/
    │                                   └── scenes/
    │                                       └── scene/
    │                                           └── bg01/
    │                                               └── *.3de  # Mock 3DE file
    └── jack_ryan/
        └── shots/
            └── ...
```

## Environment Variables

When mock filesystem is detected, the launcher sets:
- `SHOTBOT_MOCK=1` - Enables mock mode
- `SHOWS_ROOT=/tmp/mock_vfx` - Points to mock filesystem

## Benefits

✅ **Realistic Testing**: Actual production structure, not guessed  
✅ **No Errors**: All expected paths exist  
✅ **Visual Feedback**: Placeholder thumbnails show in UI  
✅ **Fast Setup**: One capture, use everywhere  
✅ **Safe**: No production data leaves the facility  

## Troubleshooting

### "No mock filesystem found"
Run `recreate_vfx_structure.py` first to create the structure.

### Permission errors
Make sure `/tmp/mock_vfx` is writable or use `--root ~/mock_vfx`

### Missing thumbnails
The recreator creates placeholders - they should show as gradient images with text.

### WSL display issues
This is separate from mock mode. Try:
- Using WSLg (Windows 11)
- Installing VcXsrv or X410
- Running with `QT_QPA_PLATFORM=offscreen` for headless

## Advanced Usage

### Custom Placeholder Images
Edit `recreate_vfx_structure.py` to customize the placeholder thumbnail generation.

### Adding More Shots
Edit `demo_shots.json` to add more shots to the mock data.

### Updating Structure
Re-run capture and recreate when the production structure changes.

## Example Workflow

```bash
# On VFX workstation
python capture_vfx_structure.py
# Output: vfx_structure_vfxws01_20240315_143022.json

# Transfer to dev machine
scp vfx_structure_*.json dev-machine:~/

# On development machine
cd ~/shotbot
python recreate_vfx_structure.py ~/vfx_structure_*.json
./venv/bin/python shotbot_mock.py

# You now have a fully mocked VFX environment!
```