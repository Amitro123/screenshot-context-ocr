@echo off
rem Start the watcher automatically at every Windows sign-in.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\startup.ps1"
pause
