@echo off
cd /d "%~dp0"
rem Starts AimStats in a small window (close it to stop) and opens the stats page in your browser.
start "AimStats - close this window to stop" /min "%~dp0app\python\python.exe" "%~dp0app\scripts\aimstats.py"
