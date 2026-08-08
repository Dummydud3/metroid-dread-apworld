' Silent launcher for Dread Client Hub (no console window).
Option Explicit

Dim sh, fso, appDir, electron, npmCmd, exitCode
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
electron = appDir & "\node_modules\electron\dist\electron.exe"

If Not fso.FileExists(electron) Then
  ' First run / missing deps — install via npm (shows a console briefly).
  npmCmd = "cmd /c ""cd /d """ & appDir & """ && npm install && if errorlevel 1 (pause & exit /b 1)"""
  exitCode = sh.Run(npmCmd, 1, True)
  If exitCode <> 0 Then
    MsgBox "Failed to install Dread Client Hub dependencies (npm install)." & vbCrLf & _
           "Install Node.js from https://nodejs.org and try again.", vbCritical, "Dread Client Hub"
    WScript.Quit 1
  End If
End If

If Not fso.FileExists(electron) Then
  MsgBox "Electron runtime not found after install:" & vbCrLf & electron, vbCritical, "Dread Client Hub"
  WScript.Quit 1
End If

sh.CurrentDirectory = appDir
sh.Run """" & electron & """ .", 1, False
