<#
.SYNOPSIS
    End-to-end tests of vllm_watchdog.ps1 alert delivery, without a dashboard,
    a model request or an engine restart. The real CLI is replaced by a Node
    recorder; health is forced, and every state/log lives under a scratch root.
#>
[CmdletBinding()]
param(
    [string]$ScratchRoot = (Join-Path $PSScriptRoot '../../../.tmp/watchdog-tests')
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$script = Join-Path $PSScriptRoot 'vllm_watchdog.ps1'
$node = (Get-Command node -ErrorAction Stop).Source
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$runRoot = Join-Path $ScratchRoot ("run-" + [Guid]::NewGuid().ToString('N'))
[System.IO.Directory]::CreateDirectory($runRoot) | Out-Null
$machine = $env:COMPUTERNAME.ToLowerInvariant()
$script:passed = 0
$env:WATCHDOG_TEST_MODE = 'ok'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "ASSERTION: $Message" }
    $script:passed++
}

function New-Case {
    param([string]$Name, [string]$State = 'down', [switch]$ReAlert)
    $case = Join-Path $runRoot $Name
    [System.IO.Directory]::CreateDirectory((Join-Path $case 'state')) | Out-Null
    [System.IO.Directory]::CreateDirectory((Join-Path $case 'rsm/scripts')) | Out-Null
    $state = if ($State -eq 'down') {
        '{"state":"down","since":"2026-01-01T00:00:00.000Z","lastAlert":"' + $(if ($ReAlert) { '2026-01-01T00:00:00.000Z' } else { '' }) + '","mode":"stack-present"}'
    } else {
        '{"state":"up","since":"","lastAlert":"","mode":"stack-present"}'
    }
    [System.IO.File]::WriteAllText((Join-Path $case 'state/vllm-watchdog-state.json'),
        $state, [System.Text.UTF8Encoding]::new($false))
    return $case
}

function Set-FakeCli {
    param([string]$Case, [ValidateSet('ok', 'workspace-fails', 'pg-unsynced', 'deduplicated')][string]$Mode)
    $js = @'
const fs = await import('node:fs');
const args = process.argv.slice(2);
fs.appendFileSync(process.env.WATCHDOG_TEST_LOG, JSON.stringify(args) + '\n');
const dashboard = args[args.indexOf('--dashboard') + 1];
if (process.env.WATCHDOG_TEST_MODE === 'workspace-fails' && dashboard === 'workspace:vllm') {
  console.error('injected workspace failure');
  process.exit(7);
}
if (process.env.WATCHDOG_TEST_MODE === 'deduplicated') {
  console.log(JSON.stringify({ok: true, base: 'file', deduplicated: true}));
} else {
  console.log(JSON.stringify({ok: true, pgSynced: process.env.WATCHDOG_TEST_MODE !== 'pg-unsynced'}));
}
'@
    [System.IO.File]::WriteAllText((Join-Path $Case 'rsm/scripts/rsm-dashboard-append.mjs'), $js,
        [System.Text.UTF8Encoding]::new($false))
    $env:WATCHDOG_TEST_MODE = $Mode
}

function Invoke-Watchdog {
    param([string]$Case, [switch]$Up, [switch]$Down, [switch]$DryRun, [switch]$MissingCli,
        [string]$Mode = '', [switch]$LockHeld)
    # One JSON-lines log per CASE: the second pass of a case reads the calls of both passes.
    $log = Join-Path $Case 'cli.jsonl'
    $env:WATCHDOG_TEST_LOG = $log
    # Without -Mode the child inherits the mode Set-FakeCli last installed for the case.
    if ($Mode) { $env:WATCHDOG_TEST_MODE = $Mode }
    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script,
        '-StateDir', (Join-Path $Case 'state'), '-RsmRoot', (Join-Path $Case 'rsm'),
        '-NodePath', $node, '-HealthUrl', 'http://127.0.0.1:9/', '-SelfTimeoutSeconds', '0')
    $rsmIndex = [Array]::IndexOf($arguments, '-RsmRoot')
    if ($Up) { $arguments += '-ForceUp' }
    if ($Down) { $arguments += '-ForceDown' }
    if ($DryRun) { $arguments += '-DryRun' }
    if ($MissingCli) { $arguments[$rsmIndex + 1] = (Join-Path $Case 'missing-rsm') }
    $lock = $null
    if ($LockHeld) {
        $lock = [System.IO.File]::Open((Join-Path $Case 'state/vllm-watchdog.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    }
    try { $text = & $pwsh @arguments 2>&1 | Out-String } finally { if ($lock) { $lock.Dispose() } }
    $result = @{ rc = $LASTEXITCODE; text = $text; calls = @(); log = $log }
    if (Test-Path $log) {
        # Each line is ONE call = one argument array; the unary comma stops PowerShell from
        # unrolling that array into the pipeline (which made two calls count as N arguments).
        $result.calls = @(Get-Content $log | ForEach-Object { ,($_ | ConvertFrom-Json) })
    }
    return $result
}

function Get-Value {
    param($Call, [string]$Name)
    return [string]$Call[[Array]::IndexOf($Call, $Name) + 1]
}

function Assert-NoDriveWrite {
    param($Result)
    # The only Add-Content left must target the local log, never a dashboard file.
    $source = Get-Content $script -Raw
    $driveWrites = [regex]::Matches($source, '(?m)^\s*Add-Content\s+-Path\s+([^\s]+)') |
        ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -ne '$logFile' }
    Assert-True ($driveWrites.Count -eq 0) 'the source has no raw Add-Content outside the local log'
    Assert-True (-not ($source -match '\$Dashboard(Vllm|Global)')) 'the source has no Drive dashboard path parameter'
    Assert-True ((Get-Content $script | Select-String 'Add-Content').Count -ge 1) 'the source assertion is not vacuous'
}

# 1. Dry-run composes the alert but never calls the CLI or changes state.
$case = New-Case 'quiet-up' -State 'up'
$r = Invoke-Watchdog $case -Up
Assert-True ($r.rc -eq 0) 'a quiet UP engine exits zero'
Assert-True ($r.calls.Count -eq 0) 'a quiet UP engine posts no recovery'

$case = New-Case 'dry-run' -ReAlert
$before = (Get-FileHash (Join-Path $case 'state/vllm-watchdog-state.json')).Hash
$r = Invoke-Watchdog $case -Down -DryRun
Assert-True ($r.rc -in 1, 2) "dry-run keeps the DOWN exit code, got $($r.rc)"
Assert-True ($r.calls.Count -eq 0) 'dry-run calls no CLI'
Assert-True ((Get-FileHash (Join-Path $case 'state/vllm-watchdog-state.json')).Hash -eq $before) 'dry-run preserves state'
Assert-True ($r.text -match 'DRY-RUN dashboard=workspace:vllm') 'dry-run names the workspace target'
Assert-True ($r.text -match 'DRY-RUN dashboard=global') 'dry-run names the global target'
Assert-True (-not (Test-Path (Join-Path $case 'state/vllm-watchdog-undelivered.jsonl'))) 'dry-run creates no undelivered queue'
Assert-NoDriveWrite $r

# 2. DOWN posts once to each destination with the same stable incident id.
# New-Case has lastAlert='' and a months-old since, so the first alert is a re-alert
# (id -down-kN), not a first DOWN: that id must be identical on both destinations and
# on a later pass with a different history. The fresh-down case is covered by case 2b.
$case = New-Case 'down-ok'
Set-FakeCli $case 'ok'
$r = Invoke-Watchdog $case -Down
$r = Invoke-Watchdog $case -Down  # cooldown: no duplicate first alert
Assert-True ($r.rc -in 1, 2) 'DOWN keeps its engine exit code'
Assert-True ($r.calls.Count -eq 2) 'DOWN posts exactly twice'
$id = Get-Value $r.calls[0] '--message-id'
Assert-True ($id -match "^vllm-watchdog-$machine-20260101T000000000Z-down-k\d+$") 're-alert id is derived from the persisted down start'
Assert-True ((Get-Value $r.calls[0] '--dashboard') -eq 'workspace:vllm') 'workspace target'
Assert-True ((Get-Value $r.calls[1] '--dashboard') -eq 'global') 'global target'
Assert-True ((Get-Value $r.calls[0] '--message-id') -eq $id) 'stable DOWN id'
Assert-True ((Get-Value $r.calls[1] '--message-id') -eq $id) 'same DOWN id on both destinations'
Assert-True ((Get-Value $r.calls[0] '--author-workspace') -eq 'vllm-watchdog') 'author workspace'
Assert-True ((Get-Value $r.calls[0] '--content') -match '^\[ERROR\]') 'CLI requires an [ERROR]-prefixed body'
Assert-True (@(Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.jsonl') -ErrorAction SilentlyContinue).Count -eq 0) 'no pending line after full delivery'
Assert-NoDriveWrite $r

# 3. Partial delivery is retried with the SAME id and removes only the accepted line.
$case = New-Case 'partial-retry'
Set-FakeCli $case 'workspace-fails'
$r = Invoke-Watchdog $case -Down
Assert-True ($r.calls.Count -eq 2) 'both destinations are attempted despite a failure'
$pendingPath = Join-Path $case 'state/vllm-watchdog-undelivered.jsonl'
Assert-True (Test-Path $pendingPath) 'failed post is retained locally'
$pending = @(Get-Content $pendingPath | ForEach-Object { $_ | ConvertFrom-Json })
Assert-True ($pending.Count -eq 1) 'only the failed destination is queued'
Assert-True ($pending[0].messageId -eq $id) 'queue preserves the id'
Set-FakeCli $case 'ok'
$r = Invoke-Watchdog $case -Down -Mode ok
Assert-True ($r.calls.Count -eq 3) 'retry adds one call, not two new alerts'
Assert-True ((Get-Value $r.calls[2] '--dashboard') -eq 'workspace:vllm') 'only the failed destination is retried'
Assert-True ((Get-Value $r.calls[2] '--message-id') -eq $id) 'retry keeps the same id'
Assert-True (@(Get-Content $pendingPath).Count -eq 0) 'accepted retry empties the queue'
Assert-NoDriveWrite $r

# 4. Recovery delivery failure is logged but the UP engine keeps exit 0, then replay.
$case = New-Case 'recovery-retry'
Set-FakeCli $case 'workspace-fails'
$r = Invoke-Watchdog $case -Up
$restoreId = "vllm-watchdog-$machine-20260101T000000000Z-restored"
Assert-True ($r.rc -eq 0) 'an UP engine keeps exit 0 even with an undelivered recovery'
Assert-True ($r.text -match 'ALERT DELIVERY INCOMPLETE') 'the undelivered recovery is loud in the local log'
Assert-True ((Get-Value $r.calls[0] '--message-id') -eq $restoreId) 'stable recovery id'
Assert-True ((Get-Value $r.calls[0] '--content') -match '^\[DONE\]') 'CLI requires a [DONE]-prefixed body'
Assert-True ((Get-Content (Join-Path $case 'state/vllm-watchdog-state.json') -Raw | ConvertFrom-Json).state -eq 'up') 'recovery still records UP'
Set-FakeCli $case 'ok'
$r = Invoke-Watchdog $case -Up -Mode ok
Assert-True ($r.rc -eq 0) 'a completed retry on an UP engine exits zero'
Assert-True ($r.calls.Count -eq 3) 'only the missing recovery is replayed'
Assert-True ((Get-Value $r.calls[2] '--message-id') -eq $restoreId) 'recovery retry keeps its id'
Assert-True (@(Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.jsonl')).Count -eq 0) 'recovery queue drained'
Assert-NoDriveWrite $r

# 5. An absent CLI cannot silently lose the alert or write to Drive.
$case = New-Case 'missing-cli'
$r = Invoke-Watchdog $case -Up -MissingCli
Assert-True ($r.rc -eq 0) 'UP engine keeps exit 0 when the CLI is missing'
Assert-True ($r.text -match 'ALERT DELIVERY INCOMPLETE') 'a missing CLI is a loud delivery failure'
Assert-True ($r.calls.Count -eq 0) 'missing CLI calls nothing'
Assert-True ($r.text -match 'Dashboard CLI introuvable') 'the local log names the failure'
$queued = @(Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.jsonl'))
Assert-True ($queued.Count -eq 2) 'both destinations are preserved for replay'
$r = Invoke-Watchdog $case -Up -DryRun
Assert-True (@(Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.jsonl')).Count -eq 2) 'dry-run does not drain a real pending queue'
Assert-NoDriveWrite $r

# 6. A Drive-only post (exit 0 but pgSynced=false) remains queued and returns 5.
$case = New-Case 'pg-unsynced'
Set-FakeCli $case 'pg-unsynced'
$r = Invoke-Watchdog $case -Down
Assert-True ($r.rc -eq 5) 'PG-unsynced DOWN alert forces delivery exit 5'
Assert-True (@(Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.jsonl')).Count -eq 2) 'Drive-only posts are not acknowledged'
$r = Invoke-Watchdog $case -Down -Mode ok
Assert-True ($r.rc -eq 1) 'a delivered retry restores the DOWN engine exit'
Assert-True (@(Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.jsonl')).Count -eq 0) 'PG-confirmed retry drains the queue'

# 7. A re-alert id comes from persisted state, not the current time.
$case = New-Case 'realert-stable' -ReAlert
Set-FakeCli $case 'workspace-fails'
$r = Invoke-Watchdog $case -Down
$realertId = Get-Value $r.calls[0] '--message-id'
Assert-True ($realertId -ne $id) 'a re-alert has a distinct id'
Assert-True ($r.calls.Count -eq 2) 'the two re-alert destinations are attempted'
$r = Invoke-Watchdog $case -Down
Assert-True ($r.calls.Count -eq 3) 'a failed re-alert retries, without minting a new alert'
Assert-True ((Get-Value $r.calls[2] '--message-id') -eq $realertId) 'the same re-alert survives a failed attempt'
Assert-True ((Get-Value $r.calls[2] '--dashboard') -eq 'workspace:vllm') 'only the destination that failed is replayed'
$r = Invoke-Watchdog $case -Down -Mode ok
Assert-True (@(Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.jsonl')).Count -eq 0) 'confirmed re-alert retry drains the queue'

# 8. An unreadable journal line is quarantined, it never freezes the state machine.
$case = New-Case 'corrupt-journal'
Set-FakeCli $case 'workspace-fails'
$pendingPath = Join-Path $case 'state/vllm-watchdog-undelivered.jsonl'
$good = @{ dashboard = 'global'; body = '[DONE] **[WATCHDOG] test**'; messageId = "$id-restored" } | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText($pendingPath, "{`n$good`n", [System.Text.UTF8Encoding]::new($false))
$r = Invoke-Watchdog $case -Up
Assert-True ($r.rc -eq 0) 'an UP engine with an undelivered line keeps exit 0'
Assert-True ($r.text -match 'ALERT DELIVERY INCOMPLETE') 'the undelivered line is loud in the local log'
Assert-True ((Get-Content (Join-Path $case 'state/vllm-watchdog-state.json') -Raw | ConvertFrom-Json).state -eq 'up') 'a corrupt line does not freeze the state at down'
Assert-True ((Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.corrupt.jsonl')).Count -eq 1) 'the unreadable line is quarantined once'
Assert-True (@(Get-Content $pendingPath).Count -eq 1) 'only the deliverable line remains queued'
$r = Invoke-Watchdog $case -Up
Assert-True ((Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.corrupt.jsonl')).Count -eq 1) 'quarantine is idempotent across runs'
$r = Invoke-Watchdog $case -Up -Mode ok
Assert-True (@(Get-Content $pendingPath).Count -eq 0) 'a later healthy run drains the deliverable line'
Assert-True ((Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.corrupt.jsonl')).Count -eq 1) 'the quarantined line is preserved, not deleted'

# 9. Delivery failure while UP keeps the engine exit code 0 and still queues RESTAURE.
$case = New-Case 'replay-up-cli-down'
Set-FakeCli $case 'workspace-fails'
$r = Invoke-Watchdog $case -Up
Assert-True ($r.rc -eq 0) 'UP engine keeps exit 0 even with an undelivered RESTAURE'
Assert-True (@($r.calls | Where-Object { (Get-Value $_ '--dashboard') -eq 'global' }).Count -eq 1) 'the global destination was accepted'
Assert-True (@(Get-Content (Join-Path $case 'state/vllm-watchdog-undelivered.jsonl')).Count -eq 1) 'the failed destination stays queued'
$r = Invoke-Watchdog $case -Up
Assert-True ($r.rc -eq 0) 'a second failing run still reports UP'
Assert-True ((Get-Content (Join-Path $case 'state/vllm-watchdog-state.json') -Raw | ConvertFrom-Json).state -eq 'up') 'state machine ran despite the pending queue'

# 10. An id already present is accepted (id-bearing file-only messages are re-injected by the store).
$case = New-Case 'deduplicated'
Set-FakeCli $case 'deduplicated'
$r = Invoke-Watchdog $case -Up
Assert-True ($r.rc -eq 0) 'a deduplicated reply is an accepted delivery'
Assert-True ($r.text -match 'identifiant deja present') 'the log distinguishes dedup from a PG sync'

# 11. A held instance lock makes a second run a no-op, without touching the queue.
$case = New-Case 'instance-lock'
Set-FakeCli $case 'ok'
$r = Invoke-Watchdog $case -Up -LockHeld
Assert-True ($r.rc -eq 0) 'an ignored run exits zero'
Assert-True ($r.calls.Count -eq 0) 'an ignored run posts nothing'
Assert-True ($r.text -match 'Autre instance en cours') 'the skip is logged, not silent'
Assert-True ((Get-Content (Join-Path $case 'state/vllm-watchdog-state.json') -Raw | ConvertFrom-Json).state -eq 'down') 'an ignored run does not rewrite state'

# 12. The incident id survives the en-US / fr-FR culture round-trip of a persisted state.
$case = New-Case 'culture-roundtrip'
Set-FakeCli $case 'ok'
$previousCulture = [Threading.Thread]::CurrentThread.CurrentCulture
try {
    [Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::GetCultureInfo('fr-FR')
    $r = Invoke-Watchdog $case -Up
    $frId = Get-Value $r.calls[0] '--message-id'
    $r = Invoke-Watchdog $case -Up
    Assert-True ((Get-Value $r.calls[0] '--message-id') -eq $frId) 'a retry under fr-FR keeps the incident id'
} finally { [Threading.Thread]::CurrentThread.CurrentCulture = $previousCulture }
Assert-True ($frId -eq $restoreId) 'the fr-FR id equals the en-US id (no UTC/local drift)'

# 13. A FRESH down past its grace (lastAlert still empty) uses the plain -down id.
$case = New-Case 'fresh-down'
Set-FakeCli $case 'ok'
$freshSince = [DateTime]::UtcNow.AddMinutes(-25).ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
[System.IO.File]::WriteAllText((Join-Path $case 'state/vllm-watchdog-state.json'),
    ('{"state":"down","since":"' + $freshSince + '","lastAlert":"","mode":"stack-present"}'), [System.Text.UTF8Encoding]::new($false))
$r = Invoke-Watchdog $case -Down
Assert-True ($r.calls.Count -eq 2) 'both destinations receive the first alert'
$freshId = Get-Value $r.calls[0] '--message-id'
Assert-True ($freshId -match '^vllm-watchdog-[a-z0-9.-]+-\d{8}T\d{9}Z-down$') 'a fresh down carries the plain -down id'
$r = Invoke-Watchdog $case -Down
Assert-True ($r.calls.Count -eq 2) 'the cooldown prevents a duplicate once lastAlert is recorded'

Write-Host "PASS: $script:passed assertions; scratch=$runRoot"
