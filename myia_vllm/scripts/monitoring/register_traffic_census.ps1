# register_traffic_census.ps1 -- register the user-level hourly traffic-census task
# =====================================================================================
# Same proven pattern as nb_audit/register_hourly.ps1 (raw task XML +
# Register-ScheduledTask -Xml; the New-ScheduledTaskAction object loses its
# Argument property on this PS5.1 host -- measured 10/10). User-level,
# LeastPrivilege -> NO UAC prompt.
#
# Dry-run by default: prints the exact task XML and does nothing. -Apply
# registers it. -Remove unregisters it.
#
# Cadence: hourly at minute 25 -- clear of the nbaudit runner at :05. The
# worker's checkpoint makes a late/missed pass safe (it just aggregates more).
# State trace: %LOCALAPPDATA%\traffic-census\last-result.json (the scheduled-
# task LastTaskResult is NOT a health signal -- nbaudit 37h-outage lesson).
# =====================================================================================
param([switch]$Apply, [switch]$Remove, [string]$Name = 'traffic-census-hourly', [string]$Start = '00:25')
$worker = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'traffic_census_hourly.ps1'
$pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$begin = (Get-Date).Date.Add([TimeSpan]::Parse($Start)).ToString('s')
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Persistent hourly aggregation of the :5002 traffic census (po-2025 request, log rotates ~1.2h). Owner ai-01:vllm. State: %LOCALAPPDATA%\traffic-census\last-result.json.</Description></RegistrationInfo>
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
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>$pwsh</Command><Arguments>-NoProfile -WindowStyle Hidden -File "$worker"</Arguments></Exec>
  </Actions>
</Task>
"@
if ($Remove) { Unregister-ScheduledTask -TaskName $Name -Confirm:$false; "removed $Name"; return }
if (-not $Apply) { "DRY-RUN: would register '$Name' for $user with this definition (nothing changed):"; $xml; return }
Register-ScheduledTask -TaskName $Name -Xml $xml | Select-Object TaskName, State
