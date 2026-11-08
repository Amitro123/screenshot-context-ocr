# Screenshot Context - one-shot installer (Windows, no admin needed except for the Tesseract installer prompt).
# Safe to re-run: every step is skipped when already done.
#   -Startup   also start the watcher automatically at every Windows sign-in
#   -NoStart   install only, do not launch the watcher now
param([switch]$Startup, [switch]$NoStart)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Step($m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Good($m) { Write-Host "    OK: $m" -ForegroundColor Green }
function Fail($m) { Write-Host ""; Write-Host "FAILED: $m" -ForegroundColor Red; exit 1 }

function Retry([scriptblock]$Action, [string]$What, [int]$Times = 3) {
    for ($i = 1; $i -le $Times; $i++) {
        try { & $Action; return } catch {
            if ($i -eq $Times) { throw }
            Write-Host "    $What failed (attempt $i/$Times): $($_.Exception.Message). Retrying..." -ForegroundColor Yellow
            Start-Sleep -Seconds 3
        }
    }
}

function Find-Tesseract {
    $candidates = @(
        (Get-Command tesseract -ErrorAction SilentlyContinue | ForEach-Object { $_.Source }),
        "$env:ProgramFiles\Tesseract-OCR\tesseract.exe",
        "${env:ProgramFiles(x86)}\Tesseract-OCR\tesseract.exe",
        "$env:LOCALAPPDATA\Programs\Tesseract-OCR\tesseract.exe"
    )
    $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

# 1. Python ------------------------------------------------------------------
Step 'Checking Python 3.10+'
$havePy = Get-Command py -ErrorAction SilentlyContinue
if (-not $havePy) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host '    Python not found - installing Python 3.12 with winget...'
        winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
        Fail 'Python was just installed. Close this window, open a new one and run install.cmd again.'
    }
    Fail 'Python 3 is not installed. Install it from https://www.python.org/downloads/ (tick "Add to PATH"), then run install.cmd again.'
}
Good ((& py -3 --version) 2>&1)

# 2. Virtual environment + Pillow -------------------------------------------------
Step 'Preparing the Python environment'
$venvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) { & py -3 -m venv .venv; if ($LASTEXITCODE) { Fail 'Could not create the virtual environment.' } }
Retry { & $venvPython -m pip install --disable-pip-version-check -q -r requirements.txt; if ($LASTEXITCODE) { throw 'pip install failed' } } 'pip install'
Good 'Pillow installed'

# 3. Tesseract ----------------------------------------------------------------
Step 'Checking Tesseract OCR'
$tess = Find-Tesseract
if (-not $tess) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail 'Tesseract is missing and winget is not available. Install it from https://github.com/UB-Mannheim/tesseract/wiki and run install.cmd again.'
    }
    Write-Host '    Installing Tesseract (accept the Windows permission prompt if it appears)...'
    winget install --id UB-Mannheim.TesseractOCR -e --silent --accept-package-agreements --accept-source-agreements
    $tess = Find-Tesseract
    if (-not $tess) { Fail 'Tesseract installation did not complete. Install it manually from https://github.com/UB-Mannheim/tesseract/wiki' }
}
Good $tess

# 4. Language data (English + Hebrew "best") in a user-writable folder --------------------
Step 'Preparing Hebrew and English language data'
$tessdata = Join-Path $env:USERPROFILE 'tessdata'
New-Item -ItemType Directory -Force -Path $tessdata | Out-Null
$installedData = Join-Path (Split-Path -Parent $tess) 'tessdata'
foreach ($name in 'eng.traineddata', 'osd.traineddata') {
    $src = Join-Path $installedData $name
    $dst = Join-Path $tessdata $name
    if ((Test-Path $src) -and -not (Test-Path $dst)) { Copy-Item $src $dst }
}
$heb = Join-Path $tessdata 'heb.traineddata'
$hebOk = (Test-Path $heb) -and ((Get-Item $heb).Length -gt 1MB)
if (-not $hebOk) {
    Retry {
        Invoke-WebRequest -UseBasicParsing 'https://github.com/tesseract-ocr/tessdata_best/raw/main/heb.traineddata' -OutFile $heb
        if ((Get-Item $heb).Length -lt 1MB) { throw 'downloaded file is too small' }
    } 'Hebrew model download'
}
Good "language data in $tessdata"

# 5. Verify ---------------------------------------------------------------------
Step 'Verifying the installation'
& $venvPython (Join-Path $Root 'scripts\ocr.py') --check
if ($LASTEXITCODE) { Fail 'Self-check failed. See the message above.' }

# 6. Start / auto-start -------------------------------------------------------------
if ($Startup) {
    Step 'Enabling start with Windows'
    & (Join-Path $Root 'scripts\startup.ps1')
}
if (-not $NoStart) {
    Step 'Starting the watcher'
    $pythonw = Join-Path $Root '.venv\Scripts\pythonw.exe'
    Start-Process -FilePath $pythonw -ArgumentList ('"' + (Join-Path $Root 'clipboard-watcher.pyw') + '"') -WorkingDirectory $Root
    Good 'Watcher is running. A small "watcher is active" popup should appear at the bottom-right of the screen.'
}

Write-Host ""
Write-Host "Done. Take a screenshot with Win+Shift+S and answer the popup." -ForegroundColor Green
