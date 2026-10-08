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
$rcRunner = $LASTEXITCODE
Stamp "runner rc=$rcRunner; deliver"
& $py nb_audit_deliver.py --send *>> $log
$rcDeliver = $LASTEXITCODE
Stamp "deliver rc=$rcDeliver"

# A runner failure leaves the deliverer with nothing to send, and the deliverer exits 0
# ("nothing to deliver") -- so the pass reads as healthy while the workload is dead. It
# stayed dead 37 h that way (07/10 00:05Z -> 08/10 13:05Z, rc=1 on every pass). The log
# line alone was not enough: fail loudly, so LastTaskResult turns non-zero and
# Get-ScheduledTaskInfo shows it without reading the log at all.
if ($rcRunner -ne 0) {
    Stamp "FAILED: runner rc=$rcRunner — NO records produced this pass"
    exit $rcRunner
}
exit 0
