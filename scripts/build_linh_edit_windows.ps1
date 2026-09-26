[CmdletBinding()]
param(
    [switch]$SkipFetch,
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv-linh-edit"
$Python = Join-Path $Venv "Scripts\python.exe"
$Ffprobe = Join-Path $Root "bin\ffprobe.exe"
$Ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
$Fonts = Join-Path $Root "assets\fonts"
$Entry = Join-Path $Root "linh_edit_launcher.py"
$Dist = Join-Path $Root "dist"
$Work = Join-Path $Root "build\linh-edit-pyinstaller"
$Spec = Join-Path $Root "build\linh-edit-spec"

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

if ((-not $SkipFetch) -and ((-not (Test-Path -LiteralPath $Ffmpeg -PathType Leaf)) -or (-not (Test-Path -LiteralPath $Ffprobe -PathType Leaf)))) {
    & (Join-Path $PSScriptRoot "fetch_ffprobe.ps1")
    Assert-NativeSuccess "Tải FFmpeg đã khóa checksum"
}

foreach ($Required in @($Ffmpeg, $Ffprobe, $Fonts, $Entry)) {
    if (-not (Test-Path -LiteralPath $Required)) {
        throw "Thiếu thành phần build: $Required"
    }
}

& $Ffmpeg -version
Assert-NativeSuccess "Kiểm tra ffmpeg"
& $Ffprobe -version
Assert-NativeSuccess "Kiểm tra ffprobe"

Push-Location $Root
try {
    & $Python -m pip install --upgrade pip
    Assert-NativeSuccess "Nâng cấp pip"
    & $Python -m pip install "pyinstaller==6.21.0" "pytest==9.1.1"
    Assert-NativeSuccess "Cài công cụ build"

    if (-not $SkipTests) {
        $env:PYTHONPATH = $Root
        & $Python -m pytest -q (Join-Path $Root "linh_edit\tests")
        Assert-NativeSuccess "Pytest Linh Edit"
        & $Python -m compileall -q (Join-Path $Root "linh_edit")
        Assert-NativeSuccess "Compileall Linh Edit"
        & $Python -m linh_edit doctor
        Assert-NativeSuccess "Doctor source"
    }

    New-Item -ItemType Directory -Force -Path $Work, $Spec, $Dist | Out-Null

    $Arguments = @(
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--noupx",
        "--name", "LinhEdit",
        "--distpath", $Dist,
        "--workpath", $Work,
        "--specpath", $Spec,
        "--paths", $Root,
        "--add-binary", "$Ffprobe;bin",
        "--add-binary", "$Ffmpeg;bin",
        "--add-data", "$Fonts;assets\fonts",
        $Entry
    )
    & $Python -m PyInstaller @Arguments
    Assert-NativeSuccess "PyInstaller Linh Edit"
} finally {
    Pop-Location
}

$AppDir = Join-Path $Dist "LinhEdit"
$Exe = Join-Path $AppDir "LinhEdit.exe"
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
    throw "Không tạo được LinhEdit.exe."
}

$BundledFfmpeg = Get-ChildItem -LiteralPath $AppDir -Recurse -Filter "ffmpeg.exe" -File | Select-Object -First 1
$BundledFfprobe = Get-ChildItem -LiteralPath $AppDir -Recurse -Filter "ffprobe.exe" -File | Select-Object -First 1
$BundledFont = Get-ChildItem -LiteralPath $AppDir -Recurse -Filter "RobotoCondensed-Bold.ttf" -File | Select-Object -First 1
if ($null -eq $BundledFfmpeg -or $null -eq $BundledFfprobe -or $null -eq $BundledFont) {
    throw "Bản Linh Edit chưa đóng gói đủ FFmpeg/FFprobe/font."
}

$Process = Start-Process -FilePath $Exe -ArgumentList "doctor" -Wait -PassThru
if ($Process.ExitCode -ne 0) {
    throw "LinhEdit.exe doctor thất bại với mã $($Process.ExitCode)."
}

$SmokeDir = Join-Path $Root "build\linh-edit-smoke"
New-Item -ItemType Directory -Force -Path $SmokeDir | Out-Null
$SmokeVideo = Join-Path $SmokeDir "clip.mp4"
$SmokeProject = Join-Path $SmokeDir "project.linhedit.json"
$SmokeOutput = Join-Path $SmokeDir "final.mp4"

& $Ffmpeg -y -hide_banner -loglevel error -f lavfi -i "testsrc2=size=1080x1920:rate=30" -f lavfi -i "sine=frequency=440:sample_rate=48000" -t 2 -c:v libx264 -pix_fmt yuv420p -c:a aac $SmokeVideo
Assert-NativeSuccess "Tạo media smoke test Windows"

$Clip = @{
    path = $SmokeVideo
    kind = "video"
    role = "human"
    start = 0.0
    duration = 2.0
    score = 1.0
    x = 0.5
    y = 0.5
    scale = 1.0
    motion = "none"
    keep_audio = $true
    source_gain = 1.0
}
$ProjectPayload = @{
    name = "Windows smoke"
    profile = "TALKING_HEAD_EXPERT"
    target_seconds = 2.0
    title = "Smoke"
    media = @($Clip)
    timeline = @($Clip)
    texts = @()
    sfx = @()
    voiceover = ""
    music = ""
    music_gain = 0.14
    output_dir = $SmokeDir
    dirty = $false
}
$ProjectPayload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SmokeProject -Encoding utf8

$RenderProcess = Start-Process -FilePath $Exe -ArgumentList @("render", "--project", $SmokeProject, "--output", $SmokeOutput) -Wait -PassThru
if ($RenderProcess.ExitCode -ne 0) {
    throw "LinhEdit.exe render smoke test thất bại với mã $($RenderProcess.ExitCode)."
}
if (-not (Test-Path -LiteralPath $SmokeOutput -PathType Leaf)) {
    throw "LinhEdit.exe không tạo video smoke output."
}
& $BundledFfprobe.FullName -v error -select_streams v:0 -show_entries "stream=codec_name,width,height,avg_frame_rate" -of json $SmokeOutput
Assert-NativeSuccess "ffprobe smoke output từ LinhEdit.exe"

Copy-Item -LiteralPath (Join-Path $Root "linh_edit\README.md") -Destination (Join-Path $AppDir "README.txt") -Force
if (Test-Path -LiteralPath (Join-Path $Root "THIRD_PARTY_NOTICES.md")) {
    Copy-Item -LiteralPath (Join-Path $Root "THIRD_PARTY_NOTICES.md") -Destination (Join-Path $AppDir "THIRD_PARTY_NOTICES.md") -Force
}

Write-Host "Linh Edit build hoàn tất: $Exe"
