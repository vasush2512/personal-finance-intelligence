@echo off
REM Starts the dashboard. Double-click this file.
REM The backend must be running too - see backend\start.bat.

cd /d "%~dp0"

if not exist "node_modules" (
    echo.
    echo Installing dependencies for the first time. This takes a minute...
    echo.
    call npm install
)

echo.
echo ============================================================
echo   Expense Tracker dashboard is starting.
echo.
echo   Open this in your browser:
echo       http://localhost:5173
echo.
echo   The backend must also be running:
echo       backend\start.bat
echo.
echo   Press Ctrl+C in this window to stop.
echo ============================================================
echo.

call npm run dev

echo.
echo Dashboard stopped.
pause
