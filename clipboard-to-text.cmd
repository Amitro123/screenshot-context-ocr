@echo off
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\ocr.py" --clipboard --copy %*
if errorlevel 1 pause
