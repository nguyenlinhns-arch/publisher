[CmdletBinding()]
param(
    [string]$BundlePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$Root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($BundlePath)) {
    $BundlePath = Join-Path $Root "dist\MXHPublisher"
}
$BundlePath = (Resolve-Path -LiteralPath $BundlePath).Path
$TemporaryBase = if ([string]::IsNullOrWhiteSpace($env:RUNNER_TEMP)) {
    [System.IO.Path]::GetTempPath()
} else {
    $env:RUNNER_TEMP
}
$Sandbox = Join-Path $TemporaryBase `
    ("mxh-publisher-smoke-" + [guid]::NewGuid().ToString("N"))
$IsolatedBundle = Join-Path $Sandbox "MXHPublisher"
$Application = Join-Path $IsolatedBundle "MXHPublisher.exe"
$Process = $null

$OldLocalAppData = $env:LOCALAPPDATA
$OldAppData = $env:APPDATA
$OldPythonPath = $env:PYTHONPATH
$OldFacebookToken = $env:MXH_FACEBOOK_PAGE_TOKEN

function Assert-ExitCode {
    param(
        [Parameter(Mandatory = $true)][string]$Step,
        [Parameter(Mandatory = $true)][int]$ExitCode
    )
    if ($ExitCode -ne 0) {
        throw "$Step thất bại với mã thoát $ExitCode."
    }
}

function Invoke-PackagedCommand {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $CommandProcess = Start-Process `
        -FilePath $Application `
        -ArgumentList $Arguments `
        -WorkingDirectory $Sandbox `
        -Wait `
        -PassThru
    return $CommandProcess.ExitCode
}

function Restore-EnvironmentValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()][string]$Value
    )
    if ($null -eq $Value) {
        Remove-Item "Env:$Name" -ErrorAction SilentlyContinue
    } else {
        Set-Item "Env:$Name" $Value
    }
}

New-Item -ItemType Directory -Force -Path $Sandbox | Out-Null
Copy-Item -LiteralPath $BundlePath -Destination $IsolatedBundle -Recurse
if (-not (Test-Path -LiteralPath $Application -PathType Leaf)) {
    throw "Không tìm thấy EXE trong bản onedir biệt lập: $Application"
}

# PE optional-header Subsystem 2 means IMAGE_SUBSYSTEM_WINDOWS_GUI. This is a
# release invariant: Windows must not create a CMD/console window for the app.
$ExecutableBytes = [System.IO.File]::ReadAllBytes($Application)
$PeHeaderOffset = [System.BitConverter]::ToInt32($ExecutableBytes, 0x3c)
$OptionalHeaderOffset = $PeHeaderOffset + 24
$Subsystem = [System.BitConverter]::ToUInt16(
    $ExecutableBytes,
    $OptionalHeaderOffset + 68
)
if ($Subsystem -ne 2) {
    throw "MXHPublisher.exe không phải Windows GUI subsystem; CMD có thể xuất hiện."
}
Write-Host "PE subsystem đạt: Windows GUI (không tạo cửa sổ CMD)."

$env:LOCALAPPDATA = Join-Path $Sandbox "LocalAppData"
$env:APPDATA = Join-Path $Sandbox "RoamingAppData"
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:MXH_FACEBOOK_PAGE_TOKEN -ErrorAction SilentlyContinue

Push-Location $Sandbox
try {
    $HelpExitCode = Invoke-PackagedCommand -Arguments @("--help")
    Assert-ExitCode "MXHPublisher --help" $HelpExitCode

    # Newer builds expose --system-only. Exit code 2 means an older parser, so
    # fall back to the existing doctor command without ever requiring FB tokens.
    $DoctorExitCode = Invoke-PackagedCommand `
        -Arguments @("doctor", "--system-only")
    if ($DoctorExitCode -eq 2) {
        $FallbackDoctorExitCode = Invoke-PackagedCommand -Arguments @("doctor")
        Assert-ExitCode "MXHPublisher doctor" $FallbackDoctorExitCode
    } else {
        Assert-ExitCode "MXHPublisher doctor --system-only" $DoctorExitCode
    }

    $WorkerExitCode = Invoke-PackagedCommand `
        -Arguments @("worker", "--verify-due", "--max-items", "1")
    Assert-ExitCode "Worker với database trống" $WorkerExitCode

    $BundledFfprobe = Get-ChildItem -LiteralPath $IsolatedBundle `
        -Recurse -Filter "ffprobe.exe" -File | Select-Object -First 1
    if ($null -eq $BundledFfprobe) {
        throw "Bản onedir không chứa ffprobe.exe."
    }
    & $BundledFfprobe.FullName -version
    Assert-ExitCode "ffprobe đóng gói" $LASTEXITCODE
    $BundledFfmpeg = Get-ChildItem -LiteralPath $IsolatedBundle `
        -Recurse -Filter "ffmpeg.exe" -File | Select-Object -First 1
    if ($null -eq $BundledFfmpeg) {
        throw "Bản onedir không chứa ffmpeg.exe."
    }
    & $BundledFfmpeg.FullName -version
    Assert-ExitCode "ffmpeg đóng gói" $LASTEXITCODE

    $BundledFrame = Get-ChildItem -LiteralPath $IsolatedBundle `
        -Recurse -Filter "nen.png" -File | Select-Object -First 1
    if ($null -eq $BundledFrame) {
        throw "Bản onedir thiếu khung nền mặc định nen.png."
    }
    $FrameHash = (Get-FileHash -LiteralPath $BundledFrame.FullName `
        -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($FrameHash -ne "d66882d0e60f73cdde049d6ad997a859ee0d379571bb0dc36e6155df58c6d910") {
        throw "Khung nền mặc định không đúng tệp đã duyệt."
    }

    $PlaywrightNode = Get-ChildItem -LiteralPath $IsolatedBundle `
        -Recurse -Filter "node.exe" -File |
        Where-Object { $_.FullName -match 'playwright' } |
        Select-Object -First 1
    $PlaywrightCli = Get-ChildItem -LiteralPath $IsolatedBundle `
        -Recurse -Filter "cli.js" -File |
        Where-Object { $_.FullName -match 'playwright' } |
        Select-Object -First 1
    if ($null -eq $PlaywrightNode -or $null -eq $PlaywrightCli) {
        throw "Bản onedir thiếu Playwright driver (node.exe/cli.js)."
    }
    & $PlaywrightNode.FullName $PlaywrightCli.FullName --version
    Assert-ExitCode "Playwright driver đóng gói" $LASTEXITCODE

    $Process = Start-Process -FilePath $Application -WorkingDirectory $Sandbox -PassThru
    Start-Sleep -Seconds 5
    $Process.Refresh()
    if ($Process.HasExited) {
        throw "Giao diện thoát sớm với mã $($Process.ExitCode)."
    }
    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    $Process.WaitForExit(5000) | Out-Null
    $Process = $null

    Write-Host "Smoke test Windows onedir đạt."
} catch {
    $LogDirectory = Join-Path $env:LOCALAPPDATA "MXHPublisher\logs"
    if (Test-Path -LiteralPath $LogDirectory) {
        Get-ChildItem -LiteralPath $LogDirectory -File |
            ForEach-Object {
                Write-Host "--- Log: $($_.FullName)"
                Get-Content -LiteralPath $_.FullName -Tail 200
            }
    }
    throw
} finally {
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
    Restore-EnvironmentValue "LOCALAPPDATA" $OldLocalAppData
    Restore-EnvironmentValue "APPDATA" $OldAppData
    Restore-EnvironmentValue "PYTHONPATH" $OldPythonPath
    Restore-EnvironmentValue "MXH_FACEBOOK_PAGE_TOKEN" $OldFacebookToken
    if (Test-Path -LiteralPath $Sandbox) {
        Remove-Item -LiteralPath $Sandbox -Recurse -Force
    }
}
