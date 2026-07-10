$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    py -3.12 -m venv (Join-Path $Root ".venv")
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -e "${Root}[dev]"
& $Python -m pytest
$Arguments = @(
    "--noconfirm",
    "--clean",
    "--name", "MXHPublisher",
    "--collect-all", "playwright",
    "--collect-all", "tzdata",
    "--paths", (Join-Path $Root "src")
)
$Ffprobe = Join-Path $Root "bin\ffprobe.exe"
if (Test-Path $Ffprobe) {
    $Arguments += @("--add-binary", "$Ffprobe;bin")
} else {
    throw "Thiếu bin\ffprobe.exe. Không tạo bản phát hành không tự kiểm tra được video."
}
$Arguments += (Join-Path $Root "src\mxh_publisher\__main__.py")
& $Python -m PyInstaller @Arguments

Write-Host "Bản chạy nằm tại dist\MXHPublisher\MXHPublisher.exe"
