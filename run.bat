@echo off
title Cyber Snake 2077 - Multiplayer Arcade Server
echo ========================================================
echo   Launching CYBER SNAKE 2077 Online Multiplayer Server
echo ========================================================
echo.

set PYTHON_CMD=python
where python >nul 2>nul
if %errorlevel% neq 0 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    )
)

echo Using Python: %PYTHON_CMD%
echo.
echo Fetching local network link for your friends...
echo.
echo --------------------------------------------------------
echo   Share this link with your friends on your network:
echo   http://192.168.1.134:8000
echo --------------------------------------------------------
echo.
echo Press Ctrl+C in this window to stop the server.
echo.

start "" http://192.168.1.134:8000
%PYTHON_CMD% -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
pause
