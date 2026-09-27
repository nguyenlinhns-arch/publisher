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
$Background = Join-Path $Root "assets\nen.png"
$DefaultSfx = Join-Path $Root "assets\sound.mp3"
$Entry = Join-Path $Root "linh_edit_launcher.py"
$HubLauncher = Join-Path $Root "linh_edit\MO_UNG_DUNG.bat"
$HubCheck = Join-Path $Root "linh_edit\CHECK_THAY_LINH_HUB.ps1"
$HubManifest = Join-Path $Root "linh_edit\.thay-linh-app.json"
$AppManifest = Join-Path $Root "linh_edit\app_manifest.json"
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

foreach ($Required in @($Ffmpeg, $Ffprobe, $Fonts, $Background, $DefaultSfx, $Entry, $HubLauncher, $HubCheck, $HubManifest, $AppManifest)) {
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
    & $Python -m pip install "pyinstaller==6.21.0" "pytest==9.1.1" "Pillow==11.3.0"
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
        "--add-data", "$Background;assets",
        "--add-data", "$DefaultSfx;assets",
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
$BundledMontserratSemiBold = Get-ChildItem -LiteralPath $AppDir -Recurse -Filter "Montserrat-SemiBold.ttf" -File | Select-Object -First 1
$BundledMontserratExtraBold = Get-ChildItem -LiteralPath $AppDir -Recurse -Filter "Montserrat-ExtraBold.ttf" -File | Select-Object -First 1
$BundledOswaldBold = Get-ChildItem -LiteralPath $AppDir -Recurse -Filter "Oswald-Bold.ttf" -File | Select-Object -First 1
$BundledBackground = Get-ChildItem -LiteralPath $AppDir -Recurse -Filter "nen.png" -File | Select-Object -First 1
$BundledSfx = Get-ChildItem -LiteralPath $AppDir -Recurse -Filter "sound.mp3" -File | Select-Object -First 1
if (
    $null -eq $BundledFfmpeg -or
    $null -eq $BundledFfprobe -or
    $null -eq $BundledMontserratSemiBold -or
    $null -eq $BundledMontserratExtraBold -or
    $null -eq $BundledOswaldBold -or
    $null -eq $BundledBackground -or
    $null -eq $BundledSfx
) {
    throw "Bản Linh Edit chưa đóng gói đủ FFmpeg/FFprobe/Montserrat/Oswald/nền/SFX."
}

$Process = Start-Process -FilePath $Exe -ArgumentList "doctor" -Wait -PassThru
if ($Process.ExitCode -ne 0) {
    throw "LinhEdit.exe doctor thất bại với mã $($Process.ExitCode)."
}

$SmokeDir = Join-Path $Root "build\linh-edit-smoke"
New-Item -ItemType Directory -Force -Path $SmokeDir | Out-Null
$SmokeVideo = Join-Path $SmokeDir "clip.mp4"
$SmokeVoice = Join-Path $SmokeDir "voice.wav"
$SmokeMusic = Join-Path $SmokeDir "music.wav"
$SmokeProject = Join-Path $SmokeDir "project.linhedit.json"
$SmokeOutput = Join-Path $SmokeDir "final.mp4"

& $Ffmpeg -y -hide_banner -loglevel error -f lavfi -i "testsrc2=size=1080x1920:rate=30" -f lavfi -i "sine=frequency=440:sample_rate=48000" -t 6 -c:v libx264 -pix_fmt yuv420p -c:a aac $SmokeVideo
Assert-NativeSuccess "Tạo media smoke test Windows"
& $Ffmpeg -y -hide_banner -loglevel error -f lavfi -i "sine=frequency=700:sample_rate=48000" -t 5 -c:a pcm_s16le $SmokeVoice
Assert-NativeSuccess "Tạo voice smoke test"
& $Ffmpeg -y -hide_banner -loglevel error -f lavfi -i "sine=frequency=120:sample_rate=48000" -t 6 -c:a pcm_s16le $SmokeMusic
Assert-NativeSuccess "Tạo music smoke test"

$Clip = @{
    path = $SmokeVideo
    kind = "video"
    role = "human"
    start = 0.0
    duration = 6.0
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
    target_seconds = 6.0
    title = "Smoke"
    media = @($Clip)
    timeline = @($Clip)
    texts = @()
    sfx = @()
    voiceover = $SmokeVoice
    music = $SmokeMusic
    music_gain = 0.14
    voice_gain = 1.0
    auto_duck_music = $true
    duck_threshold = 0.025
    duck_ratio = 8.0
    duck_attack_ms = 25.0
    duck_release_ms = 450.0
    caption_coverage_target = 0.65
    transcript = "Buoi sang toi di tren con duong vao lang. Sau do toi gap nguoi dan va tiep tuc cong viec."
    output_dir = $SmokeDir
    dirty = $false
}
$ProjectPayload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SmokeProject -Encoding utf8

$CaptionProcess = Start-Process -FilePath $Exe -ArgumentList @(
    "caption-apply",
    "--project", $SmokeProject,
    "--coverage", "0.65"
) -Wait -PassThru
if ($CaptionProcess.ExitCode -ne 0) {
    throw "LinhEdit.exe caption-apply smoke test thất bại với mã $($CaptionProcess.ExitCode)."
}

$TextShotProcess = Start-Process -FilePath $Exe -ArgumentList @(
    "text-shot-report",
    "--project", $SmokeProject,
    "--coverage", "0.65"
) -Wait -PassThru
if ($TextShotProcess.ExitCode -ne 0) {
    throw "LinhEdit.exe text-shot-report smoke test thất bại với mã $($TextShotProcess.ExitCode)."
}

$TalkRhythmProcess = Start-Process -FilePath $Exe -ArgumentList @(
    "talk-rhythm-apply",
    "--project", $SmokeProject,
    "--minimum-segment", "1.0",
    "--punch-scale", "1.035"
) -Wait -PassThru
if ($TalkRhythmProcess.ExitCode -ne 0) {
    throw "LinhEdit.exe talk-rhythm-apply smoke test thất bại với mã $($TalkRhythmProcess.ExitCode)."
}

$RenderProcess = Start-Process -FilePath $Exe -ArgumentList @("render", "--project", $SmokeProject, "--output", $SmokeOutput) -Wait -PassThru
if ($RenderProcess.ExitCode -ne 0) {
    throw "LinhEdit.exe render smoke test thất bại với mã $($RenderProcess.ExitCode)."
}
if (-not (Test-Path -LiteralPath $SmokeOutput -PathType Leaf)) {
    throw "LinhEdit.exe không tạo video smoke output."
}
& $BundledFfprobe.FullName -v error -select_streams v:0 -show_entries "stream=codec_name,width,height,avg_frame_rate" -of json $SmokeOutput
Assert-NativeSuccess "ffprobe smoke output từ LinhEdit.exe"

$ProxyProcess = Start-Process -FilePath $Exe -ArgumentList @(
    "proxy-build",
    "--media", $SmokeVideo
) -Wait -PassThru
if ($ProxyProcess.ExitCode -ne 0) {
    throw "LinhEdit.exe proxy-build smoke test thất bại với mã $($ProxyProcess.ExitCode)."
}

$ShotProcess = Start-Process -FilePath $Exe -ArgumentList @(
    "shot-detect",
    "--media", $SmokeVideo
) -Wait -PassThru
if ($ShotProcess.ExitCode -ne 0) {
    throw "LinhEdit.exe shot-detect smoke test thất bại với mã $($ShotProcess.ExitCode)."
}

$ReviewDir = Join-Path $SmokeDir "source-review"
$ReviewProcess = Start-Process -FilePath $Exe -ArgumentList @(
    "source-review",
    "--media", $SmokeVideo,
    "--output-dir", $ReviewDir,
    "--tiles", "4",
    "--columns", "4"
) -Wait -PassThru
if ($ReviewProcess.ExitCode -ne 0) {
    throw "LinhEdit.exe source-review smoke test thất bại với mã $($ReviewProcess.ExitCode)."
}
$ReviewManifest = Join-Path $ReviewDir "source_review_manifest.json"
if (-not (Test-Path -LiteralPath $ReviewManifest -PathType Leaf)) {
    throw "LinhEdit.exe không tạo source review manifest."
}

$VisualOutput = Join-Path $SmokeDir "visual_master_no_audio.mp4"
$VisualProcess = Start-Process -FilePath $Exe -ArgumentList @(
    "render",
    "--project", $SmokeProject,
    "--output", $VisualOutput,
    "--visual-master"
) -Wait -PassThru
if ($VisualProcess.ExitCode -ne 0) {
    throw "LinhEdit.exe visual master smoke test thất bại với mã $($VisualProcess.ExitCode)."
}
if (-not (Test-Path -LiteralPath $VisualOutput -PathType Leaf)) {
    throw "LinhEdit.exe không tạo visual master smoke output."
}
$AudioProbe = & $BundledFfprobe.FullName -v error -select_streams a:0 -show_entries "stream=codec_name" -of "csv=p=0" $VisualOutput
Assert-NativeSuccess "ffprobe visual master output"
if ($AudioProbe) {
    throw "Visual master không được chứa audio stream."
}

foreach ($ReviewStage in @("visual", "audio", "full")) {
    $ReviewProcess = Start-Process -FilePath $Exe -ArgumentList @(
        "review-set",
        "--project", $SmokeProject,
        "--stage", $ReviewStage,
        "--value", "PASS"
    ) -Wait -PassThru
    if ($ReviewProcess.ExitCode -ne 0) {
        throw "LinhEdit.exe review-set $ReviewStage smoke test thất bại."
    }
}
$ReviewStatusProcess = Start-Process -FilePath $Exe -ArgumentList @(
    "review-status",
    "--project", $SmokeProject
) -Wait -PassThru
if ($ReviewStatusProcess.ExitCode -ne 0) {
    throw "LinhEdit.exe review-status smoke test thất bại."
}

Copy-Item -LiteralPath (Join-Path $Root "linh_edit\README.md") -Destination (Join-Path $AppDir "README.txt") -Force
Copy-Item -LiteralPath $HubLauncher -Destination (Join-Path $AppDir "MO_UNG_DUNG.bat") -Force
Copy-Item -LiteralPath $HubCheck -Destination (Join-Path $AppDir "CHECK_THAY_LINH_HUB.ps1") -Force
Copy-Item -LiteralPath $HubManifest -Destination (Join-Path $AppDir ".thay-linh-app.json") -Force
Copy-Item -LiteralPath $AppManifest -Destination (Join-Path $AppDir "app_manifest.json") -Force

foreach ($RequiredPackaged in @(
    (Join-Path $AppDir "MO_UNG_DUNG.bat"),
    (Join-Path $AppDir "CHECK_THAY_LINH_HUB.ps1"),
    (Join-Path $AppDir ".thay-linh-app.json"),
    (Join-Path $AppDir "app_manifest.json")
)) {
    if (-not (Test-Path -LiteralPath $RequiredPackaged -PathType Leaf)) {
        throw "Thiếu thành phần Hub trong bản đóng gói: $RequiredPackaged"
    }
}

if (Test-Path -LiteralPath (Join-Path $Root "THIRD_PARTY_NOTICES.md")) {
    Copy-Item -LiteralPath (Join-Path $Root "THIRD_PARTY_NOTICES.md") -Destination (Join-Path $AppDir "THIRD_PARTY_NOTICES.md") -Force
}

Write-Host "Linh Edit build hoàn tất: $Exe"
