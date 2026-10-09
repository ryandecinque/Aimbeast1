@echo off
title AimStats - Install
cd /d "%~dp0"
"%~dp0app\python\python.exe" "%~dp0app\scripts\installer.py" install
echo.
pause
