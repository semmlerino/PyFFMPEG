#!/bin/bash
# Quick screenshot command - run this when ShotBot is visible
powershell.exe -ExecutionPolicy Bypass -File screenshot_windows.ps1
echo "View with: cat /mnt/c/temp/shotbot_screenshot.png (or use Read tool in Claude)"