@echo off
title HisaabHoshiyaar Server
cd /d "%~dp0"
echo ========================================================
echo   Starting HisaabHoshiyaar Server
echo   Open in browser: http://localhost:8000
echo ========================================================
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
) else (
    python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
)
pause
