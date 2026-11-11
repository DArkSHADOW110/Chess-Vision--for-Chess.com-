@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Project Python environment is missing. See QUICKSTART.md.
    pause
    exit /b 1
)
start "Chess Vision" ".venv\Scripts\pythonw.exe" "src\app.py"
