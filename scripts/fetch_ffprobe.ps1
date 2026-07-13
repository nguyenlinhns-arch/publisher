[CmdletBinding()]
param(
    [string]$Version = "8.1.2",
    [string]$DownloadUrl = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip",
    [string]$ExpectedSha256 = "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Root = Split-Path -Parent $PSScriptRoot
$BinDirectory = Join-Path $Root "bin"
$Destination = Join-Path $BinDirectory "ffprobe.exe"
$FfmpegDestination = Join-Path $BinDirectory "ffmpeg.exe"
$VendorDirectory = Join-Path $Root "build\vendor\ffmpeg"
$TemporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) `
    ("mxh-publisher-ffmpeg-" + [guid]::NewGuid().ToString("N"))
$Archive = Join-Path $TemporaryRoot "ffmpeg.zip"
$Extracted = Join-Path $TemporaryRoot "extracted"

function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step thất bại với mã thoát $LASTEXITCODE."
    }
}

New-Item -ItemType Directory -Force -Path $TemporaryRoot, $Extracted | Out-Null
try {
    Write-Host "Đang tải FFmpeg $Version từ gyan.dev..."
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $Archive

    $ActualSha256 = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "FFmpeg SHA-256 không khớp. Nhận $ActualSha256; cần $ExpectedSha256."
    }

    Expand-Archive -LiteralPath $Archive -DestinationPath $Extracted -Force
    $Probe = Get-ChildItem -LiteralPath $Extracted -Recurse -Filter "ffprobe.exe" -File |
        Select-Object -First 1
    if ($null -eq $Probe) {
        throw "Archive FFmpeg không chứa ffprobe.exe."
    }
    $Ffmpeg = Get-ChildItem -LiteralPath $Extracted -Recurse -Filter "ffmpeg.exe" -File |
        Select-Object -First 1
    if ($null -eq $Ffmpeg) {
        throw "Archive FFmpeg không chứa ffmpeg.exe."
    }

    & $Probe.FullName -version
    Assert-NativeSuccess "Chạy ffprobe vừa tải"
    & $Ffmpeg.FullName -version
    Assert-NativeSuccess "Chạy ffmpeg vừa tải"

    New-Item -ItemType Directory -Force -Path $BinDirectory | Out-Null
    Copy-Item -LiteralPath $Probe.FullName -Destination $Destination -Force
    Copy-Item -LiteralPath $Ffmpeg.FullName -Destination $FfmpegDestination -Force

    if (Test-Path -LiteralPath $VendorDirectory) {
        Remove-Item -LiteralPath $VendorDirectory -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $VendorDirectory | Out-Null

    $CandidateFiles = Get-ChildItem -LiteralPath $Extracted -Recurse -File
    $License = $CandidateFiles |
        Where-Object { $_.Name -match '^(LICENSE|COPYING)(\..*)?$' } |
        Sort-Object { $_.FullName.Length } |
        Select-Object -First 1
    $Readme = $CandidateFiles |
        Where-Object { $_.Name -match '^README(\..*)?$' } |
        Sort-Object { $_.FullName.Length } |
        Select-Object -First 1
    if ($null -ne $License) {
        Copy-Item -LiteralPath $License.FullName `
            -Destination (Join-Path $VendorDirectory "FFmpeg-LICENSE$($License.Extension)") -Force
    }
    if ($null -ne $Readme) {
        Copy-Item -LiteralPath $Readme.FullName `
            -Destination (Join-Path $VendorDirectory "FFmpeg-README$($Readme.Extension)") -Force
    }

    $ProbeSha256 = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    $FfmpegSha256 = (Get-FileHash -LiteralPath $FfmpegDestination -Algorithm SHA256).Hash.ToLowerInvariant()
    @(
        "FFmpeg build version: $Version"
        "Download URL: $DownloadUrl"
        "Archive SHA-256: $ExpectedSha256"
        "Bundled ffprobe.exe SHA-256: $ProbeSha256"
        "Bundled ffmpeg.exe SHA-256: $FfmpegSha256"
        "Provider: Gyan Doshi (gyan.dev), linked by ffmpeg.org"
        "License reported by provider: GPLv3"
    ) | Set-Content -LiteralPath (Join-Path $VendorDirectory "SOURCE.txt") -Encoding utf8

    Write-Host "Đã xác minh và lưu ffprobe: $Destination"
    Write-Host "Đã xác minh và lưu ffmpeg: $FfmpegDestination"
} finally {
    if (Test-Path -LiteralPath $TemporaryRoot) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
}
