@echo off
:: DAT Dashboard - Daily Report Runner
:: Runs automatically via Task Scheduler at 9:30 AM ET
:: Can also be run manually (will pause at end for manual runs)

cd /d "%~dp0"
call venv\Scripts\activate

echo [%date% %time%] Running DAT Dashboard report...
echo.

python -m src.main run

echo.
if %errorlevel% equ 0 (
    echo Report generated successfully!
    echo Check data\reports\ for output files.
) else (
    echo Report generation failed. Check error messages above.
)

:: Only pause if running interactively (not from Task Scheduler)
if "%1"=="--scheduled" exit /b %errorlevel%
pause
