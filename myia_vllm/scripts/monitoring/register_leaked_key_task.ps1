$ErrorActionPreference = 'Stop'

$TaskName = 'LeakedKeyMonitor-vLLM'
$Pwsh     = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Script   = 'D:\vllm\myia_vllm\scripts\monitoring\run_leaked_key_monitor.ps1'

# Remove any prior registration so this is idempotent.
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task '$TaskName'."
}

$action = New-ScheduledTaskAction -Execute $Pwsh `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""

# Fire hourly, indefinitely. Base time = now (gives a natural off-:00 minute).
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 1)

# Interactive: runs in the logged-on user's session so the GDrive G: mount
# (where roo-state-manager writes the dashboards) is visible.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description 'Hourly leaked vLLM medium API-key monitor (MONITORING ONLY, no key rotation). On a new unauthorized public IP or volume spike, relays an alert to workspace-roo-extensions + workspace-cluster-coordination via dashboard_post.cjs.' | Out-Null

Write-Host "Registered '$TaskName'."
Get-ScheduledTask -TaskName $TaskName |
    Select-Object TaskName, State,
        @{n='NextRun';e={(Get-ScheduledTaskInfo $_.TaskName).NextRunTime}} |
    Format-List
