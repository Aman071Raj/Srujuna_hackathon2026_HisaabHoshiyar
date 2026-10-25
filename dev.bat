@echo off
cd /d "%~dp0"
if exist "HisaabHoshiyaar" cd HisaabHoshiyaar
echo ===================================================
echo   Starting HisaabHoshiyaar Dev Server (Port 8000)
echo ===================================================
python -m uvicorn main:app --reload --port 8000
pause
