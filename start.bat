@echo off
rem No_Loop - one command to start the local UI.
rem Delegates to start.ps1 with the execution policy relaxed for this process
rem only (nothing about the machine is changed). Any arguments are forwarded:
rem   start.bat --port 9000
rem   start.bat --no-browser
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
exit /b %ERRORLEVEL%
