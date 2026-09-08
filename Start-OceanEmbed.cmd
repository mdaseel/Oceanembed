@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. See PHASE7B_README.md for one-time setup.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\poc\serve.py"
pause
