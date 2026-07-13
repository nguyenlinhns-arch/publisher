[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipTests,
    [switch]$SkipQualityChecks
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Ffprobe = Join-Path $Root "bin\ffprobe.exe"
$Ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
$DefaultFrame = Join-Path $Root "assets\nen.png"
$IntroSound = Join-Path $Root "assets\sound.mp3"
$FontsDirectory = Join-Path $Root "assets\fonts"
$DistPath = Join-Path $Root "dist"
$WorkPath = Join-Path $Root "build\pyinstaller"
$SpecPath = Join-Path $Root "build\pyinstaller-spec"
$EntryPoint = Join-Path $Root "src\mxh_video_editor\__main__.py"

function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step thất bại với mã thoát $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $PyLauncher) {
        & $PyLauncher.Source -3.12 -m venv $Venv
        Assert-NativeSuccess "Tạo môi trường Python 3.12"
    } else {
        $SystemPython = Get-Command python -ErrorAction Stop
        & $SystemPython.Source -m venv $Venv
        Assert-NativeSuccess "Tạo môi trường Python"
    }
}

if (-not (Test-Path -LiteralPath $Ffprobe -PathType Leaf)) {
    throw "Thiếu bin\ffprobe.exe. Hãy chạy scripts\fetch_ffprobe.ps1 trước khi build."
}
if (-not (Test-Path -LiteralPath $Ffmpeg -PathType Leaf)) {
    throw "Thiếu bin\ffmpeg.exe. Hãy chạy scripts\fetch_ffprobe.ps1 trước khi build."
}
if (-not (Test-Path -LiteralPath $DefaultFrame -PathType Leaf)) {
    throw "Thiếu assets\nen.png — khung nền mặc định của dự án."
}
if (-not (Test-Path -LiteralPath $IntroSound -PathType Leaf)) {
    throw "Thiếu assets\sound.mp3 — âm thanh mở đầu mặc định."
}
if (-not (Test-Path -LiteralPath $FontsDirectory -PathType Container)) {
    throw "Thiếu thư mục font assets\fonts."
}

& $Ffprobe -version
Assert-NativeSuccess "Kiểm tra ffprobe"
& $Ffmpeg -version
Assert-NativeSuccess "Kiểm tra ffmpeg"

Push-Location $Root
try {
    if (-not $SkipInstall) {
        & $Python -m pip install --upgrade pip
        Assert-NativeSuccess "Nâng cấp pip"
        & $Python -m pip install -e "${Root}[dev]"
        Assert-NativeSuccess "Cài dependency"
    }

    if (-not $SkipTests) {
        & $Python -m pytest -q
        Assert-NativeSuccess "Pytest"
    }

    if (-not $SkipQualityChecks) {
        & $Python -m ruff check `
            (Join-Path $Root "src\mxh_video_editor") `
            (Join-Path $Root "src\mxh_publisher\services\media.py") `
            (Join-Path $Root "editor_tests")
        Assert-NativeSuccess "Ruff"
        & $Python -m mypy `
            (Join-Path $Root "src\mxh_video_editor") `
            (Join-Path $Root "src\mxh_publisher\services\media.py")
        Assert-NativeSuccess "Mypy"
        & $Python -m compileall -q `
            (Join-Path $Root "src\mxh_video_editor") `
            (Join-Path $Root "src\mxh_publisher\services\media.py")
        Assert-NativeSuccess "Compileall"
    }

    New-Item -ItemType Directory -Force -Path $WorkPath, $SpecPath | Out-Null
    $Arguments = @(
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--noupx",
        "--name", "MXHVideoEditor",
        "--distpath", $DistPath,
        "--workpath", $WorkPath,
        "--specpath", $SpecPath,
        "--paths", (Join-Path $Root "src"),
        "--add-binary", "$Ffprobe;bin",
        "--add-binary", "$Ffmpeg;bin",
        "--add-data", "$DefaultFrame;assets",
        "--add-data", "$IntroSound;assets",
        "--add-data", "$FontsDirectory;assets\fonts",
        $EntryPoint
    )
    & $Python -m PyInstaller @Arguments
    Assert-NativeSuccess "PyInstaller"
} finally {
    Pop-Location
}

$Executable = Join-Path $DistPath "MXHVideoEditor\MXHVideoEditor.exe"
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "PyInstaller không tạo được $Executable."
}
$BundledFfprobe = Get-ChildItem (Join-Path $DistPath "MXHVideoEditor") `
    -Recurse -Filter "ffprobe.exe" -File | Select-Object -First 1
if ($null -eq $BundledFfprobe) {
    throw "Bản onedir không chứa ffprobe.exe."
}
$BundledFfmpeg = Get-ChildItem (Join-Path $DistPath "MXHVideoEditor") `
    -Recurse -Filter "ffmpeg.exe" -File | Select-Object -First 1
if ($null -eq $BundledFfmpeg) {
    throw "Bản onedir không chứa ffmpeg.exe."
}
$BundledFrame = Get-ChildItem (Join-Path $DistPath "MXHVideoEditor") `
    -Recurse -Filter "nen.png" -File | Select-Object -First 1
if ($null -eq $BundledFrame) {
    throw "Bản onedir không chứa khung nền assets\nen.png."
}

Write-Host "Build hoàn tất: $Executable"
Write-Host "ffprobe đóng gói: $($BundledFfprobe.FullName)"
Write-Host "ffmpeg đóng gói: $($BundledFfmpeg.FullName)"
Write-Host "Khung nền đóng gói: $($BundledFrame.FullName)"
