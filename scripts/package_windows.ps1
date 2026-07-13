[CmdletBinding()]
param(
    [string]$BundlePath,
    [string]$ReleaseDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if ([string]::IsNullOrWhiteSpace($BundlePath)) {
    $BundlePath = Join-Path $Root "dist\MXHVideoEditor"
}
if ([string]::IsNullOrWhiteSpace($ReleaseDirectory)) {
    $ReleaseDirectory = Join-Path $Root "release"
}
$BundlePath = (Resolve-Path -LiteralPath $BundlePath).Path

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Không tìm thấy Python trong .venv; chưa thể đọc phiên bản ứng dụng."
}
$Version = (& $Python -c "import mxh_video_editor; print(mxh_video_editor.__version__)").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Version)) {
    throw "Không đọc được phiên bản MXH Video Editor."
}

$PackageName = "MXHVideoEditor-$Version-Windows-x64"
$StageRoot = Join-Path $Root "build\package-stage"
$StageApplication = Join-Path $StageRoot "MXHVideoEditor"
$Archive = Join-Path $ReleaseDirectory "$PackageName.zip"
$Checksum = "$Archive.sha256"

if (Test-Path -LiteralPath $StageRoot) {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $StageApplication | Out-Null
Copy-Item -Path (Join-Path $BundlePath "*") -Destination $StageApplication -Recurse -Force

$Documentation = @(
    (Join-Path $Root "README.md"),
    (Join-Path $Root "RELEASE_NOTES_VIDEO_EDITOR_V$Version.md"),
    (Join-Path $Root "THIRD_PARTY_NOTICES.md"),
    (Join-Path $Root "docs\INSTALL_WINDOWS.md")
)
foreach ($Document in $Documentation) {
    if (Test-Path -LiteralPath $Document -PathType Leaf) {
        Copy-Item -LiteralPath $Document -Destination $StageApplication -Force
    }
}

$LicenseStage = Join-Path $StageApplication "licenses\ffmpeg"
$FfmpegNotices = Join-Path $Root "build\vendor\ffmpeg"
if (Test-Path -LiteralPath $FfmpegNotices -PathType Container) {
    New-Item -ItemType Directory -Force -Path $LicenseStage | Out-Null
    Copy-Item -Path (Join-Path $FfmpegNotices "*") `
        -Destination $LicenseStage -Recurse -Force
}

if (Test-Path -LiteralPath $ReleaseDirectory) {
    Remove-Item -LiteralPath $ReleaseDirectory -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $ReleaseDirectory | Out-Null
Compress-Archive -Path (Join-Path $StageRoot "*") `
    -DestinationPath $Archive -CompressionLevel Optimal -Force

$ArchiveSha256 = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
"$ArchiveSha256  $([System.IO.Path]::GetFileName($Archive))" |
    Set-Content -LiteralPath $Checksum -Encoding ascii

Write-Host "Gói Windows: $Archive"
Write-Host "SHA-256: $ArchiveSha256"
