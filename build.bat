@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tools\package_release.py
if errorlevel 1 goto failed
echo Build complete. The versioned release path is shown above.
echo Existing release folders and exam data are preserved.
echo Distribute the entire versioned release folder, including _internal.
pause
exit /b 0
:failed
echo Build failed. Review the output above.
pause
exit /b 1
