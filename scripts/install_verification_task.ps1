param(
    [string]$Executable = "$PSScriptRoot\..\dist\MXHPublisher\MXHPublisher.exe"
)

$ErrorActionPreference = "Stop"
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
    -Description "Kiểm tra trạng thái bài Facebook/TikTok đã lên lịch; không tự đăng bài." `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Force

Write-Host "Đã tạo Task Scheduler MXHPublisher-Verify."

