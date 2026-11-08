# Adds (default) or removes (-Remove) a Startup-folder shortcut so the watcher starts at sign-in.
param([switch]$Remove)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Link = Join-Path ([Environment]::GetFolderPath('Startup')) 'Screenshot Context Watcher.lnk'

if ($Remove) {
    Remove-Item $Link -ErrorAction SilentlyContinue
    Write-Host 'Auto-start removed.'
    exit 0
}

$pythonw = Join-Path $Root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) { Write-Host 'Not installed yet. Run install.cmd first.' -ForegroundColor Red; exit 1 }

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($Link)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + (Join-Path $Root 'clipboard-watcher.pyw') + '"'
$shortcut.WorkingDirectory = $Root
$shortcut.WindowStyle = 7
$shortcut.Description = 'Screenshot Context watcher'
$shortcut.Save()
Write-Host "Auto-start enabled: $Link"
