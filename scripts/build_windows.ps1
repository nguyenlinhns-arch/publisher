[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipTests,
    [switch]$SkipQualityChecks
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Ffprobe = Join-Path $Root "bin\ffprobe.exe"
$DistPath = Join-Path $Root "dist"
$WorkPath = Join-Path $Root "build\pyinstaller"
$SpecPath = Join-Path $Root "build\pyinstaller-spec"
$EntryPoint = Join-Path $Root "src\mxh_publisher\__main__.py"

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

& $Ffprobe -version
Assert-NativeSuccess "Kiểm tra ffprobe"

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
        & $Python -m ruff check (Join-Path $Root "src") (Join-Path $Root "tests")
        Assert-NativeSuccess "Ruff"
        & $Python -m mypy (Join-Path $Root "src")
        Assert-NativeSuccess "Mypy"
        & $Python -m compileall -q (Join-Path $Root "src")
        Assert-NativeSuccess "Compileall"
    }

    New-Item -ItemType Directory -Force -Path $WorkPath, $SpecPath | Out-Null
    $Arguments = @(
        "--noconfirm",
        "--clean",
        "--onedir",
        "--noupx",
        "--name", "MXHPublisher",
        "--distpath", $DistPath,
        "--workpath", $WorkPath,
        "--specpath", $SpecPath,
        "--collect-all", "playwright",
        "--collect-all", "tzdata",
        "--paths", (Join-Path $Root "src"),
        "--add-binary", "$Ffprobe;bin",
        $EntryPoint
    )
    & $Python -m PyInstaller @Arguments
    Assert-NativeSuccess "PyInstaller"
} finally {
    Pop-Location
}

$Executable = Join-Path $DistPath "MXHPublisher\MXHPublisher.exe"
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "PyInstaller không tạo được $Executable."
}
$BundledFfprobe = Get-ChildItem (Join-Path $DistPath "MXHPublisher") `
    -Recurse -Filter "ffprobe.exe" -File | Select-Object -First 1
if ($null -eq $BundledFfprobe) {
    throw "Bản onedir không chứa ffprobe.exe."
}

Write-Host "Build hoàn tất: $Executable"
Write-Host "ffprobe đóng gói: $($BundledFfprobe.FullName)"
