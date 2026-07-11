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
    $BundlePath = Join-Path $Root "dist\MXHPublisher"
}
if ([string]::IsNullOrWhiteSpace($ReleaseDirectory)) {
    $ReleaseDirectory = Join-Path $Root "release"
}
$BundlePath = (Resolve-Path -LiteralPath $BundlePath).Path

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Không tìm thấy Python trong .venv; chưa thể đọc phiên bản ứng dụng."
}
$Version = (& $Python -c "import mxh_publisher; print(mxh_publisher.__version__)").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Version)) {
    throw "Không đọc được phiên bản MXH Publisher."
}

$PackageName = "MXHPublisher-$Version-Windows-x64"
$StageRoot = Join-Path $Root "build\package-stage"
$StageApplication = Join-Path $StageRoot "MXHPublisher"
$Archive = Join-Path $ReleaseDirectory "$PackageName.zip"
$Checksum = "$Archive.sha256"

if (Test-Path -LiteralPath $StageRoot) {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $StageApplication | Out-Null
Copy-Item -Path (Join-Path $BundlePath "*") -Destination $StageApplication -Recurse -Force

$Documentation = @(
    (Join-Path $Root "README.md"),
    (Join-Path $Root "RELEASE_NOTES_V$Version.md"),
    (Join-Path $Root "THIRD_PARTY_NOTICES.md"),
    (Join-Path $Root "docs\INSTALL_WINDOWS.md")
)
foreach ($Document in $Documentation) {
    if (Test-Path -LiteralPath $Document -PathType Leaf) {
        Copy-Item -LiteralPath $Document -Destination $StageApplication -Force
    }
}
$DocumentationSource = Join-Path $Root "docs"
if (Test-Path -LiteralPath $DocumentationSource -PathType Container) {
    $DocumentationStage = Join-Path $StageApplication "docs"
    New-Item -ItemType Directory -Force -Path $DocumentationStage | Out-Null
    Copy-Item -Path (Join-Path $DocumentationSource "*") `
        -Destination $DocumentationStage -Recurse -Force
}

$LicenseStage = Join-Path $StageApplication "licenses\ffmpeg"
$FfmpegNotices = Join-Path $Root "build\vendor\ffmpeg"
if (Test-Path -LiteralPath $FfmpegNotices -PathType Container) {
    New-Item -ItemType Directory -Force -Path $LicenseStage | Out-Null
    Copy-Item -Path (Join-Path $FfmpegNotices "*") `
        -Destination $LicenseStage -Recurse -Force
}

$TaskScripts = @(
    (Join-Path $Root "scripts\install_verification_task.ps1"),
    (Join-Path $Root "scripts\uninstall_verification_task.ps1")
)
$ToolsStage = Join-Path $StageApplication "tools"
foreach ($TaskScript in $TaskScripts) {
    if (Test-Path -LiteralPath $TaskScript -PathType Leaf) {
        New-Item -ItemType Directory -Force -Path $ToolsStage | Out-Null
        Copy-Item -LiteralPath $TaskScript -Destination $ToolsStage -Force
    }
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
