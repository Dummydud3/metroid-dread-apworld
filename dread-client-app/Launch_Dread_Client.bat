@echo off
REM Launch the Dread Client Hub (YAML editor + client / patcher)
setlocal EnableExtensions
cd /d "%~dp0"
set "SKIP_REQUIREMENTS_UPDATE=1"

where npm >nul 2>&1
if errorlevel 1 (
  echo Node.js / npm not found. Install Node.js LTS from https://nodejs.org
  pause
  exit /b 1
)

REM Ensure system Python has websockets / CommonClient deps before Hub spawns it.
REM ensure_client_deps.py finds the same 3.11–3.13 interpreter Hub will use.
set "ENSURE_SCRIPT=%~dp0..\ensure_client_deps.py"
set "WORLD_DIR=%~dp0.."
if not exist "%ENSURE_SCRIPT%" goto :npm_deps

echo Checking Python client dependencies...
where py >nul 2>&1
if errorlevel 1 goto :ensure_with_python
py -3 "%ENSURE_SCRIPT%" --world "%WORLD_DIR%"
if errorlevel 1 goto :ensure_failed
goto :npm_deps

:ensure_with_python
where python >nul 2>&1
if errorlevel 1 goto :ensure_no_python
python "%ENSURE_SCRIPT%" --world "%WORLD_DIR%"
if errorlevel 1 goto :ensure_failed
goto :npm_deps

:ensure_no_python
echo.
echo No usable Python 3.11–3.13 found for the Hub client.
echo Archipelago Text Client uses its own bundled Python — Hub needs a system install.
echo.
echo Fix:
echo   1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/
echo      ^(check "Add python.exe to PATH"^)
echo   2. Or with the new Python install manager:  py install 3.12
echo   3. Confirm with:  py -0
echo   4. Re-run this launcher.
echo.
pause
exit /b 2

:ensure_failed
echo.
echo Python client dependency check failed.
echo Hub Connect will also retry — or install Python from python.org and Add to PATH.
echo.
pause
exit /b 1

:npm_deps
echo.

if not exist "node_modules\electron" (
  echo Installing Electron dependencies...
  call npm install
  if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
  )
)

if not exist "node_modules\adm-zip" (
  echo Installing missing packages...
  call npm install
)

rem Auto-repair incomplete Electron binary install.
if not exist "node_modules\electron\path.txt" goto :repair_electron
if exist "node_modules\electron\dist\electron.exe" goto :start_hub
if exist "node_modules\electron\dist\electron" goto :start_hub

:repair_electron
echo Electron binary missing or incomplete — repairing...
if exist "node_modules\electron" rmdir /s /q "node_modules\electron"
call npm install
if errorlevel 1 (
  echo Electron repair failed.
  pause
  exit /b 1
)

:start_hub
npm start
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  pause
)
exit /b %RC%
