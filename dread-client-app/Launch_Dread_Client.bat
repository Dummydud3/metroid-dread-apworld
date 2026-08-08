@echo off
REM Launch the Dread Client Hub (YAML editor + client / patcher)
cd /d "%~dp0"
set "SKIP_REQUIREMENTS_UPDATE=1"

where npm >nul 2>&1
if errorlevel 1 (
  echo Node.js / npm not found. Install Node.js LTS from https://nodejs.org
  pause
  exit /b 1
)

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
