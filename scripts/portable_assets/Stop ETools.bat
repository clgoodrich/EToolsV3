@echo off
REM Stops a running ETools app + its bundled Ollama AI engine.
echo Stopping ETools...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8080" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
)
taskkill /F /IM ollama.exe >nul 2>&1
echo Done.
timeout /t 2 >nul
