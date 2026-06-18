@echo off
REM ===================================================================
REM  ETools - portable launcher (no Python / Ollama install required)
REM  Double-click this file to start the app. It opens in your browser.
REM ===================================================================
setlocal enabledelayedexpansion
title ETools - DOGM Directional Survey

REM %~dp0 ends with a backslash.
set "ROOT=%~dp0"

REM --- Self-contained runtime + model/cache locations -----------------
set "PY=%ROOT%runtime\python\python.exe"
set "OLLAMA=%ROOT%ollama\ollama.exe"
set "OLLAMA_MODELS=%ROOT%ollama\models"
set "OLLAMA_HOST=127.0.0.1:11434"
set "HF_HOME=%ROOT%cache\hf"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
REM Generated files + a full DEBUG diagnostics log land here, off the main
REM folder, so they are easy to find and send if something goes wrong:
REM   output\logs\etools.log
set "ETOOLS_OUTPUT_DIR=%ROOT%output"

if not exist "%PY%" (
    echo [ERROR] Bundled Python not found at "%PY%".
    echo This folder looks incomplete. Copy the whole ETools_Portable folder, not just part of it.
    pause
    exit /b 1
)

REM --- Start the local AI engine (Ollama) in the background ----------
REM Only needed for the PDF -> WCR auto-extraction. Everything else runs
REM without it. Skip if something is already serving on :11434.
set "STARTED_OLLAMA="
netstat -ano | findstr /R /C:"127.0.0.1:11434 .*LISTENING" >nul 2>&1
if errorlevel 1 (
    if exist "%OLLAMA%" (
        echo Starting local AI engine ^(Ollama^) in the background...
        start "ETools AI Engine" /min "%OLLAMA%" serve
        set "STARTED_OLLAMA=1"
    ) else (
        echo [warn] Ollama not bundled - AI PDF extraction will be unavailable.
    )
) else (
    echo Local AI engine already running on :11434.
)

REM --- Launch the app (cwd = app so output/ resolves there) ----------
echo.
echo Starting ETools... your browser will open at http://localhost:8080/
echo Keep this window open while you use ETools. Close it to stop the app.
echo The FIRST PDF you parse loads the AI model and can take a minute.
echo.
echo If something goes wrong, send the log at:
echo   %ROOT%output\logs\etools.log
echo.
pushd "%ROOT%app"
"%PY%" -m etools.main
popd

REM --- Cleanup: stop the AI engine we started -----------------------
if defined STARTED_OLLAMA (
    echo Stopping local AI engine...
    taskkill /F /IM ollama.exe >nul 2>&1
)
endlocal
