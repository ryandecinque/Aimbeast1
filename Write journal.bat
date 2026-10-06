@echo off
rem Opens your aim journal with today's heading ready. It goes on the website within 5 minutes of saving.
cd /d "%~dp0"
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set D=%%d
>>journal.md echo.
>>journal.md echo ## %D% Ryan
>>journal.md echo.
start "" notepad journal.md
