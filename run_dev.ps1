# Photo2Print — הפעלת סביבת פיתוח מלאה (ללא Docker)
# מריץ API על :8000 ו-Frontend על :5173 בשני חלונות
$root = $PSScriptRoot

if (-not (Test-Path "$root\backend\.venv")) {
    Write-Host "יוצר סביבה וירטואלית ומתקין תלויות (פעם ראשונה)..." -ForegroundColor Cyan
    python -m venv "$root\backend\.venv"
    & "$root\backend\.venv\Scripts\pip.exe" install -r "$root\backend\requirements.txt"
}
if (-not (Test-Path "$root\frontend\node_modules")) {
    Write-Host "מתקין תלויות frontend..." -ForegroundColor Cyan
    Push-Location "$root\frontend"; npm install; Pop-Location
}
if (-not (Test-Path "$root\.env")) {
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host "נוצר .env מברירת המחדל — ערוך אותו להוספת מפתחות API" -ForegroundColor Yellow
}

Write-Host "מפעיל API (http://localhost:8008) ו-UI (http://localhost:5173)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "& '$root\backend\.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --port 8008 --app-dir '$root\backend'"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$root\frontend'; npm run dev"
Start-Sleep 3
Start-Process "http://localhost:5173"
