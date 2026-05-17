@echo off
REM Launch ETools - visible console (good for debugging / first-run verification)
REM Double-click this file to start the app and open your browser.

setlocal
cd /d "%~dp0"

REM Prefer the project venv; fall back to system Python if missing.
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

title ETools - DOGM Directional Survey

REM Kill any prior instance still bound to :8080 first.
call "Stop ETools.bat"

echo Starting ETools at http://localhost:8080/ ...
echo Close this window to stop the server.
echo.

"%PY%" -m etools.main

REM If the server exits unexpectedly, hold the window so the error is readable.
if errorlevel 1 (
    echo.
    echo ETools exited with errors. Press any key to close.
    pause >nul
)
endlocal
