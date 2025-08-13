@echo off
title EToolsV3 Launcher

echo Starting EToolsV3...
echo Detailed output will be saved to log.txt
echo.

REM This command runs your python script.
REM > log.txt sends all standard output to a file named log.txt.
REM 2>&1 sends all standard error (where tracebacks live) to the same place.
cd /d "%~dp0"
WinPython\python\python.exe main.py > log.txt 2>&1

echo.
echo Application has finished. Please check log.txt for details and errors.
pause