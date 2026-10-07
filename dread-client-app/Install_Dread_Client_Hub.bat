@echo off
REM Install Hub shortcuts on the desktop and Start Menu.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install_Dread_Client_Hub.ps1" %*
if errorlevel 1 (
  echo.
  echo Installer reported an error.
  pause
  exit /b 1
)
