# Windows PowerShell launcher (Unicode-friendly)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
Set-Location $rootDir

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  My Store POS — Windows" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$python = (Get-Command python -ErrorAction SilentlyContinue) ??
          (Get-Command python3 -ErrorAction SilentlyContinue) ??
          (Get-Command py -ErrorAction SilentlyContinue)
if (-not $python) {
    Write-Host "[ERROR] Python not found." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[ OK ] Python: $($python.Source)" -ForegroundColor Green

if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "[INFO] Creating virtual environment..." -ForegroundColor Yellow
    & $python.Source -m venv venv
}
$venvPython = "$rootDir\venv\Scripts\python.exe"

& $venvPython -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INFO] Installing dependencies..." -ForegroundColor Yellow
    & $venvPython -m pip install --upgrade pip -q
    & $venvPython -m pip install -r requirements.txt -q
    & $venvPython -m pip install -r windows\requirements-windows.txt -q
}

if (-not (Test-Path "pos.db")) {
    & $venvPython -c "import database as db; db.init_db()"
}
@("logs", "backups", "static\uploads") | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ | Out-Null }
}

Write-Host "[INFO] Starting POS..." -ForegroundColor Yellow
& $venvPython windows/desktop.py
Write-Host "POS closed." -ForegroundColor Gray
Read-Host "Press Enter to exit"
