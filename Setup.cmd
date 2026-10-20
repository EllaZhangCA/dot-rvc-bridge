@echo off
cd /d "%~dp0"
if not exist "%~dp0release-assets\tools\uv.exe" (
  echo Download the Windows easy ZIP from GitHub Releases, not the source ZIP.
  echo Developers: install uv, then run uv run --no-project --python 3.13.5 scripts/bootstrap.py
  pause
  exit /b 1
)
set "UV_CACHE_DIR=%~dp0runtime\uv-cache"
set "UV_PYTHON_INSTALL_DIR=%~dp0runtime\python"
"%~dp0release-assets\tools\uv.exe" run --no-project --python 3.13.5 "%~dp0scripts\bootstrap.py"
if errorlevel 1 echo Setup failed. See the error above and README.md.
pause
