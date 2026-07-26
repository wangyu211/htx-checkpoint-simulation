[CmdletBinding()]
param(
    [string]$Destination = "models\yolox_s.onnx"
)

$ErrorActionPreference = "Stop"

$sourceUrl = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx"
$expectedSha256 = "C5C2D13E59AE883E6AF3B45DAEA64AF4833A4951C92D116EC270D9DDBE998063"
$expectedBytes = 35858002

$destinationPath = [System.IO.Path]::GetFullPath(
    (Join-Path -Path (Get-Location) -ChildPath $Destination)
)
$destinationDirectory = Split-Path -Parent $destinationPath
$temporaryPath = "$destinationPath.download"

New-Item -ItemType Directory -Force -Path $destinationDirectory | Out-Null

if (Test-Path -LiteralPath $destinationPath) {
    $existingHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destinationPath).Hash
    $existingLength = (Get-Item -LiteralPath $destinationPath).Length
    if ($existingHash -eq $expectedSha256 -and $existingLength -eq $expectedBytes) {
        Write-Host "Verified existing model: $destinationPath"
        exit 0
    }
    throw "Destination exists but does not match the pinned size and SHA-256: $destinationPath"
}

Invoke-WebRequest -Uri $sourceUrl -OutFile $temporaryPath

$downloadedLength = (Get-Item -LiteralPath $temporaryPath).Length
$downloadedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $temporaryPath).Hash
if ($downloadedLength -ne $expectedBytes -or $downloadedHash -ne $expectedSha256) {
    Remove-Item -LiteralPath $temporaryPath
    throw "Downloaded model failed integrity verification."
}

Move-Item -LiteralPath $temporaryPath -Destination $destinationPath
Write-Host "Downloaded and verified: $destinationPath"
Write-Host "SHA-256: $downloadedHash"
