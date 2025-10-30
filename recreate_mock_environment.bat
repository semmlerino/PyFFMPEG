@echo off
REM Recreate Mock VFX Environment
REM This script rebuilds the mock VFX filesystem from vfx_structure_complete.json
REM Usage: Run when you need to reset or recreate the mock environment

echo ========================================
echo  Recreate Mock VFX Environment
echo ========================================
echo.
echo This will recreate the mock VFX environment at /tmp/mock_vfx
echo.
echo WARNING: This will DELETE any existing mock environment!
echo.

choice /M "Do you want to continue"
if errorlevel 2 (
    echo.
    echo Operation cancelled.
    pause
    exit /b 0
)

echo.
echo Removing old mock environment...
wsl bash -c "rm -rf /tmp/mock_vfx"

echo Creating new mock environment...
echo This will create:
echo   - 11,386 directories
echo   - 29,335 files
echo   - 432 production shots from 3 shows
echo.
echo Please wait, this may take 2-3 minutes...
echo.

cd /d "%~dp0"

wsl bash -c "cd '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot' && source venv/bin/activate && python3 recreate_vfx_structure.py vfx_structure_complete.json"

if errorlevel 1 (
    echo.
    echo ERROR: Failed to create mock environment!
    echo.
    echo Possible issues:
    echo   - vfx_structure_complete.json not found
    echo   - Insufficient disk space
    echo   - WSL filesystem issues
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Verifying Mock Environment
echo ========================================
echo.

wsl bash -c "cd '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot' && export SHOTBOT_MOCK=1 && export SHOTBOT_HEADLESS=1 && source venv/bin/activate && python3 verify_mock_environment.py"

if errorlevel 1 (
    echo.
    echo WARNING: Verification found issues!
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Mock Environment Ready!
echo ========================================
echo.
echo You can now run start_mock.bat to launch ShotBot
echo with the complete mock VFX environment.
echo.
pause
