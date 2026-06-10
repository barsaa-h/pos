# start.ps1 — Windows PowerShell launcher for POS
# Right-click → Run with PowerShell, or double-click via .bat wrapper
# PowerShell has better Unicode support than cmd.exe

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Миний дэлгүүр — POS систем" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Find Python ──
$python = (Get-Command python -ErrorAction SilentlyContinue) ?? (Get-Command python3 -ErrorAction SilentlyContinue)
if (-not $python) {
    Write-Host "[ERROR] Python not found. Install from https://python.org" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[ OK ] Using $($python.Source)" -ForegroundColor Green

# ── Create virtual environment ──
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "[INFO] Creating virtual environment ..." -ForegroundColor Yellow
    & $python.Source -m venv venv
    Write-Host "[ OK ] venv created" -ForegroundColor Green
}

# ── Activate and install dependencies ──
$venvPython = "$scriptDir\venv\Scripts\python.exe"
& $venvPython -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INFO] Installing dependencies ..." -ForegroundColor Yellow
    & $venvPython -m pip install --upgrade pip -q
    & $venvPython -m pip install -r requirements.txt -q
    Write-Host "[ OK ] Dependencies installed" -ForegroundColor Green
}

# ── Initialize database ──
if (-not (Test-Path "pos.db")) {
    Write-Host "[INFO] Creating database ..." -ForegroundColor Yellow
    & $venvPython -c "import database as db; db.init_db()"
    Write-Host "[ OK ] Database ready" -ForegroundColor Green
}

# ── Create backups folder ──
if (-not (Test-Path "backups")) {
    New-Item -ItemType Directory -Path "backups" | Out-Null
}

# ── Launch ──
Write-Host ""
Write-Host "[INFO] Starting POS ..." -ForegroundColor Yellow
Write-Host ""
& $venvPython desktop.py

Write-Host ""
Write-Host "POS has closed." -ForegroundColor Gray
Read-Host "Press Enter to exit"
