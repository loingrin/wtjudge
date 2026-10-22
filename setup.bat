@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -c "import struct,sys; print('Python',sys.version.split()[0],str(struct.calcsize('P')*8)+'-bit'); sys.exit(0 if sys.version_info >= (3,11) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo Python 3.11 or later, 64-bit is required.
    echo Install 64-bit Python, then create a new .venv as described in README.md.
    goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Setup complete. Double-click run.bat to start.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.11+ 64-bit and check network access.
pause
exit /b 1
