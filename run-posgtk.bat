@echo off
cd /d "%~dp0"
set "PATH=C:\msys64\ucrt64\bin;%PATH%"
set "POS_DB_PATH=data\pos.db"
set "PANGOCAIRO_BACKEND=fc"
echo Starting POS GTK...
C:\msys64\ucrt64\bin\python.exe -m posgtk.main
pause
