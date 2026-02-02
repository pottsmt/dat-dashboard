@echo off
echo ============================================
echo DAT Dashboard - Windows Setup Script
echo ============================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

echo [1/5] Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

echo [2/5] Activating virtual environment...
call venv\Scripts\activate

echo [3/5] Upgrading pip...
python -m pip install --upgrade pip --quiet

echo [4/5] Installing dependencies...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo [5/5] Installing DAT Dashboard...
pip install -e . --quiet

echo.
echo ============================================
echo Setup complete!
echo ============================================
echo.
echo Next steps:
echo.
echo 1. Copy .env.example to .env and fill in your credentials:
echo    copy .env.example .env
echo    notepad .env
echo.
echo 2. Create Bloomberg Excel workbook using templates\bloomberg_template.md
echo.
echo 3. Run the dashboard:
echo    venv\Scripts\activate
echo    python -m src.main run
echo.
pause
