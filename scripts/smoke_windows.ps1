[CmdletBinding()]
param([string]$BundlePath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$Root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($BundlePath)) {
    $BundlePath = Join-Path $Root "dist\MXHVideoEditor"
}
$BundlePath = (Resolve-Path -LiteralPath $BundlePath).Path
$TemporaryBase = if ([string]::IsNullOrWhiteSpace($env:RUNNER_TEMP)) {
    [System.IO.Path]::GetTempPath()
} else {
    $env:RUNNER_TEMP
}
$Sandbox = Join-Path $TemporaryBase ("mxh-video-editor-smoke-" + [guid]::NewGuid().ToString("N"))
$IsolatedBundle = Join-Path $Sandbox "MXHVideoEditor"
$Application = Join-Path $IsolatedBundle "MXHVideoEditor.exe"
$OutputDirectory = Join-Path $Sandbox "outputs"
$InputVideo = Join-Path $Sandbox "sample.mp4"
$Process = $null

function Assert-ExitCode {
    param([string]$Step, [int]$ExitCode)
    if ($ExitCode -ne 0) {
        throw "$Step thất bại với mã thoát $ExitCode."
    }
}

function Invoke-PackagedCommand {
    param([string[]]$Arguments)
    $CommandProcess = Start-Process -FilePath $Application -ArgumentList $Arguments `
        -WorkingDirectory $Sandbox -Wait -PassThru
    return $CommandProcess.ExitCode
}

New-Item -ItemType Directory -Force -Path $Sandbox, $OutputDirectory | Out-Null
Copy-Item -LiteralPath $BundlePath -Destination $IsolatedBundle -Recurse
if (-not (Test-Path -LiteralPath $Application -PathType Leaf)) {
    throw "Không tìm thấy MXHVideoEditor.exe trong bản onedir."
}

# IMAGE_SUBSYSTEM_WINDOWS_GUI = 2: chạy app không tạo cửa sổ CMD.
$ExecutableBytes = [System.IO.File]::ReadAllBytes($Application)
$PeHeaderOffset = [System.BitConverter]::ToInt32($ExecutableBytes, 0x3c)
$OptionalHeaderOffset = $PeHeaderOffset + 24
$Subsystem = [System.BitConverter]::ToUInt16($ExecutableBytes, $OptionalHeaderOffset + 68)
if ($Subsystem -ne 2) {
    throw "MXHVideoEditor.exe không phải Windows GUI subsystem."
}

$BundledFfprobe = Get-ChildItem -LiteralPath $IsolatedBundle -Recurse `
    -Filter "ffprobe.exe" -File | Select-Object -First 1
$BundledFfmpeg = Get-ChildItem -LiteralPath $IsolatedBundle -Recurse `
    -Filter "ffmpeg.exe" -File | Select-Object -First 1
$BundledFrame = Get-ChildItem -LiteralPath $IsolatedBundle -Recurse `
    -Filter "nen.png" -File | Select-Object -First 1
$BundledIntroSound = Get-ChildItem -LiteralPath $IsolatedBundle -Recurse `
    -Filter "sound.mp3" -File | Select-Object -First 1
$BundledTitleFont = Get-ChildItem -LiteralPath $IsolatedBundle -Recurse `
    -Filter "Montserrat-ExtraBold.ttf" -File | Select-Object -First 1
$BundledBrandFont = Get-ChildItem -LiteralPath $IsolatedBundle -Recurse `
    -Filter "Montserrat-SemiBold.ttf" -File | Select-Object -First 1
if ($null -eq $BundledFfprobe -or $null -eq $BundledFfmpeg `
        -or $null -eq $BundledFrame -or $null -eq $BundledIntroSound `
        -or $null -eq $BundledTitleFont `
        -or $null -eq $BundledBrandFont) {
    throw "Bản đóng gói thiếu ffmpeg, ffprobe, nền mặc định hoặc font chữ."
}
$FrameHash = (Get-FileHash -LiteralPath $BundledFrame.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($FrameHash -ne "d66882d0e60f73cdde049d6ad997a859ee0d379571bb0dc36e6155df58c6d910") {
    throw "Khung nền mặc định không đúng tệp đã duyệt."
}
$SoundHash = (Get-FileHash -LiteralPath $BundledIntroSound.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($SoundHash -ne "d2a6e6eb3191c0498637b24897b420717bcae71c4b73f1ab5237db9c47a802f6") {
    throw "Âm thanh mở đầu không đúng tệp người dùng cung cấp."
}

Push-Location $Sandbox
try {
    Assert-ExitCode "MXHVideoEditor --help" (Invoke-PackagedCommand -Arguments @("--help"))
    Assert-ExitCode "MXHVideoEditor doctor" (Invoke-PackagedCommand -Arguments @("doctor"))

    & $BundledFfmpeg.FullName -hide_banner -loglevel error -y `
        -f lavfi -t 14 -i "testsrc2=size=640x360:rate=30" `
        -f lavfi -t 14 -i "sine=frequency=880:sample_rate=48000" `
        -shortest -c:v libx264 -preset ultrafast -pix_fmt yuv420p `
        -c:a aac -movflags +faststart $InputVideo
    Assert-ExitCode "Tạo video smoke-test" $LASTEXITCODE

    $RenderArguments = @(
        "render", "--input", $InputVideo,
        "--title", "VIDEO_KIEM_TRA-FONT_VIET_NAM",
        "--output-dir", $OutputDirectory
    )
    Assert-ExitCode "Sửa video đóng gói" (Invoke-PackagedCommand -Arguments $RenderArguments)
    $Rendered = Get-ChildItem -LiteralPath $OutputDirectory -Filter "*.mp4" -File |
        Select-Object -First 1
    if ($null -eq $Rendered) {
        throw "Ứng dụng không tạo video thành phẩm."
    }
    $ProbeJson = (& $BundledFfprobe.FullName -v error -show_entries `
        "stream=codec_type,codec_name,width,height:format=duration" `
        -of json $Rendered.FullName) | ConvertFrom-Json
    Assert-ExitCode "Đọc video thành phẩm" $LASTEXITCODE
    $VideoStream = $ProbeJson.streams | Where-Object { $_.codec_type -eq "video" } |
        Select-Object -First 1
    $AudioStream = $ProbeJson.streams | Where-Object { $_.codec_type -eq "audio" } |
        Select-Object -First 1
    if ($VideoStream.width -ne 1080 -or $VideoStream.height -ne 1920 `
            -or $VideoStream.codec_name -ne "h264" -or $AudioStream.codec_name -ne "aac") {
        throw "Video thành phẩm không đúng H.264/AAC 1080×1920."
    }
    $Duration = [double]$ProbeJson.format.duration
    if ($Duration -lt 3.6 -or $Duration -gt 4.0) {
        throw "Cắt 6,2 giây đầu và 4 giây cuối không đúng; thời lượng=$Duration."
    }

    $Process = Start-Process -FilePath $Application -WorkingDirectory $Sandbox -PassThru
    Start-Sleep -Seconds 5
    $Process.Refresh()
    if ($Process.HasExited) {
        throw "Giao diện thoát sớm với mã $($Process.ExitCode)."
    }
    Stop-Process -Id $Process.Id -Force
    $Process.WaitForExit(5000) | Out-Null
    $Process = $null
    Write-Host "Smoke test MXH Video Editor đạt."
} finally {
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
    if (Test-Path -LiteralPath $Sandbox) {
        Remove-Item -LiteralPath $Sandbox -Recurse -Force
    }
}
