@echo off
rem Starts the screenshot watcher in the background (no window). Safe to run twice.
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
    echo Not installed yet. Run install.cmd first.
    pause
    exit /b 1
)
start "" "%PYW%" "%~dp0clipboard-watcher.pyw"
echo Watcher started. Take a screenshot with Win+Shift+S.
timeout /t 2 >nul
