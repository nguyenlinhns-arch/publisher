param([string]$Version = "1.1.0")
$ErrorActionPreference = "Stop"
$portable = Join-Path $PSScriptRoot "..\dist\MXHVideoEditor-$Version-Windows-x64"
if (-not (Test-Path $portable)) { throw "Portable build not found: $portable" }
$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) is required to build Setup.exe." }
$template = Join-Path $PSScriptRoot "installer.iss"
& $iscc.Source "/DMyAppVersion=$Version" "/DSourceDir=$portable" $template
if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }
