@echo off
REM ShotBot Mock Environment Launcher (Quiet Mode)
REM This script starts ShotBot with mock environment but without debug logging
REM Usage: Double-click this file or run from command prompt

echo ========================================
echo  ShotBot - Mock VFX Environment
echo ========================================
echo.
echo Starting ShotBot with 432 mock production shots...
echo.

REM Change to the shotbot directory
cd /d "%~dp0"

REM Launch ShotBot in WSL with mock environment (no debug mode)
wsl bash -c "cd '/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot' && export SHOTBOT_MOCK=1 && export SHOWS_ROOT='/tmp/mock_vfx/shows' && source venv/bin/activate && python3 shotbot.py --mock"

echo.
echo ShotBot closed.
pause
