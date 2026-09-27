@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio.ps1" %*
set "studio_exit=%errorlevel%"
if "%~1"=="" pause
exit /b %studio_exit%
