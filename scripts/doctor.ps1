# Health check: prints what is installed, what is missing and the single next step.
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
. (Join-Path $Root 'scripts\model-data.ps1')
$bad = 0
function Row($ok, $name, $detail) {
    if ($ok) { Write-Host ("[ OK ]   {0,-22} {1}" -f $name, $detail) -ForegroundColor Green }
    else     { Write-Host ("[MISSING] {0,-21} {1}" -f $name, $detail) -ForegroundColor Red; $script:bad++ }
}

$py = Get-Command py -ErrorAction SilentlyContinue
Row ([bool]$py) 'Python 3' ($(if ($py) { (& py -3 --version) 2>&1 } else { 'install Python 3.10+ from python.org' }))

$venv = Join-Path $Root '.venv\Scripts\python.exe'
$haveVenv = Test-Path $venv
Row $haveVenv 'Virtual environment' ($(if ($haveVenv) { '.venv' } else { 'run install.cmd' }))

if ($haveVenv) {
    & $venv -c "import PIL" 2>$null
    Row ($LASTEXITCODE -eq 0) 'Pillow' ($(if ($LASTEXITCODE -eq 0) { 'importable' } else { 'run install.cmd' }))
}

$tess = $null
if ($haveVenv) {
    $found = & $venv (Join-Path $Root 'scripts\ocr.py') --find-engine 2>$null
    if ($LASTEXITCODE -eq 0) { $tess = $found }
}
Row ([bool]$tess) 'Tesseract' ($(if ($tess) { $tess } else { 'run install.cmd' }))

$heb = Join-Path $env:USERPROFILE 'tessdata\heb.traineddata'
$hebOk = Test-ModelHash $heb (Get-HebrewModelSpec).Sha256
$hebHint = if (Test-Path $heb) { 'unverified or damaged model - run install.cmd to repair' } else { 'run install.cmd' }
Row $hebOk 'Hebrew language data' ($(if ($hebOk) { $heb } else { $hebHint }))

if ($haveVenv -and $tess) {
    $out = & $venv (Join-Path $Root 'scripts\ocr.py') --check 2>&1
    $pass = ($LASTEXITCODE -eq 0)
    Row $pass 'OCR self-check' (($out | Select-Object -First 1) -join ' ')
}

$running = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like '*clipboard-watcher.pyw*' }
Row ([bool]$running) 'Watcher running' ($(if ($running) { 'yes' } else { 'start it with start-watcher.cmd' }))

$link = Join-Path ([Environment]::GetFolderPath('Startup')) 'Screenshot Context Watcher.lnk'
Write-Host ("[ INFO ] {0,-22} {1}" -f 'Start with Windows', ($(if (Test-Path $link) { 'enabled' } else { 'disabled (optional: add-to-startup.cmd)' }))) -ForegroundColor DarkGray

$log = Join-Path $Root 'watcher.log'
if (Test-Path $log) {
    Write-Host "`nLast watcher events:" -ForegroundColor DarkGray
    Get-Content $log -Tail 5 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
}

Write-Host ""
if ($bad -eq 0) { Write-Host 'Everything looks good.' -ForegroundColor Green; exit 0 }
Write-Host "$bad item(s) missing. Next step: run install.cmd (safe to repeat)." -ForegroundColor Yellow
exit 1
