@echo off
rem Screenshot Context - installer. Double-click to install and start.
rem Add --startup to also launch the watcher automatically with Windows.
set "EXTRA="
if /I "%~1"=="--startup" set "EXTRA=-Startup"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %EXTRA%
echo.
pause
