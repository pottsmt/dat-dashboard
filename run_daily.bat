@echo off
:: DAT Dashboard - Daily Report Runner
:: Run this script after Bloomberg Excel has exported data

cd /d "%~dp0"
call venv\Scripts\activate

echo Running DAT Dashboard report...
echo.

python -m src.main run

echo.
if %errorlevel% equ 0 (
    echo Report generated successfully!
    echo Check data\reports\ for output files.
) else (
    echo Report generation failed. Check error messages above.
)

pause
