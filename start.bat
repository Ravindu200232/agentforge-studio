@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
set "oterm_exit=%errorlevel%"
if "%~1"=="" pause
exit /b %oterm_exit%
