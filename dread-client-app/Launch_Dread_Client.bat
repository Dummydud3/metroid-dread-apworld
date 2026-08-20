@echo off
REM Launch the Metroid Bread Client Hub (YAML editor + client / patcher)
setlocal EnableExtensions
cd /d "%~dp0"
set "SKIP_REQUIREMENTS_UPDATE=1"

REM Prefer npm.cmd so we never hit PowerShell's npm.ps1 under Restricted policy.
where npm.cmd >nul 2>&1
if errorlevel 1 (
  where npm >nul 2>&1
  if errorlevel 1 (
    echo Node.js / npm not found. Install Node.js 24 from https://nodejs.org/dist/latest-v24.x/
    pause
    exit /b 1
  )
)
set "NPM=npm.cmd"
where npm.cmd >nul 2>&1
if errorlevel 1 set "NPM=npm"

where node >nul 2>&1
if errorlevel 1 (
  echo Node.js not found. Install Node.js 24 from https://nodejs.org/dist/latest-v24.x/
  pause
  exit /b 1
)

REM Electron 33 install.js uses extract-zip, which silently fails on Node 26.x
REM (path.txt / electron.exe never appear; npm start then throws the reinstall Error).
REM Majors ^>=25 are refused; managed Node 24 from the Hub Setup Wizard is preferred.
for /f "usebackq delims=" %%A in (`node -p "process.versions.node.split('.')[0]" 2^>nul`) do set "NODE_MAJOR=%%A"
if not defined NODE_MAJOR set "NODE_MAJOR=0"
if %NODE_MAJOR% GEQ 25 (
  echo.
  echo Node.js %NODE_MAJOR% is not supported for the Metroid Bread Client Hub.
  echo Electron cannot download its binary on Node 26.x ^(extract-zip bug^).
  echo.
  echo Fix: install Node.js 24 from https://nodejs.org/dist/latest-v24.x/
  echo   ^(or use Archipelago Launcher → Hub Setup Wizard → Install Node 24^)
  echo   then reopen this launcher ^(or wipe node_modules and reinstall^).
  echo.
  echo Current node:
  node -v
  echo.
  pause
  exit /b 25
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

REM Electron postinstall must run (downloads binary). Clear blockers.
set "ELECTRON_SKIP_BINARY_DOWNLOAD="
set "npm_config_ignore_scripts=false"

REM Ensure project .npmrc allows Electron postinstall (create or repair).
if not exist ".npmrc" goto :write_npmrc
findstr /i /c:"ignore-scripts=true" ".npmrc" >nul 2>&1
if not errorlevel 1 goto :write_npmrc
findstr /i /c:"ignore-scripts=false" ".npmrc" >nul 2>&1
if errorlevel 1 (
  echo ignore-scripts=false>> ".npmrc"
)
findstr /i /c:"dangerously-allow-all-scripts=" ".npmrc" >nul 2>&1
if errorlevel 1 (
  echo dangerously-allow-all-scripts=true>> ".npmrc"
)
goto :after_npmrc

:write_npmrc
(
  echo ignore-scripts=false
  echo dangerously-allow-all-scripts=true
) > ".npmrc"

:after_npmrc

if not exist "node_modules\electron" (
  echo Installing Electron dependencies...
  call %NPM% install --no-ignore-scripts
  if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
  )
)

if not exist "node_modules\adm-zip" (
  echo Installing missing packages...
  call %NPM% install --no-ignore-scripts
)

REM Require path.txt + platform binary before npm start (mirrors electron/index.js).
call :electron_healthy
if not errorlevel 1 goto :start_hub

:repair_electron
echo Electron binary missing or incomplete — repairing...
if exist "node_modules\electron\install.js" (
  echo Trying electron install.js...
  pushd "node_modules\electron"
  node install.js
  popd
)
call :electron_healthy
if not errorlevel 1 goto :start_hub

echo Force-removing node_modules\electron and reinstalling with scripts enabled...
if exist "node_modules\electron" rmdir /s /q "node_modules\electron"
call %NPM% install --no-ignore-scripts
if errorlevel 1 (
  echo Electron repair npm install failed.
  pause
  exit /b 1
)
if exist "node_modules\electron\install.js" (
  pushd "node_modules\electron"
  node install.js
  popd
)
call :electron_healthy
if not errorlevel 1 goto :start_hub

echo.
echo Electron still failed to install correctly after repair.
echo path.txt / electron.exe are still missing under node_modules\electron.
echo.
echo This usually means Node.js is too new ^(24.16+ / 26.x^).
echo Install Node.js 24 from https://nodejs.org/dist/latest-v24.x/ then run:
echo   rmdir /s /q node_modules
echo   npm install --no-ignore-scripts
echo.
node -v
echo.
pause
exit /b 1

:start_hub
call :electron_healthy
if errorlevel 1 (
  echo Refusing to start: Electron binary still missing.
  pause
  exit /b 1
)
call %NPM% start
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  pause
)
exit /b %RC%

:electron_healthy
REM exit 0 = healthy, 1 = broken
if not exist "node_modules\electron\path.txt" exit /b 1
if exist "node_modules\electron\dist\electron.exe" exit /b 0
if exist "node_modules\electron\dist\electron" exit /b 0
exit /b 1
