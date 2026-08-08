@echo off
REM Metroid Dread Seed Manager Launcher
REM Launches the GUI for creating and managing Dread seeds

echo ====================================
echo Metroid Dread Seed Manager
echo ====================================
echo.

REM Check for Python 3
python --version 2>&1 | findstr /C:"Python 3" >nul
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=python
    goto :found_python
)

py -3 --version 2>&1 | findstr /C:"Python 3" >nul
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=py -3
    goto :found_python
)

python3 --version 2>&1 | findstr /C:"Python 3" >nul
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=python3
    goto :found_python
)

echo ERROR: Python 3 not found!
echo Please install Python 3.10 or newer.
pause
exit /b 1

:found_python
echo Found Python 3: %PYTHON_CMD%
echo.

REM Check for PyYAML
%PYTHON_CMD% -c "import yaml" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Installing required dependency: PyYAML...
    %PYTHON_CMD% -m pip install pyyaml
)

REM Launch GUI
echo Launching Seed Manager GUI...
echo.
%PYTHON_CMD% "%~dp0DreadSeedManager.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo GUI closed with error code %ERRORLEVEL%
    pause
)
