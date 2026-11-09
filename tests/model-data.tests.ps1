# No Pester dependency: test actual helper with a local fake downloader.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\scripts\model-data.ps1')
$testDir = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $testDir | Out-Null
try {
    $source = Join-Path $testDir 'good.bin'
    $destination = Join-Path $testDir 'heb.traineddata'
    [IO.File]::WriteAllText($source, 'verified model fixture')
    $script:hash = (Get-FileHash $source -Algorithm SHA256).Hash
    function Get-HebrewModelSpec { @{ Url = 'https://invalid.test/model'; Sha256 = $script:hash } }
    $script:mode = 'corrupt'
    $script:downloads = 0
    function Invoke-WebRequest($Uri, $OutFile, [switch]$UseBasicParsing) {
        $script:downloads++
        if ($script:mode -eq 'good') { Copy-Item $source $OutFile }
        else {
            [IO.File]::WriteAllText($OutFile, 'partial download')
            if ($script:mode -eq 'interrupt') { throw 'network interrupted' }
        }
    }
    foreach ($mode in 'corrupt', 'interrupt') {
        $script:mode = $mode
        [IO.File]::WriteAllText($destination, 'existing model')
        $failed = $false
        try { Install-HebrewModel $destination } catch { $failed = $true }
        if (-not $failed) { throw "Expected $mode failure" }
        if ([IO.File]::ReadAllText($destination) -ne 'existing model') { throw 'Existing model was damaged' }
        if (Get-ChildItem $testDir -Filter '*.download') { throw 'Temporary download leaked' }
    }
    $script:mode = 'good'
    Install-HebrewModel $destination
    if (-not (Test-ModelHash $destination $script:hash)) { throw 'Verified replacement failed' }
    $count = $script:downloads
    Install-HebrewModel $destination
    if ($script:downloads -ne $count) { throw 'Verified model downloaded again' }
    Remove-Item $destination
    Install-HebrewModel $destination
    if (-not (Test-ModelHash $destination $script:hash)) { throw 'Fresh installation failed' }
    Write-Host 'PASS: corrupt/interrupted downloads, verified replacement, idempotence, fresh install'
} finally {
    Remove-Item $testDir -Recurse -Force
}
