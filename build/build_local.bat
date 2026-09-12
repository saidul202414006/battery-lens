@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM Battery Lens — Local Windows Build Script
REM Creates BatteryLens-Setup.exe in dist/
REM
REM Prerequisites:
REM   pip install pyinstaller
REM   choco install nsis    (or download NSIS installer from nsis.sourceforge.io)
REM
REM Usage: build\build_local.bat
REM ─────────────────────────────────────────────────────────────────────────────

setlocal
cd /d "%~dp0.."

echo.
echo  Battery Lens — Local Windows Build
echo  ════════════════════════════════════

REM ── Get version ──────────────────────────────────────────────────────────────
for /f "tokens=*" %%v in ('python -c "from version import __version__; print(__version__)"') do set "APP_VERSION=%%v"
echo  Version: %APP_VERSION%

REM ── Step 1: Install PyInstaller if missing ────────────────────────────────────
echo.
echo  [1/4] Checking PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo  Installing PyInstaller...
    pip install pyinstaller --quiet
)
echo  ^✓ PyInstaller ready

REM ── Step 2: PyInstaller build ─────────────────────────────────────────────────
echo.
echo  [2/4] Building with PyInstaller...
if exist dist\BatteryLens rmdir /s /q dist\BatteryLens
pyinstaller battery_lens.spec --distpath dist --workpath build\pyinstaller_work --noconfirm
if errorlevel 1 (
    echo.
    echo  ERROR: PyInstaller build failed.
    pause
    exit /b 1
)
echo  ^✓ PyInstaller build complete: dist\BatteryLens\

REM ── Step 3: NSIS installer ────────────────────────────────────────────────────
echo.
echo  [3/4] Creating installer with NSIS...
where makensis >nul 2>&1
if errorlevel 1 (
    echo  ^⚠  NSIS not found. Skipping installer creation.
    echo     Download NSIS from: https://nsis.sourceforge.io/Download
    echo     Or install via: choco install nsis
    echo.
    echo  You can still run the app directly:
    echo    dist\BatteryLens\BatteryLens.exe
    goto :done
)

makensis /DAPP_VERSION=%APP_VERSION% build\installer.nsi
if errorlevel 1 (
    echo  ERROR: NSIS build failed.
    pause
    exit /b 1
)

REM ── Step 4: Done ──────────────────────────────────────────────────────────────
:done
echo.
echo  [4/4] Cleaning up build artifacts...
if exist build\pyinstaller_work rmdir /s /q build\pyinstaller_work

echo.
echo  ════════════════════════════════════════════════════
if exist dist\BatteryLens-Setup.exe (
    echo   ^✓ Installer:  dist\BatteryLens-Setup.exe
) else (
    echo   ^✓ Portable:   dist\BatteryLens\BatteryLens.exe
)
echo  ════════════════════════════════════════════════════
echo.
pause
