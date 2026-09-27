[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exe = Join-Path $Root "LinhEdit.exe"

if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
    Write-Error "MISSING_LINH_EDIT_EXE"
    exit 1
}

$Process = Start-Process -FilePath $Exe -ArgumentList "doctor" -Wait -PassThru
if ($Process.ExitCode -ne 0) {
    Write-Error "LINH_EDIT_DOCTOR_FAILED:$($Process.ExitCode)"
    exit $Process.ExitCode
}

Write-Output "PASS Linh Edit doctor"
exit 0
