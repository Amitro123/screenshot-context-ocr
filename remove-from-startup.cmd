@echo off
rem Stop starting the watcher automatically with Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\startup.ps1" -Remove
pause
