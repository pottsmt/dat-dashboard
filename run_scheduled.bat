@echo off
:: Called by Windows Task Scheduler - no pause at end
cd /d "C:\Users\Matthew\claude-projects\dat-dashboard"

echo [%date% %time%] Scheduled DAT Dashboard report run >> data\scheduler.log 2>&1
"C:\Users\Matthew\claude-projects\dat-dashboard\venv\Scripts\python.exe" -m src.main run >> data\scheduler.log 2>&1

if %errorlevel% neq 0 (
    echo [%date% %time%] Report FAILED >> data\scheduler.log 2>&1
) else (
    echo [%date% %time%] Report completed successfully >> data\scheduler.log 2>&1
)
