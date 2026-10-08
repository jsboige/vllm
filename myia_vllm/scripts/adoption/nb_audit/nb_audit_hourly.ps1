# Hourly pre-audit pass (CoursIA #17073, mode (b)): produce fresh records, then deliver them.
# Run by the user-level scheduled task that register_hourly.ps1 creates. Record: _iteration_log/nb_audit_pilot/NOTES.md
# Series: 17107/17239/17357 = the original pilot (all at 0 remaining, kept: they cost 3 REST reads and
# pick up anything new). 17692 (02-ML-Cours) + 19451:Audio/ (GenAI/Audio) = wave 1 complete of the
# converged Hermes+NanoClaw order (08/10 evening, user green light same day): one wave at a time, prod
# first, pass size at our call, joint re-evaluation after wave 1. #19451 is a wide series (14 sections,
# 226 unchecked) -- --subpath scopes it to Audio/; later waves switch the prefix. The skip list the
# order named (PR #19868) was stale within hours (closed-superseded by #19854); the runner now derives
# per pass which notebooks an open PR is about to change and skips those by itself.
param([int[]]$Series = @(17107, 17239, 17357, 17692, 19451), [int]$PerSeries = 3,
      [string[]]$Subpath = @('19451:Audio/'))
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $env:LOCALAPPDATA 'nbaudit\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ('hourly-{0:yyyyMMdd}.log' -f (Get-Date).ToUniversalTime())
$env:PYTHONIOENCODING = 'utf-8'
$py = 'C:\Python314\python.exe'
Set-Location $here
function Stamp($m) { Add-Content $log ('=== {0:yyyy-MM-ddTHH:mm:ss}Z {1}' -f (Get-Date).ToUniversalTime(), $m) }

# The pass publishes a durable result. It CANNOT rely on its exit code: the scheduled task
# launches wscript.exe on nb_audit_hourly.launcher.vbs, whose `Run(..., 0, False)` does not wait
# and hands back nothing, so wscript itself always exits 0. Measured 08/10/2026: a VBS with that
# exact tail running a child that exits 7 returned 0. A 37 h outage (07/10 00:05Z -> 08/10 13:05Z,
# 32 consecutive rc=1 passes) therefore left `LastTaskResult` at 0 the whole time -- the log line
# was the only trace, and nothing read the log. The state file below is the signal that survives:
# one line, machine-readable, written on every pass including the failing ones, with a failure
# counter that makes a multi-day silence impossible to miss.
$stateFile = Join-Path (Split-Path -Parent $logDir) 'last-result.json'
function Write-State($runnerRc, $deliverRc) {
    # deliver_rc != 0 means a real send failed (nb_audit_deliver.py returns 1 only when some
    # message did not go out; "nothing to deliver" is 0), so both codes count as a failure.
    $ok = ($runnerRc -eq 0) -and ($deliverRc -eq 0)
    $prev = 0
    if (Test-Path $stateFile) {
        try { $prev = [int](Get-Content $stateFile -Raw | ConvertFrom-Json).consecutive_failures } catch { $prev = 0 }
    }
    $fails = 0
    if (-not $ok) { $fails = $prev + 1 }
    $state = [ordered]@{
        ts                   = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        runner_rc            = $runnerRc
        deliver_rc           = $deliverRc
        ok                   = $ok
        consecutive_failures = $fails
        series               = @($Series)
        per_series           = $PerSeries
        subpath              = @($Subpath)
    }
    # UTF-8 no BOM: Add-Content/Out-File would prepend one and break the parser (global rule).
    [System.IO.File]::WriteAllText($stateFile, ($state | ConvertTo-Json -Compress), [System.Text.UTF8Encoding]::new($false))
}

$rcRunner = -1
$rcDeliver = -1
try {
    Stamp 'runner'
    $runnerArgs = @('nb_audit_runner.py', '--series') + $Series + @('--per-series', $PerSeries)
    foreach ($sp in $Subpath) { $runnerArgs += @('--subpath', $sp) }
    & $py @runnerArgs *>> $log
    $rcRunner = $LASTEXITCODE
    Stamp "runner rc=$rcRunner; deliver"
    & $py nb_audit_deliver.py --send *>> $log
    $rcDeliver = $LASTEXITCODE
    Stamp "deliver rc=$rcDeliver"
} finally {
    Write-State $rcRunner $rcDeliver
}

if ($rcRunner -ne 0) {
    Stamp "FAILED: runner rc=$rcRunner - NO records produced this pass"
}
# Still propagate the code for the day the task is re-pointed at pwsh directly; today the
# launcher discards it, which is exactly why the state file above carries the signal.
if ($rcRunner -ne 0) { exit $rcRunner }
if ($rcDeliver -ne 0) { exit $rcDeliver }
exit 0
