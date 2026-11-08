# Register the hourly pre-audit task for the current user (no elevation). Dry-run by default:
# prints the exact task XML and does nothing; -Apply registers it. -Remove unregisters it.
# 2026-11-08: :05 -> :12. The GitHub REST bucket (5000/h per USER, shared fleet-wide)
# rolls over around :06-:08Z; every :05Z pass since 05:05Z 08/11 died on "rate limit
# exceeded" while the fresh window measured nearly empty minutes later. :12 lands
# 4-6 min after the rollover. Re-register with -Apply -Start 00:12 (dry-run default).
param([switch]$Apply, [switch]$Remove, [string]$Name = 'nbaudit-hourly', [string]$Start = '00:12')
$wrapper = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'nb_audit_hourly.ps1'
$vbs = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'nb_audit_hourly.launcher.vbs'   # invisible launcher (flicker fix #44) - a direct pwsh action flashes a console hourly
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
    <Exec><Command>wscript.exe</Command><Arguments>"$vbs"</Arguments></Exec>
  </Actions>
</Task>
"@
if ($Remove) { Unregister-ScheduledTask -TaskName $Name -Confirm:$false; "removed $Name"; return }
if (-not $Apply) { "DRY-RUN: would register '$Name' for $user with this definition (nothing changed):"; $xml; return }
Register-ScheduledTask -TaskName $Name -Xml $xml | Select-Object TaskName, State
