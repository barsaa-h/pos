@echo off
title Миний дэлгүүр — POS
cd /d "%~dp0.."

echo ============================================
echo   My Store POS — Windows
echo ============================================
echo.

:: ── Find Python ──
set PYTHON=
for %%p in (python python3 py) do (
    where %%p >nul 2>&1
    if not errorlevel 1 set PYTHON=%%p
)
if "%PYTHON%"=="" (
    echo [ERROR] Python not found.
    echo Install Python 3.10+ from https://python.org
    echo Check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
echo [ OK ] Python: %PYTHON%

:: ── Create virtual environment ──
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Creating virtual environment...
    %PYTHON% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
)
call venv\Scripts\activate.bat

:: ── Install dependencies ──
echo [INFO] Checking dependencies...
venv\Scripts\python.exe -c "import flask, webview" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    venv\Scripts\python.exe -m pip install --upgrade pip -q
    venv\Scripts\python.exe -m pip install -r requirements.txt -q
    if exist "windows\requirements-windows.txt" (
        venv\Scripts\python.exe -m pip install -r windows\requirements-windows.txt -q
    )
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo [ OK ] Dependencies installed
)

:: ── Initialize database ──
if not exist "pos.db" (
    echo [INFO] Creating database...
    venv\Scripts\python.exe -c "import database as db; db.init_db()"
)
if not exist "logs" mkdir logs
if not exist "backups" mkdir backups
if not exist "static\uploads" mkdir static\uploads

echo.
echo [INFO] Starting POS...
venv\Scripts\python.exe windows/desktop.py
echo POS closed.
pause
