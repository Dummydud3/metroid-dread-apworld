@echo off
REM Install Metroid Bread Client Hub — Desktop + Start Menu shortcuts
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install_Dread_Client_Hub.ps1" %*
if errorlevel 1 (
  echo.
  echo Installer reported an error.
  pause
  exit /b 1
)
