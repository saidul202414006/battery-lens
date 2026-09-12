@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM Battery Lens — Windows Install Script
REM Run as a normal user (no admin required).
REM ─────────────────────────────────────────────────────────────────────────────

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo  Battery Lens — Windows Setup
echo  ═════════════════════════════════════

REM ── 1. Check for Python ──────────────────────────────────────────────────────
echo.
echo  [1/5] Checking for Python 3.10+...

python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python not found.
    echo.
    echo  Please install Python 3.10 or newer from:
    echo    https://www.python.org/downloads/windows/
    echo.
    echo  Important: During installation, check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

REM Check Python version is 3.10+
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python 3.10 or newer is required.
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo  Found: %%i
    echo.
    echo  Download the latest Python from: https://www.python.org/downloads/windows/
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo  ^✓ Found: %%i

REM ── 2. Create virtual environment ────────────────────────────────────────────
echo.
echo  [2/5] Setting up virtual environment...

if exist ".venv\Scripts\python.exe" (
    echo  ^✓ Virtual environment already exists -- updating packages.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo  ERROR: Failed to create virtual environment.
        echo  Try: python -m pip install virtualenv
        pause
        exit /b 1
    )
    echo  ^✓ Virtual environment created.
)

REM ── 3. Upgrade pip ───────────────────────────────────────────────────────────
echo.
echo  [3/5] Upgrading pip...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
echo  ^✓ pip up to date.

REM ── 4. Install packages ───────────────────────────────────────────────────────
echo.
echo  [4/5] Installing Python packages...

.venv\Scripts\pip.exe install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo  ERROR: Package installation failed.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)

.venv\Scripts\pip.exe install -r requirements-windows.txt --quiet 2>nul

echo  ^✓ All packages installed.

REM ── 5. Create launcher shortcut ───────────────────────────────────────────────
echo.
echo  [5/5] Creating launcher...

REM Write a simple launcher .bat
set "LAUNCHER=%SCRIPT_DIR%battery-lens.bat"
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%"
    echo start "" "%SCRIPT_DIR%.venv\Scripts\pythonw.exe" "%SCRIPT_DIR%main.py"
) > "%LAUNCHER%"

echo  ^✓ Launcher created: %LAUNCHER%

REM ── Done ─────────────────────────────────────────────────────────────────────
echo.
echo  ══════════════════════════════════════════════════════════
echo   Battery Lens is ready!
echo.
echo   Launch:  Double-click battery-lens.bat
echo            (The app will appear in your system tray)
echo.
echo   To run on Windows startup:
echo     Open the app ^> Settings ^> check "Run Battery Lens
echo     on Windows Startup" ^> Save Settings
echo  ══════════════════════════════════════════════════════════
echo.
pause
