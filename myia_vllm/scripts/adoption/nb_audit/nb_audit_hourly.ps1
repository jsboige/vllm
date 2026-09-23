# Hourly pre-audit pass (CoursIA #17073, mode (b)): produce fresh records, then deliver them.
# Run by the user-level scheduled task that register_hourly.ps1 creates. Record: _iteration_log/nb_audit_pilot/NOTES.md
param([int[]]$Series = @(17107, 17239, 17357), [int]$PerSeries = 3)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $env:LOCALAPPDATA 'nbaudit\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ('hourly-{0:yyyyMMdd}.log' -f (Get-Date).ToUniversalTime())
$env:PYTHONIOENCODING = 'utf-8'
$py = 'C:\Python314\python.exe'
Set-Location $here
function Stamp($m) { Add-Content $log ('=== {0:yyyy-MM-ddTHH:mm:ss}Z {1}' -f (Get-Date).ToUniversalTime(), $m) }
Stamp 'runner'
& $py nb_audit_runner.py --series @Series --per-series $PerSeries *>> $log
Stamp "runner rc=$LASTEXITCODE; deliver"
& $py nb_audit_deliver.py --send *>> $log
Stamp "deliver rc=$LASTEXITCODE"
