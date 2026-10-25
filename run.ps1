Set-Location -Path $PSScriptRoot
if (Test-Path "HisaabHoshiyaar") { Set-Location "HisaabHoshiyaar" }
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Starting HisaabHoshiyaar with Supabase Cloud    " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

if (Get-Command uvicorn -ErrorAction SilentlyContinue) {
    uvicorn main:app --reload --port 8000
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python -m uvicorn main:app --reload --port 8000
} else {
    & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m uvicorn main:app --reload --port 8000
}
