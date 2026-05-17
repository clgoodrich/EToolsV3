# Creates a desktop shortcut to launch ETools (silent mode).
# Right-click this file in Explorer -> Run with PowerShell, or run from a terminal.

$ErrorActionPreference = 'Stop'

$repo     = Split-Path -Parent $MyInvocation.MyCommand.Definition
$target   = Join-Path $repo 'Launch ETools (Silent).vbs'
$icon     = Join-Path $repo 'data\favicon.ico'
$desktop  = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop 'ETools.lnk'

if (-not (Test-Path $target)) {
    Write-Error "Launcher not found: $target"
}

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath        = 'wscript.exe'
$shortcut.Arguments         = '"' + $target + '"'
$shortcut.WorkingDirectory  = $repo
$shortcut.WindowStyle       = 1
$shortcut.Description       = 'ETools - DOGM Directional Survey & WCR'
if (Test-Path $icon) { $shortcut.IconLocation = $icon }
$shortcut.Save()

Write-Host "Desktop shortcut created: $linkPath" -ForegroundColor Green
Write-Host "Double-click 'ETools' on your desktop to launch the app."
