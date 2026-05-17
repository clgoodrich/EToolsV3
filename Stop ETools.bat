@echo off
REM Stops the silent ETools server. Only kills python processes serving on port 8080.

setlocal
echo Looking for ETools server on port 8080...

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8080" ^| findstr "LISTENING"') do (
    echo Stopping PID %%P
    taskkill /F /PID %%P >nul 2>&1
)
echo Done.
endlocal
timeout /t 2 >nul
