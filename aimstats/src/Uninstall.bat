@echo off
title AimStats - Uninstall
cd /d "%~dp0"
"%~dp0app\python\python.exe" "%~dp0app\scripts\installer.py" uninstall
echo.
pause
