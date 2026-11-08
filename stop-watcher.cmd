@echo off
rem Stops the screenshot watcher (only this plugin's process).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
timeout /t 2 >nul
