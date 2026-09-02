<#
.SYNOPSIS
    Watchdog host-side du stack vLLM prod (ai-01, GPUs 0,1, port 5002).
    ALERT-ONLY : detection + alerte dashboard, AUCUNE remediation.

.DESCRIPTION
    Pourquoi un watcher EXTERNE au stack : le 2026-09-02 (~14:20-15:30Z) les 3
    conteneurs myia_vllm-* ont ete SUPPRIMES (compose down ou equivalent) —
    restart policy et watchdog v5 (sidecar du meme stack) ne peuvent pas
    relever ce qui n'existe plus : le down emporte le watcher avec le moteur.
    34 min d'outage sans aucune alerte automatique. Ce script, hors du stack,
    ferme la breche de detection. Modele : embedding_watchdog.ps1 (ai-01).

    Verifie toutes les 5 min (schtask Watchdog-vLLM-API) :
      1) Sante moteur : http://localhost:5002/health (200 = UP)
      2) Existence du stack : au moins un conteneur nomme myia_vllm-*
         (docker ps -a) — distingue "engine qui boote / crash-loop" de
         "stack supprime".

    Machine a etats (state.json) avec graces patient-boot :
      UP                    : silencieux
      DOWN + stack present  : BOOT/HANG — alerte seulement apres
                              BootGraceMinutes (20 min : couvre un boot chaud
                              ~5 min, un restart watchdog v5 ~11 min ; aligne
                              sur start_period 1800s du profil)
      DOWN + stack ABSENT   : REMOVAL — alerte apres AbsentGraceMinutes
                              (15 min : couvre le reboot machine -> Docker
                              Desktop autostart -> boot engine ~10 min, et le
                              gap d'un swap de profil d'eval ~5 min ; le
                              depot du stack par un operateur est legitime,
                              l'alerte est informative)
      DOWN -> UP            : alerte [DONE] recovery (duree du down)
      Re-alerte bornee      : cooldown ReAlertMinutes (60 min)

    Fenetres d'eval connues (benignes) : swap de profil (ornith15 etc.) =
      stack ABSENT < 15 min puis un autre conteneur myia_vllm-* sert :5002.
      L'alerte ABSENT persistante (> 15 min) = vrai incident (removal ou
      swap pendu).

    Dashboards : append direct format roosync (### [ISO] machine|workspace)
      sur workspace-vllm.md + global.md (G:). NB 2026-09-02 : le canal MCP
      roosync_dashboard peut stall 12 min sur GDrive post-reboot ; l'ecriture
      directe du fichier est le mecanisme de reference des watchers host-side
      (cf. embedding_watchdog.ps1, race avec la condensation acceptee).

.NOTES
    Codes sortie : 0 = UP · 1 = DOWN stack present · 2 = DOWN stack absent ·
    3 = docker CLI injoignable (traite absent) · 124 = self-timeout.

.EXAMPLE
    .\vllm_watchdog.ps1                       # run normal (schtask 5 min)
    .\vllm_watchdog.ps1 -ForceDown -DryRun    # simule, n'ecrit rien
#>

[CmdletBinding()]
param(
    [string]$HealthUrl         = 'http://localhost:5002/health',
    [string]$ContainerGlob     = 'myia_vllm-',
    [string]$StateDir          = 'C:\ProgramData\maint-scripts\logs',
    [string]$DashboardVllm     = 'G:\Mon Drive\Synchronisation\RooSync\.shared-state\dashboards\workspace-vllm.md',
    [string]$DashboardGlobal   = 'G:\Mon Drive\Synchronisation\RooSync\.shared-state\dashboards\global.md',
    [string]$MachineId         = '',
    [string]$WorkspaceId       = 'vllm-watchdog',
    [int]$HttpTimeoutSeconds   = 10,
    [int]$SelfTimeoutSeconds   = 60,
    [int]$BootGraceMinutes     = 20,
    [int]$AbsentGraceMinutes   = 15,
    [int]$ReAlertMinutes       = 60,
    [switch]$ForceDown,
    [switch]$ForceUp,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($MachineId)) { $MachineId = $env:COMPUTERNAME.ToLowerInvariant() }

if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Path $StateDir -Force | Out-Null }
$logFile   = Join-Path $StateDir "vllm-watchdog.log"
$stateFile = Join-Path $StateDir "vllm-watchdog-state.json"

# --- Self-timeout : un docker CLI hang (daemon mort) ne doit pas bloquer la schtask ---
if ($SelfTimeoutSeconds -gt 0) {
    try {
        Add-Type -TypeDefinition @"
using System; using System.Threading; using System.IO;
public static class VllmWatchdogSelfTimeout {
    public static void Arm(int ms, string logPath, int exitCode) {
        Thread t = new Thread(() => {
            Thread.Sleep(ms);
            try { File.AppendAllText(logPath, "["+DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")+"] [ERROR] SELF-TIMEOUT "+(ms/1000)+"s exceeded, force-exit "+exitCode+"\n"); } catch {}
            Environment.Exit(exitCode);
        });
        t.IsBackground = true; t.Start();
    }
}
"@ -ErrorAction Stop
        [VllmWatchdogSelfTimeout]::Arm($SelfTimeoutSeconds * 1000, $logFile, 124)
    } catch {
        Add-Content -Path $logFile -Value ("[{0}] [WARN] self-timeout arm failed: {1}" -f (Get-Date -f "yyyy-MM-dd HH:mm:ss"), $_.Exception.Message) -Encoding UTF8
    }
}

function Log {
    param([string]$msg, [string]$lvl = "INFO")
    $line = "[{0}] [{1}] {2}" -f (Get-Date -f "yyyy-MM-dd HH:mm:ss"), $lvl, $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Probe-Http {
    param([string]$Url)
    $code = 000; $ms = -1
    try {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $r = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec $HttpTimeoutSeconds -SkipHttpErrorCheck -MaximumRedirection 0 -ErrorAction Stop
        $sw.Stop()
        $code = [int]$r.StatusCode; $ms = $sw.ElapsedMilliseconds
    } catch { $sw.Stop(); $ms = $sw.ElapsedMilliseconds }
    return @{ code = $code; ms = $ms }
}

# Retourne $true si au moins un conteneur myia_vllm-* existe (running OU exited).
# Echec docker CLI => $false + flag pour qualifier (daemon Docker lui-meme down).
function Test-StackPresent {
    try {
        $names = & docker ps -a --filter "name=$ContainerGlob" --format '{{.Names}}' 2>$null
        if ($LASTEXITCODE -ne 0) { return @{ present = $false; dockerOk = $false } }
        return @{ present = @($names).Count -gt 0; dockerOk = $true }
    } catch { return @{ present = $false; dockerOk = $false } }
}

function Get-DateTimeValue {
    param($Value)
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace($Value)) { return $null }
    if ($Value -isnot [datetime]) {
        $Value = [datetime]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
    }
    if ($Value.Kind -eq [DateTimeKind]::Local) { return $Value.ToUniversalTime() }
    if ($Value.Kind -eq [DateTimeKind]::Unspecified) { return [datetime]::SpecifyKind($Value, [DateTimeKind]::Utc) }
    return $Value
}

function Read-State {
    if (Test-Path $stateFile) {
        try { return (Get-Content $stateFile -Raw | ConvertFrom-Json) } catch { }
    }
    return @{ state = 'up'; since = ''; lastAlert = ''; mode = '' }
}

function Write-State {
    param($State)
    if ($DryRun) { return }  # un test DryRun ne doit pas polluer l'etat reel (sinon faux recovery au run suivant)
    $State | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8
}

function Append-Dashboard {
    param([string]$Path, [string]$Body)
    if ($DryRun) { return }
    if (-not (Test-Path $Path)) { Log "Dashboard introuvable, skip: $Path" "WARN"; return }
    $header = "### [$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ'))] $MachineId|$WorkspaceId"
    Add-Content -Path $Path -Value ("`n$header`n`n$Body`n") -Encoding UTF8
    Log "Alert dashboard: $Path"
}

# ========== PROBES ==========
Log "Run start (ForceDown=$ForceDown ForceUp=$ForceUp DryRun=$DryRun)"

$h = Probe-Http $HealthUrl
$stack = Test-StackPresent
$engineUp = ($h.code -ge 200 -and $h.code -lt 300)

if ($ForceUp)   { $engineUp = $true;  $h = @{ code = 200; ms = 0 } }
if ($ForceDown) { $engineUp = $false; $h = @{ code = 000; ms = -1 } }

$mode = if (-not $stack.dockerOk) { 'docker-down' }
        elseif ($stack.present)   { 'stack-present' }
        else                      { 'stack-absent' }

if ($engineUp) { $exitCode = 0 }
elseif ($mode -eq 'stack-present') { $exitCode = 1 }
else { $exitCode = 2 }

Log ("Probe: health={0}/{1}ms stack={2} docker={3} mode={4} -> {5} (exit={6})" -f $h.code, $h.ms, $stack.present, $stack.dockerOk, $mode, $(if ($engineUp) {'UP'} else {'DOWN'}), $exitCode)

# ========== STATE MACHINE ==========
$st = Read-State
$now = [DateTime]::UtcNow
$iso = $now.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')

if ($exitCode -eq 0) {
    if ($st.state -eq 'down') {
        Log "Transition DOWN -> UP. Post recovery." "INFO"
        $downSince = Get-DateTimeValue $st.since
        $downMin = if ($downSince) { [Math]::Round((($now - $downSince).TotalMinutes)) } else { '?' }
        $body = @"
**[DONE][WATCHDOG] vLLM :5002 RESTAURE (health $($h.code))**
- Probe: health=$($h.code)/$($h.ms)ms
- Down depuis $($st.since) (mode $($st.mode)) — duree: $downMin min
— $MachineId vllm_watchdog.ps1
"@
        Append-Dashboard $DashboardVllm $body
        Append-Dashboard $DashboardGlobal $body
    }
    Write-State @{ state = 'up'; since = ''; lastAlert = ''; mode = $mode }
    Log "State UP. No alert." "INFO"
    exit 0
}

# --- DOWN : graces patient-boot avant premiere alerte ---
$sinceStr = if ($st.since) { $st.since } else { $iso }
$downSince = Get-DateTimeValue $sinceStr
$downMin = if ($downSince) { ($now - $downSince).TotalMinutes } else { 0 }
$grace = if ($mode -eq 'stack-present') { $BootGraceMinutes } else { $AbsentGraceMinutes }
$isNewDown = ($st.state -ne 'down')

if ($isNewDown) {
    Write-State @{ state = 'down'; since = $iso; lastAlert = ''; mode = $mode }
    Log "DOWN (mode=$mode). Grace $grace min avant alerte (depuis $iso)." "WARN"
    exit $exitCode
}

# Down persistant : premiere alerte si grace passee, sinon re-alerte cooldown
$alertNow = $false
if ($downMin -ge $grace -and -not $st.lastAlert) { $alertNow = $true }
elseif ($st.lastAlert) {
    $last = Get-DateTimeValue $st.lastAlert
    $elapsed = if ($last) { ($now - $last).TotalMinutes } else { [double]::MaxValue }
    if ($elapsed -ge $ReAlertMinutes) { $alertNow = $true }
}

if ($alertNow) {
    $ctx = if ($mode -eq 'stack-present') {
        "stack PRESENT (conteneurs myia_vllm-* visibles) — boot long, crash-loop ou hang moteur (le watchdog v5 in-stack gere le restart ; alerte = redondance de detection externe)"
    } elseif ($mode -eq 'docker-down') {
        "docker CLI INJOIGNABLE — Docker Desktop probablement mort (tout le host Docker est down)"
    } else {
        "stack ABSENT (aucun conteneur myia_vllm-*) — REMOVAL (compose down / docker rm) ou swap de profil pendu. NB : un swap d'eval legitime dure < 15 min ; une absence persistante = incident (cas 2026-09-02 : 34 min muettes). AUCUNE action auto."
    }
    $body = @"
**[ERROR][WATCHDOG] vLLM :5002 DOWN (health $($h.code)) — mode $mode**
- Probe: health=$($h.code)/$($h.ms)ms · $ctx
- Down depuis: $sinceStr ($([Math]::Round($downMin)) min)
- Action RECOMMANDEE (ce watcher n'execute RIEN) : verifier `docker ps -a --filter name=myia_vllm-` puis si absent `docker compose -f d:\vllm\myia_vllm\configs\docker\profiles\medium-qwen36-stock-tq.yml --env-file d:\vllm\myia_vllm\.env up -d` (prod). Si GPU 0/1 a 0 MiB + erreurs CUDA : voir pattern 08-31 (MAJ driver + reboot).
- Re-alerte auto dans $ReAlertMinutes min si persiste
— $MachineId vllm_watchdog.ps1
"@
    Append-Dashboard $DashboardVllm $body
    Append-Dashboard $DashboardGlobal $body
    Write-State @{ state = 'down'; since = $sinceStr; lastAlert = $iso; mode = $mode }
    Log "ALERT posted (exit=$exitCode, mode=$mode)." "ERROR"
} else {
    Write-State @{ state = 'down'; since = $sinceStr; lastAlert = $st.lastAlert; mode = $mode }
    Log "DOWN persistant (mode=$mode, $([Math]::Round($downMin)) min), grace $grace min passee=$($downMin -ge $grace), cooldown actif. Silence." "WARN"
}

exit $exitCode
