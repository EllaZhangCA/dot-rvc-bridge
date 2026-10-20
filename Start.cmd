@echo off
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Please run Setup.cmd first.
  pause
  exit /b 1
)
start "Dot RVC Bridge" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0scripts\desktop.py"
