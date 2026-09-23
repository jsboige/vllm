# Register the hourly pre-audit task for the current user (no elevation). Dry-run by default:
# prints the exact task XML and does nothing; -Apply registers it. -Remove unregisters it.
param([switch]$Apply, [switch]$Remove, [string]$Name = 'nbaudit-hourly', [string]$Start = '00:05')
$wrapper = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'nb_audit_hourly.ps1'
$pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$begin = (Get-Date).Date.Add([TimeSpan]::Parse($Start)).ToString('s')
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>CoursIA #17073 pre-audit, mode (b): runner + delivery to the bots. Owner ai-01:vllm.</Description></RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>$begin</StartBoundary>
      <Repetition><Interval>PT1H</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>$user</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StartWhenAvailable>false</StartWhenAvailable>
    <ExecutionTimeLimit>PT50M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>$pwsh</Command><Arguments>-NoProfile -WindowStyle Hidden -File "$wrapper"</Arguments></Exec>
  </Actions>
</Task>
"@
if ($Remove) { Unregister-ScheduledTask -TaskName $Name -Confirm:$false; "removed $Name"; return }
if (-not $Apply) { "DRY-RUN: would register '$Name' for $user with this definition (nothing changed):"; $xml; return }
Register-ScheduledTask -TaskName $Name -Xml $xml | Select-Object TaskName, State
