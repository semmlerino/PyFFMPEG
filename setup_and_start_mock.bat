@echo off
REM ShotBot Mock Environment Setup and Launcher
REM This script verifies/creates the mock VFX environment, then starts ShotBot
REM Usage: Double-click this file or run from command prompt

setlocal enabledelayedexpansion

echo ========================================
echo  ShotBot - Mock VFX Environment Setup
echo ========================================
echo.

REM Change to the shotbot directory
cd /d "%~dp0"

REM Check if mock environment exists
echo Checking for mock VFX environment...
wsl bash -c "[ -d '/tmp/mock_vfx/shows' ] && echo 'EXISTS' || echo 'MISSING'" > temp_check.txt
set /p ENV_STATUS=<temp_check.txt
del temp_check.txt

if "!ENV_STATUS!"=="MISSING" (
    echo.
    echo Mock VFX environment not found!
    echo Creating mock environment from vfx_structure_complete.json...
    echo This may take a few minutes...
    echo.

    wsl bash -c "cd '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot' && source venv/bin/activate && python3 recreate_vfx_structure.py vfx_structure_complete.json"

    if errorlevel 1 (
        echo.
        echo ERROR: Failed to create mock environment!
        echo Please check that vfx_structure_complete.json exists.
        pause
        exit /b 1
    )

    echo.
    echo Mock environment created successfully!
) else (
    echo Mock VFX environment found at /tmp/mock_vfx/shows
)

echo.
echo Verifying mock environment...
wsl bash -c "cd '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot' && export SHOTBOT_MOCK=1 && export SHOTBOT_HEADLESS=1 && source venv/bin/activate && python3 verify_mock_environment.py"

if errorlevel 1 (
    echo.
    echo WARNING: Mock environment verification failed!
    echo ShotBot may not work correctly.
    echo.
    choice /M "Do you want to continue anyway"
    if errorlevel 2 exit /b 1
)

echo.
echo ========================================
echo  Starting ShotBot...
echo ========================================
echo.
echo Configuration:
echo   - Mock Mode: ENABLED
echo   - Debug Mode: ENABLED
echo   - Shows Root: /tmp/mock_vfx/shows
echo   - Mock Shots: 432 production shots
echo.

REM Launch ShotBot with mock environment
wsl bash -c "cd '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot' && export SHOTBOT_MOCK=1 && export SHOTBOT_DEBUG=1 && export SHOWS_ROOT='/tmp/mock_vfx/shows' && source venv/bin/activate && python3 shotbot.py --mock"

echo.
echo ShotBot closed.
pause
