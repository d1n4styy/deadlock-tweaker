@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Deadlock Tweaker — Launcher

:: ============================================================
::  Deadlock Tweaker — Open Source Launcher
::  GitHub: https://github.com/d1n4styy/deadlock-tweaker
:: ============================================================

set NODE_OK=0
set NPM_OK=0

:: 1. Refresh PATH (picks up winget installs in same session)
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable(\"Path\",\"Machine\") + \";\" + [System.Environment]::GetEnvironmentVariable(\"Path\",\"User\")"') do set "PATH=%%i"

:: 2. Check Node.js
node --version >nul 2>&1
if %errorlevel% == 0 set NODE_OK=1

if %NODE_OK%==0 (
    echo.
    echo  [!] Node.js not found. Installing via winget...
    echo.
    winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements --silent
    if errorlevel 1 (
        echo  [ERROR] Could not install Node.js.
        echo  Please install manually from: https://nodejs.org
        pause
        exit /b 1
    )
    :: Refresh PATH again
    for /f "tokens=*" %%i in ('powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable(\"Path\",\"Machine\") + \";\" + [System.Environment]::GetEnvironmentVariable(\"Path\",\"User\")"') do set "PATH=%%i"
    echo  [OK] Node.js installed.
)

:: 3. Install npm dependencies if node_modules missing
if not exist "%~dp0node_modules\" (
    echo.
    echo  [*] Installing dependencies (first run only)...
    cd /d "%~dp0"
    npm install --omit=dev
    if errorlevel 1 (
        echo  [ERROR] npm install failed.
        pause
        exit /b 1
    )
    echo  [OK] Dependencies installed.
)

:: 4. Python backend check (needed for backend/server.py)
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Python not found. Installing Python 3.12...
    winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent
    for /f "tokens=*" %%i in ('powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable(\"Path\",\"Machine\") + \";\" + [System.Environment]::GetEnvironmentVariable(\"Path\",\"User\")"') do set "PATH=%%i"
)

:: 5. Launch
echo.
echo  [*] Starting Deadlock Tweaker...
cd /d "%~dp0"
npm start
endlocal
