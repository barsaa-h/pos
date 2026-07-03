@echo off
:: Cross-platform launcher — auto-detects OS and runs the right platform
title Миний дэлгүүр — POS

cd /d "%~dp0"

:: Detect platform and delegate
ver | findstr /i "Windows" >nul
if %errorlevel% equ 0 (
    call windows\start.bat
) else (
    echo This launcher is for Windows. On Ubuntu use: ./ubuntu/start.sh
    pause
)
