@echo off
echo ============================================================
echo DAT Dashboard - Automated Bloomberg Export ^& Run
echo ============================================================
echo.
echo This will:
echo   1. Open Bloomberg Excel template
echo   2. Wait 30 seconds for data to load
echo   3. Export to CSV
echo   4. Generate dashboard report
echo   5. Open the report in your browser
echo.
echo Make sure Bloomberg Terminal is running!
echo.
pause

cd /d "%~dp0"
python scripts\run_dashboard_auto.py --wait 30

echo.
pause
