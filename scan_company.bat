@echo off
:: DAT Dashboard - Scan SEC Filings for a Company
:: Usage: scan_company.bat TICKER

cd /d "%~dp0"
call venv\Scripts\activate

if "%1"=="" (
    echo Usage: scan_company.bat TICKER
    echo Example: scan_company.bat MSTR
    pause
    exit /b 1
)

echo Scanning SEC filings for %1...
echo.

python -m src.main scan %1 --lookback 365

echo.
echo Scan complete. Run 'python -m src.main show %1' to view extracted data.
pause
