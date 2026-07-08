@echo off
set "PATH=C:\msys64\ucrt64\bin;%PATH%"
C:\msys64\ucrt64\bin\python.exe -m pytest tests/ -v %*
pause
