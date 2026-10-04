@echo off
rem Sets up Claude Talk on this PC, or updates it after a git pull. Double-click it or run it in a terminal.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "code=%errorlevel%"
pause
exit /b %code%
