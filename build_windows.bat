@echo off
REM ============================================================
REM Build script for openQCM-pm-monitor — Windows one-file .exe
REM
REM Run from a Python environment that already has the runtime
REM dependencies installed (PyQt5, pyqtgraph, scipy, numpy,
REM pyserial, pandas).  PyInstaller itself is installed by this
REM script if missing.
REM ============================================================

echo.
echo === openQCM-pm-monitor — Windows build ===
echo.

REM Ensure PyInstaller is available
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install "pyinstaller>=6.0"
)

REM Wipe previous build artefacts for a clean output
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist

REM Build using the spec file
python -m PyInstaller openqcm-pm-monitor.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo BUILD FAILED — see PyInstaller output above.
    pause
    exit /b 1
)

echo.
echo === Build complete ===
echo Executable: dist\openQCM-pm-monitor.exe
echo.
pause
