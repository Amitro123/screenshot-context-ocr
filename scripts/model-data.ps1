# One pinned upstream artifact shared by setup and doctor.
function Get-HebrewModelSpec {
    @{
        Url = 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/e12c65a915945e4c28e237a9b52bc4a8f39a0cec/heb.traineddata'
        Sha256 = 'dbaa827aea6bc21215638447f17783a1004987c2d0bf5573d111fee397abdae5'
    }
}

function Test-ModelHash([string]$Path, [string]$Sha256) {
    (Test-Path -LiteralPath $Path -PathType Leaf) -and
        ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -eq $Sha256)
}

function Install-HebrewModel([string]$Destination) {
    $spec = Get-HebrewModelSpec
    if (Test-ModelHash $Destination $spec.Sha256) { return }
    # Same directory/volume: retain the existing model until the replacement is verified.
    $temp = $Destination + '.' + [Guid]::NewGuid().ToString('N') + '.download'
    try {
        Invoke-WebRequest -UseBasicParsing $spec.Url -OutFile $temp
        if (-not (Test-ModelHash $temp $spec.Sha256)) { throw 'Hebrew model checksum mismatch' }
        if (Test-Path -LiteralPath $Destination) {
            [IO.File]::Replace($temp, $Destination, [NullString]::Value)
        } else {
            [IO.File]::Move($temp, $Destination)
        }
    } finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
    }
}
