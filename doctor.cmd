@echo off
rem Health check: shows what works, what is missing, and the next step.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\doctor.ps1"
echo.
pause
