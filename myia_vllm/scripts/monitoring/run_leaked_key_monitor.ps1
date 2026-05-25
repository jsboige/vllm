<#
.SYNOPSIS
    Hourly wrapper for the leaked medium API key monitor (scheduled-task entry point).

.DESCRIPTION
    1. Rotates logs/error_sources.jsonl when it grows past a size cap (the capture
       middleware opens the file per-write in append mode, so a host-side rename is
       safe: the next request recreates a fresh error_sources.jsonl). Old archives
       are gzip'd and pruned after a retention window.
    2. Runs leaked_key_monitor.py (incremental scan; persists high-water + seen IPs).
    3. On exit code 2 (a genuinely NEW unauthorized public IP, or a volume spike),
       launches a headless `claude -p` session that posts the dashboard-ready alert
       (written by the monitor to logs/leaked_key_last_alert.md, UTF-8) VERBATIM to
       the two roosync dashboards, SEQUENTIALLY:
         1) workspace-roo-extensions   2) workspace-cluster-coordination
       Sequential is mandatory: both live on the same shared GDrive folder and
       concurrent .tmp->.md renames collide (ENOENT).
    4. Appends an audit line to logs/leaked_key_monitor_runs.log every run.

    Standing decision: MONITORING ONLY. Never rotate the leaked API key.

.NOTES
    All string literals here are ASCII so the file is safe to read under both
    Windows PowerShell 5.1 and PowerShell 7 with no BOM. Any French/accented text
    is confined to leaked_key_last_alert.md, which Claude reads directly as UTF-8.
#>
param(
    [int]$RotateSizeMB = 100,    # rotate error_sources.jsonl above this size
    [int]$ArchiveRetentionDays = 90,
    [switch]$NoEscalate,         # run the monitor + rotation but never call claude
    [string]$TestWorkspace,      # validation: post only to this one workspace (not prod)
    [switch]$ForceEscalate       # validation: run the relay even when exit code != 2
)

$ErrorActionPreference = 'Stop'

# --- Paths (resolved relative to this script: myia_vllm/scripts/monitoring/) ---
$Here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$MyiaVllm = (Resolve-Path (Join-Path $Here '..\..')).Path
$LogDir   = Join-Path $MyiaVllm 'logs'
$Monitor  = Join-Path $Here 'leaked_key_monitor.py'
$ErrLog   = Join-Path $LogDir 'error_sources.jsonl'
$ArchDir  = Join-Path $LogDir 'archive'
$LastAlert= Join-Path $LogDir 'leaked_key_last_alert.md'
$RunsLog  = Join-Path $LogDir 'leaked_key_monitor_runs.log'

function Write-RunLog([string]$msg) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $line  = "[$stamp] $msg"
    [System.IO.File]::AppendAllText($RunsLog, $line + "`n", [System.Text.UTF8Encoding]::new($false))
    Write-Host $line
}

function Resolve-Exe([string[]]$candidates) {
    foreach ($c in $candidates) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

# --- 1. Rotate error_sources.jsonl if oversized -------------------------------
try {
    if (Test-Path $ErrLog) {
        $sizeMB = [math]::Round((Get-Item $ErrLog).Length / 1MB, 1)
        if ($sizeMB -ge $RotateSizeMB) {
            if (-not (Test-Path $ArchDir)) { New-Item -ItemType Directory -Path $ArchDir | Out-Null }
            $tag  = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
            $dest = Join-Path $ArchDir "error_sources-$tag.jsonl"
            Move-Item -LiteralPath $ErrLog -Destination $dest    # next request recreates ErrLog
            try {
                $gz = "$dest.gz"
                $in = [System.IO.File]::OpenRead($dest)
                $out = [System.IO.File]::Create($gz)
                $gzs = New-Object System.IO.Compression.GZipStream($out, [System.IO.Compression.CompressionLevel]::Optimal)
                $in.CopyTo($gzs); $gzs.Dispose(); $out.Dispose(); $in.Dispose()
                Remove-Item -LiteralPath $dest -Force
                Write-RunLog "ROTATE error_sources.jsonl ($sizeMB MB) -> $([System.IO.Path]::GetFileName($gz))"
            } catch {
                Write-RunLog "ROTATE moved to $dest (gzip failed: $($_.Exception.Message))"
            }
            # prune old archives
            Get-ChildItem -Path $ArchDir -Filter 'error_sources-*' -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$ArchiveRetentionDays) } |
                ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
        }
    }
} catch {
    Write-RunLog "ROTATE-ERROR $($_.Exception.Message)"
}

# --- 2. Run the monitor -------------------------------------------------------
$py = Resolve-Exe @('python', 'python3', 'C:\Python314\python.exe', 'C:\Python310\python.exe')
if (-not $py) { Write-RunLog 'FATAL python not found on PATH'; exit 1 }

$monitorOut = & $py $Monitor 2>&1
$code = $LASTEXITCODE
$summary = ($monitorOut | Select-Object -Last 1) -as [string]
Write-RunLog "SCAN exit=$code | $summary"

# --- 3. Escalate only on a new alert (exit code 2) ----------------------------
# Relay = direct stdio MCP client (dashboard_post.cjs) calling the exact
# roosync_dashboard tool. `claude -p` headless was tried first but does NOT expose
# roo-state-manager's tools (heavy skeleton-load startup exceeds the print-session
# MCP init window), so a deterministic, token-free direct client is used instead.
if (($code -eq 2 -or $ForceEscalate) -and -not $NoEscalate) {
    if (-not (Test-Path $LastAlert)) {
        Write-RunLog 'ESCALATE-SKIP no leaked_key_last_alert.md to post'
        exit $code
    }
    $node = Resolve-Exe @('node', 'C:\Program Files\nodejs\node.exe')
    if (-not $node) { Write-RunLog 'ESCALATE-FAIL node not found'; exit $code }
    $poster = Join-Path $Here 'dashboard_post.cjs'

    if ($TestWorkspace) { $wsList = $TestWorkspace }                      # validation
    else { $wsList = 'roo-extensions,cluster-coordination' }              # production targets

    Write-RunLog "ESCALATE (code=$code force=$ForceEscalate) -> posting to: $wsList"
    try {
        $relayOut = & $node $poster --workspace $wsList --content-file $LastAlert --tags 'SECURITY,WARN' 2>&1
        $rc = $LASTEXITCODE
        $tail = ($relayOut | Select-Object -Last 4) -join ' | '
        Write-RunLog "RELAY rc=$rc $tail"
    } catch {
        Write-RunLog "RELAY-ERROR $($_.Exception.Message)"
    }
}

exit $code
