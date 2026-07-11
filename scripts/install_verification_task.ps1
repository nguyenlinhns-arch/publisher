param([string]$Executable)

$ErrorActionPreference = "Stop"
$PackagedExecutable = Join-Path $PSScriptRoot "..\MXHPublisher.exe"
$DevelopmentExecutable = Join-Path $PSScriptRoot "..\dist\MXHPublisher\MXHPublisher.exe"
if ([string]::IsNullOrWhiteSpace($Executable)) {
    $Executable = if (Test-Path -LiteralPath $PackagedExecutable) {
        $PackagedExecutable
    } else {
        $DevelopmentExecutable
    }
}
$Executable = (Resolve-Path $Executable).Path
$Action = New-ScheduledTaskAction -Execute $Executable -Argument "worker --verify-due"
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 15)
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName "MXHPublisher-Verify" `
    -Description "Đối soát chỉ-đọc trạng thái Facebook đã lên lịch; không tạo bài mới." `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Force

Write-Host "Đã tạo Task Scheduler MXHPublisher-Verify."
