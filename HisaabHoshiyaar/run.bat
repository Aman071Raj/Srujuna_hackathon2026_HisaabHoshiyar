@echo off
cd /d "%~dp0"
echo ===================================================
echo   Starting HisaabHoshiyaar with Supabase Cloud
echo ===================================================
python -m uvicorn main:app --reload --port 8000 2>nul || "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m uvicorn main:app --reload --port 8000 2>nul || py -m uvicorn main:app --reload --port 8000
pause
