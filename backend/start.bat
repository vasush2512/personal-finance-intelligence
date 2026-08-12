@echo off
REM Starts the backend API. Double-click this file, or run it from a terminal.
REM Developer convenience only - not part of the PRD.

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo.
    echo Could not find venv\Scripts\activate.bat
    echo Create the environment first:  python -m venv venv
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo.
echo ============================================================
echo   Expense Tracker API is starting.
echo.
echo   Open this in your browser:
echo       http://127.0.0.1:8000/docs
echo.
echo   Press Ctrl+C in this window to stop the server.
echo ============================================================
echo.

uvicorn app.main:app --reload

echo.
echo Server stopped.
pause
