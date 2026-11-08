# Stops only this plugin's watcher (matches the script name, never other Python programs).
$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like '*clipboard-watcher.pyw*'
}
if (-not $procs) { Write-Host 'The watcher is not running.'; exit 0 }
$procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host 'The watcher was stopped.'
