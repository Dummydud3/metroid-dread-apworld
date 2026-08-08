#Requires -Version 5.1
<#
.SYNOPSIS
  Install Dread Client Hub shortcuts (Desktop + Start Menu) and ensure npm deps.
#>
param(
  [switch]$Silent,
  [switch]$NoDesktop,
  [switch]$NoStartMenu,
  [switch]$SkipDeps,
  [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$AppName = "Dread Client Hub"
$AppDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $AppDir
$LauncherVbs = Join-Path $AppDir "Launch_Dread_Hub.vbs"
$LauncherBat = Join-Path $AppDir "Launch_Dread_Client.bat"
$IconCandidates = @(
  (Join-Path $AppDir "icon.ico"),
  (Join-Path $RepoRoot "data\icon.ico"),
  (Join-Path $AppDir "node_modules\electron\dist\electron.exe")
)

function Get-IconPath {
  foreach ($p in $IconCandidates) {
    if (Test-Path -LiteralPath $p) { return $p }
  }
  return $LauncherVbs
}

function Ensure-AppIcon {
  $dest = Join-Path $AppDir "icon.ico"
  if (Test-Path -LiteralPath $dest) { return $dest }
  $src = Join-Path $RepoRoot "data\icon.ico"
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination $dest -Force
    return $dest
  }
  return (Get-IconPath)
}

function Get-ShortcutPaths {
  $desktop = [Environment]::GetFolderPath("Desktop")
  $startMenu = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\Dread Client Hub"
  [pscustomobject]@{
    DesktopLnk   = Join-Path $desktop "$AppName.lnk"
    StartMenuDir = $startMenu
    StartMenuLnk = Join-Path $startMenu "$AppName.lnk"
    UninstallLnk = Join-Path $startMenu "Uninstall $AppName.lnk"
  }
}

function New-Shortcut {
  param(
    [Parameter(Mandatory)][string]$LinkPath,
    [Parameter(Mandatory)][string]$TargetPath,
    [string]$Arguments = "",
    [string]$WorkDir = $AppDir,
    [string]$IconPath = "",
    [string]$Description = $AppName
  )

  $dir = Split-Path -Parent $LinkPath
  if (-not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
  }

  $wsh = New-Object -ComObject WScript.Shell
  $sc = $wsh.CreateShortcut($LinkPath)
  $sc.TargetPath = $TargetPath
  if ($Arguments) { $sc.Arguments = $Arguments }
  $sc.WorkingDirectory = $WorkDir
  $sc.WindowStyle = 1
  $sc.Description = $Description
  if ($IconPath -and (Test-Path -LiteralPath $IconPath)) {
    if ($IconPath.ToLower().EndsWith(".exe")) {
      $sc.IconLocation = "$IconPath,0"
    } else {
      $sc.IconLocation = $IconPath
    }
  }
  $sc.Save()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($wsh) | Out-Null
}

function Install-NpmDeps {
  Write-Host "Installing / verifying npm dependencies..."
  Push-Location $AppDir
  try {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
      throw "Node.js / npm not found. Install Node.js LTS from https://nodejs.org then re-run this installer."
    }
    & npm install
    if ($LASTEXITCODE -ne 0) {
      throw "npm install failed (exit $LASTEXITCODE)."
    }
  } finally {
    Pop-Location
  }
}

function Install-Hub {
  param(
    [bool]$Desktop,
    [bool]$StartMenu,
    [bool]$Deps,
    [bool]$LaunchAfter
  )

  if (-not (Test-Path -LiteralPath $LauncherVbs)) {
    throw "Launcher missing: $LauncherVbs"
  }

  if ($Deps) {
    Install-NpmDeps
  }

  $icon = Ensure-AppIcon
  $paths = Get-ShortcutPaths
  $wscript = Join-Path $env:WINDIR "System32\wscript.exe"

  if ($Desktop) {
    New-Shortcut -LinkPath $paths.DesktopLnk -TargetPath $wscript `
      -Arguments "`"$LauncherVbs`"" -WorkDir $AppDir -IconPath $icon `
      -Description "Metroid Dread Archipelago Client Hub"
    Write-Host "Desktop shortcut: $($paths.DesktopLnk)"
  }

  if ($StartMenu) {
    New-Shortcut -LinkPath $paths.StartMenuLnk -TargetPath $wscript `
      -Arguments "`"$LauncherVbs`"" -WorkDir $AppDir -IconPath $icon `
      -Description "Metroid Dread Archipelago Client Hub"
    Write-Host "Start Menu shortcut: $($paths.StartMenuLnk)"

    # Uninstall entry in the same Start Menu folder
    $uninstallPs1 = Join-Path $AppDir "Install_Dread_Client_Hub.ps1"
    New-Shortcut -LinkPath $paths.UninstallLnk -TargetPath "powershell.exe" `
      -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$uninstallPs1`" -Uninstall" `
      -WorkDir $AppDir -IconPath $icon `
      -Description "Remove Dread Client Hub shortcuts"
    Write-Host "Start Menu uninstall: $($paths.UninstallLnk)"
  }

  # Remember install location for uninstall / repair
  $metaDir = Join-Path $env:LOCALAPPDATA "DreadClientHub"
  New-Item -ItemType Directory -Path $metaDir -Force | Out-Null
  @{
    appName   = $AppName
    appDir    = $AppDir
    repoRoot  = $RepoRoot
    installed = (Get-Date).ToString("o")
    desktop   = [bool]$Desktop
    startMenu = [bool]$StartMenu
  } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $metaDir "install.json") -Encoding UTF8

  Write-Host ""
  Write-Host "$AppName installed." -ForegroundColor Green

  if ($LaunchAfter) {
    Start-Process -FilePath $wscript -ArgumentList "`"$LauncherVbs`"" -WorkingDirectory $AppDir
  }
}

function Uninstall-Hub {
  $paths = Get-ShortcutPaths
  foreach ($p in @($paths.DesktopLnk, $paths.StartMenuLnk, $paths.UninstallLnk)) {
    if (Test-Path -LiteralPath $p) {
      Remove-Item -LiteralPath $p -Force
      Write-Host "Removed $p"
    }
  }
  if (Test-Path -LiteralPath $paths.StartMenuDir) {
    $left = Get-ChildItem -LiteralPath $paths.StartMenuDir -Force -ErrorAction SilentlyContinue
    if (-not $left -or $left.Count -eq 0) {
      Remove-Item -LiteralPath $paths.StartMenuDir -Force -Recurse -ErrorAction SilentlyContinue
    }
  }
  $meta = Join-Path $env:LOCALAPPDATA "DreadClientHub\install.json"
  if (Test-Path -LiteralPath $meta) {
    Remove-Item -LiteralPath $meta -Force -ErrorAction SilentlyContinue
  }
  Write-Host "Shortcuts removed. App files were left in place:" -ForegroundColor Yellow
  Write-Host "  $AppDir"
}

function Show-InstallerUi {
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing

  $form = New-Object System.Windows.Forms.Form
  $form.Text = "Install $AppName"
  $form.Size = New-Object System.Drawing.Size(460, 320)
  $form.StartPosition = "CenterScreen"
  $form.FormBorderStyle = "FixedDialog"
  $form.MaximizeBox = $false
  $form.MinimizeBox = $false
  $form.BackColor = [System.Drawing.Color]::FromArgb(7, 16, 22)
  $form.ForeColor = [System.Drawing.Color]::FromArgb(230, 242, 246)
  $form.Font = New-Object System.Drawing.Font("Segoe UI", 10)

  $title = New-Object System.Windows.Forms.Label
  $title.Text = $AppName
  $title.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 16)
  $title.ForeColor = [System.Drawing.Color]::FromArgb(62, 207, 191)
  $title.Location = New-Object System.Drawing.Point(24, 18)
  $title.AutoSize = $true
  $form.Controls.Add($title)

  $sub = New-Object System.Windows.Forms.Label
  $sub.Text = "Create shortcuts and prepare the Metroid Dread Archipelago hub."
  $sub.Location = New-Object System.Drawing.Point(26, 54)
  $sub.Size = New-Object System.Drawing.Size(400, 40)
  $sub.ForeColor = [System.Drawing.Color]::FromArgb(138, 167, 181)
  $form.Controls.Add($sub)

  $chkDesktop = New-Object System.Windows.Forms.CheckBox
  $chkDesktop.Text = "Create Desktop shortcut"
  $chkDesktop.Checked = $true
  $chkDesktop.Location = New-Object System.Drawing.Point(30, 110)
  $chkDesktop.AutoSize = $true
  $form.Controls.Add($chkDesktop)

  $chkStart = New-Object System.Windows.Forms.CheckBox
  $chkStart.Text = "Add to Start Menu"
  $chkStart.Checked = $true
  $chkStart.Location = New-Object System.Drawing.Point(30, 140)
  $chkStart.AutoSize = $true
  $form.Controls.Add($chkStart)

  $chkDeps = New-Object System.Windows.Forms.CheckBox
  $chkDeps.Text = "Install / update npm dependencies (recommended)"
  $chkDeps.Checked = $true
  $chkDeps.Location = New-Object System.Drawing.Point(30, 170)
  $chkDeps.AutoSize = $true
  $form.Controls.Add($chkDeps)

  $chkLaunch = New-Object System.Windows.Forms.CheckBox
  $chkLaunch.Text = "Launch Hub when finished"
  $chkLaunch.Checked = $true
  $chkLaunch.Location = New-Object System.Drawing.Point(30, 200)
  $chkLaunch.AutoSize = $true
  $form.Controls.Add($chkLaunch)

  $btnInstall = New-Object System.Windows.Forms.Button
  $btnInstall.Text = "Install"
  $btnInstall.Location = New-Object System.Drawing.Point(230, 240)
  $btnInstall.Size = New-Object System.Drawing.Size(90, 32)
  $btnInstall.BackColor = [System.Drawing.Color]::FromArgb(31, 143, 132)
  $btnInstall.ForeColor = [System.Drawing.Color]::FromArgb(4, 19, 15)
  $btnInstall.FlatStyle = "Flat"
  $form.Controls.Add($btnInstall)

  $btnCancel = New-Object System.Windows.Forms.Button
  $btnCancel.Text = "Cancel"
  $btnCancel.Location = New-Object System.Drawing.Point(330, 240)
  $btnCancel.Size = New-Object System.Drawing.Size(90, 32)
  $btnCancel.FlatStyle = "Flat"
  $btnCancel.BackColor = [System.Drawing.Color]::FromArgb(18, 36, 48)
  $btnCancel.ForeColor = $form.ForeColor
  $form.Controls.Add($btnCancel)

  $result = @{ ok = $false }

  $btnCancel.Add_Click({ $form.Close() })
  $btnInstall.Add_Click({
      $result.ok = $true
      $result.desktop = $chkDesktop.Checked
      $result.startMenu = $chkStart.Checked
      $result.deps = $chkDeps.Checked
      $result.launch = $chkLaunch.Checked
      $form.Close()
    })

  [void]$form.ShowDialog()
  return $result
}

try {
  if ($Uninstall) {
    if (-not $Silent) {
      Add-Type -AssemblyName System.Windows.Forms
      $confirm = [System.Windows.Forms.MessageBox]::Show(
        "Remove $AppName Desktop and Start Menu shortcuts?",
        "Uninstall $AppName",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
      )
      if ($confirm -ne [System.Windows.Forms.DialogResult]::Yes) { exit 0 }
    }
    Uninstall-Hub
    if (-not $Silent) {
      Add-Type -AssemblyName System.Windows.Forms
      [System.Windows.Forms.MessageBox]::Show(
        "Shortcuts removed.",
        $AppName,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
      ) | Out-Null
    }
    exit 0
  }

  if ($Silent) {
    Install-Hub -Desktop:(-not $NoDesktop) -StartMenu:(-not $NoStartMenu) `
      -Deps:(-not $SkipDeps) -LaunchAfter:$false
    exit 0
  }

  $choice = Show-InstallerUi
  if (-not $choice.ok) { exit 0 }

  try {
    Install-Hub -Desktop:([bool]$choice.desktop) -StartMenu:([bool]$choice.startMenu) `
      -Deps:([bool]$choice.deps) -LaunchAfter:([bool]$choice.launch)
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
      "$AppName is ready.`n`nDesktop and/or Start Menu shortcuts were created.",
      $AppName,
      [System.Windows.Forms.MessageBoxButtons]::OK,
      [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
  } catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
      $_.Exception.Message,
      "Install failed",
      [System.Windows.Forms.MessageBoxButtons]::OK,
      [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
  }
} catch {
  Write-Host $_.Exception.Message -ForegroundColor Red
  if (-not $Silent) { Read-Host "Press Enter to close" | Out-Null }
  exit 1
}
