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
         "stack supprime". Interroge seulement moteur DOWN : sur cet hote
         l'appel docker a ete mesure entre 7 et 26 s (24/11), temps que la
         livraison des alertes ne doit pas payer sur un run sain.

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

    Dashboards : CLI deterministe rsm-dashboard-append.mjs (dual-write G: + PG),
      workspace:vllm + global, avec un messageId stable par incident. Aucun agent
      ni canal MCP interactif : un stall MCP ne fait donc pas taire l'alerte.
      Jamais d'append direct sans ID dans les fichiers Drive (#595 / #4131).

    Livraison (#595) — la machine a etats ne depend JAMAIS de la livraison :
      1. l'alerte est ecrite dans un journal local, vllm-watchdog-undelivered.jsonl
         (write-ahead : un kill ne perd rien) ;
      2. l'etat est pose ;
      3. chaque ligne du journal est presentee a la CLI, la plus ancienne
         d'abord (une RESTAURE n'arrive jamais apres le DOWN suivant).
      Une ligne ne sort du journal qu'apres confirmation de la CLI : exit 0,
      ok:true, et PG synchronise OU identifiant deja present. Un identifiant
      deja present n'est pas une perte : le magasin reinjecte dans la vue tout
      message file-only qui porte un identifiant (dashboard.js, STALE-FILE
      #3230) ; seuls les blocs SANS identifiant restent orphelins du PG.
      Ligne illisible : isolee dans vllm-watchdog-undelivered.corrupt.jsonl,
      jamais laissee en tete de file (elle figeait le watchdog entrier).

    Run borne par la tache planifiee elle-meme : ExecutionTimeLimit PT1M. Le
      self-timeout du script reste donc SOUS 60 s, pour que ce soit lui qui
      conclue (code 124 trace dans le log) et non une coupature muette.

.NOTES
    Codes sortie : 0 = UP (ou re-alerte deja partie sur au moins une destination) ·
    1 = DOWN stack present · 2 = DOWN stack absent ou docker CLI injoignable ·
    5 = DOWN et alerte entierement non livree (etat moteur dans la ligne
    "ALERT DELIVERY INCOMPLETE") · 124 = self-timeout. Un seul run a la fois :
    verrou vllm-watchdog.lock.

.EXAMPLE
    .\vllm_watchdog.ps1                       # run normal (schtask 5 min)
    .\vllm_watchdog.ps1 -ForceDown -DryRun    # simule, n'ecrit rien
#>

[CmdletBinding()]
param(
    [string]$HealthUrl         = 'http://localhost:5002/health',
    [string]$ContainerGlob     = 'myia_vllm-',
    [string]$StateDir          = 'C:\ProgramData\maint-scripts\logs',
    [string]$RsmRoot           = '',
    [string]$NodePath          = '',
    [string]$MachineId         = '',
    [string]$WorkspaceId       = 'vllm-watchdog',
    [int]$HttpTimeoutSeconds   = 10,
    [int]$SelfTimeoutSeconds   = 55,
    [int]$BootGraceMinutes     = 20,
    [int]$AbsentGraceMinutes   = 15,
    [int]$ReAlertMinutes       = 60,
    [switch]$ForceDown,
    [switch]$ForceUp,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$script:RunStarted = [DateTime]::UtcNow
if ([string]::IsNullOrWhiteSpace($MachineId)) { $MachineId = $env:COMPUTERNAME.ToLowerInvariant() }
if ([string]::IsNullOrWhiteSpace($RsmRoot)) {
    $RsmRoot = if ($env:RSM_SERVER_ROOT) { $env:RSM_SERVER_ROOT } else { 'D:\roo-extensions\mcps\internal\servers\roo-state-manager' }
}
# Borne d'ecriture G: de la CLI (UNIFIED_STORE_DASHBOARD_GDRIVE_WRITE_TIMEOUT_MS, defaut 30 s).
$cliWriteBoundSeconds = 30

if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Path $StateDir -Force | Out-Null }
$logFile     = Join-Path $StateDir "vllm-watchdog.log"
$stateFile   = Join-Path $StateDir "vllm-watchdog-state.json"
$alertFile   = Join-Path $StateDir "vllm-watchdog-undelivered.jsonl"
$corruptFile = Join-Path $StateDir "vllm-watchdog-undelivered.corrupt.jsonl"
$lockFile    = Join-Path $StateDir "vllm-watchdog.lock"
$script:Undelivered = $false
$script:PostDelivered = @{}

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

# Ecriture atomique (temporaire puis remplacement) : un kill en pleine ecriture ne
# laisse ni journal ni etat tronques.
function Write-TextAtomic {
    param([string]$Path, [string]$Text)
    $tmp = "$Path.tmp"
    [System.IO.File]::WriteAllText($tmp, $Text, [System.Text.UTF8Encoding]::new($false))
    # Ecriture atomique par rename avec ecrasement (.NET Core) : pas de partage
    # Delete requis, donc le verrou d'instance peut rester exclusif (FileShare.None).
    [System.IO.File]::Move($tmp, $Path, $true)
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
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) { return $null }
    if ($Value -isnot [datetime]) {
        $Value = [datetime]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
    }
    if ($Value.Kind -eq [DateTimeKind]::Unspecified) {
        # Un `DateTime` Kind=Utc re-converti en texte (ConvertFrom-Json puis [string])
        # perd son suffixe : on le relit donc en UTC explicite, pas en heure locale.
        return [datetime]::SpecifyKind($Value, [DateTimeKind]::Utc)
    }
    return $Value.ToUniversalTime()
}

function Read-State {
    if (Test-Path $stateFile) {
        try { return (Get-Content $stateFile -Raw | ConvertFrom-Json) } catch {
            Log "Etat illisible ($stateFile), traite comme UP tant que la sonde ne dit pas le contraire." "WARN"
        }
    }
    return @{ state = 'up'; since = ''; lastAlert = ''; mode = '' }
}

function Write-State {
    param($State)
    if ($DryRun) { return }  # un test DryRun ne doit pas polluer l'etat reel (sinon faux recovery au run suivant)
    Write-TextAtomic $stateFile ((($State | ConvertTo-Json) + "`n"))
}

function Get-IncidentId {
    param($Since)   # DateTime ou texte ISO : jamais de conversion dependant de la culture
    $parsed = Get-DateTimeValue $Since
    if ($parsed) { $stamp = $parsed.ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ') }
    else {
        $text = if ($null -ne $Since) { [string]$Since } else { '' }
        $stamp = [regex]::Replace($text, '[^A-Za-z0-9]', '')
        if (-not $stamp) { $stamp = 'unknown' }
    }
    # identifiant CLI : [A-Za-z0-9._:-], <= 128
    $machine = [regex]::Replace($MachineId.ToLowerInvariant(), '[^a-z0-9._:-]', '-')
    return "vllm-watchdog-$machine-$stamp"
}

function Read-PendingAlerts {
    if (-not (Test-Path $alertFile)) { return @() }
    return @(Get-Content $alertFile | Where-Object { $null -ne $_ -and $_.Trim().Length -gt 0 })
}

# Cle d'une ligne du journal. Une ligne illisible ou incomplete recoit une cle a
# elle : aucune reecriture ne peut la faire disparaitre sans qu'on l'ait isolee.
function Get-JournalKey {
    param([string]$Line)
    try { $item = $Line | ConvertFrom-Json } catch { return "unreadable:$Line" }
    if (-not ($item.dashboard -and $item.body -and $item.messageId)) { return "incomplete:$Line" }
    return "$($item.messageId)`n$($item.dashboard)"
}

function Queue-Alert {
    param([string]$Dashboard, [string]$Body, [string]$MessageId)
    if ($DryRun) {
        Log "DRY-RUN dashboard=$Dashboard messageId=$MessageId body=$($Body -replace '\r?\n', ' | ')"
        return
    }
    $lines = @(Read-PendingAlerts | Where-Object { (Get-JournalKey $_) -ne "$MessageId`n$Dashboard" })
    $record = @{ timestamp = [DateTime]::UtcNow.ToString('o'); dashboard = $Dashboard
                 messageId = $MessageId; body = $Body } | ConvertTo-Json -Compress
    Write-TextAtomic $alertFile ((@($lines) + $record) -join "`n")
}

function Read-CliOutcome {
    # Derniere ligne JSON de la sortie CLI (une ligne WARN peut la preceder).
    param([string]$Output)
    foreach ($line in @($Output -split '\r?\n' | Select-Object -Last 6)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try { return $line | ConvertFrom-Json } catch { }
    }
    return $null
}

# Presente UNE ligne du journal a la CLI. $true seulement sur confirmation de
# livraison ; toute autre issue laisse la ligne au journal pour le run suivant.
function Send-Alert {
    param($Item)
    $Dashboard = [string]$Item.dashboard; $Body = [string]$Item.body; $MessageId = [string]$Item.messageId
    $cli = Join-Path $RsmRoot 'scripts\rsm-dashboard-append.mjs'
    if (-not (Test-Path -LiteralPath $cli)) {
        Log "Dashboard CLI introuvable ($cli), alerte conservee dans $alertFile ($MessageId)" "ERROR"
        return $false
    }
    if ($NodePath) {
        $node = $NodePath
    } else {
        $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
        $node = if ($nodeCmd) { $nodeCmd.Source } elseif (Test-Path 'C:\Program Files\nodejs\node.exe') { 'C:\Program Files\nodejs\node.exe' } else { '' }
    }
    if (-not $node) {
        Log "node absent, alerte conservee dans $alertFile ($MessageId)" "ERROR"
        return $false
    }
    try {
        # Jamais d'append Drive sans ID : la CLI porte la transaction duale Drive + PG.
        $stdout = & $node $cli --machine $MachineId --dashboard $Dashboard --message-id $MessageId --author-workspace $WorkspaceId --content $Body 2>&1 | Out-String
        $cliExit = $LASTEXITCODE
    } catch {
        $stdout = $_.Exception.Message
        $cliExit = -1
    }
    $outcome = if ($cliExit -eq 0) { Read-CliOutcome $stdout } else { $null }
    $accepted = $cliExit -eq 0 -and $null -ne $outcome -and $outcome.ok -eq $true -and
                ($outcome.deduplicated -eq $true -or $outcome.pgSynced -eq $true)
    if (-not $accepted) {
        $reason = if ($null -ne $outcome -and $outcome.pgSynced -eq $false) { 'pgSynced=false (le post Drive seul ne suffit pas)' } else { "exit=$cliExit; $($stdout.Trim())" }
        Log "Alerte non livree sur $Dashboard (messageId=$MessageId), conservee dans ${alertFile}: $reason" "ERROR"
        return $false
    }
    $how = if ($outcome.deduplicated -eq $true) { 'identifiant deja present' } else { 'PG synchronise' }
    Log "Alert dashboard: $Dashboard (messageId=$MessageId, $how)"
    return $true
}

# Livre le journal, la plus ancienne ligne d'abord. $true s'il reste une alerte non
# livree ou une ligne isolee : la machine a etats a deja tourne.
function Invoke-AlertDelivery {
    if ($DryRun) { return $false }
    $lines = Read-PendingAlerts
    if ($lines.Count -eq 0) { return $false }
    $deliveredKeys = @{}; $corrupt = @(); $deferred = 0
    foreach ($line in $lines) {
        $key = Get-JournalKey $line
        if ($key.StartsWith('unreadable:') -or $key.StartsWith('incomplete:')) {
            Log "Ligne d'alerte non relisible isolee dans $corruptFile : $($line.Substring(0, [Math]::Min(80, $line.Length)))" "ERROR"
            $corrupt += $line
            continue
        }
        # N'entamer aucun appel que le self-timeout couperait.
        $elapsed = ([DateTime]::UtcNow - $script:RunStarted).TotalSeconds
        if ($SelfTimeoutSeconds -gt 0 -and ($elapsed + $cliWriteBoundSeconds) -ge ($SelfTimeoutSeconds - 5)) {
            $deferred++
            continue
        }
        $item = $line | ConvertFrom-Json
        if (Send-Alert $item) {
            $deliveredKeys[$key] = $true
            $script:PostDelivered["$($item.messageId)|$($item.dashboard)"] = $true
        }
    }
    $remaining = @($lines | Where-Object {
        $k = Get-JournalKey $_
        (-not $deliveredKeys.ContainsKey($k)) -and ($corrupt -notcontains $_)
    })
    if ($corrupt.Count -gt 0) {
        [System.IO.File]::AppendAllText($corruptFile, (($corrupt -join "`n") + "`n"), [System.Text.UTF8Encoding]::new($false))
    }
    if ($remaining.Count -ne $lines.Count) { Write-TextAtomic $alertFile ($remaining -join "`n") }
    if ($deferred -gt 0) { Log "$deferred alerte(s) non presentees ce run (budget de temps), remises au prochain run." "WARN" }
    if ($remaining.Count -gt 0) {
        Log "ALERT DELIVERY INCOMPLETE (engine=$(if ($script:EngineUp) {'UP'} else {'DOWN'})): $($remaining.Count) alerte(s) dans $alertFile" "ERROR"
        return $true
    }
    if ($corrupt.Count -gt 0) { return $true }
    if ($deliveredKeys.Count -gt 0) { Log "Alertes en attente livrees, journal local vide." "INFO" }
    return $false
}

# ========== RUN ==========
# Un seul run a la fois (la schtask est en IgnoreNew ; ceci couvre un run manuel
# qui chevaucherait un run planifie). Partage impossible seul = autre instance.
if (-not $DryRun) {
    $script:InstanceLock = $null
    try {
        # Exclusif : l'ecriture atomique est par rename, sans partage Delete requis.
        $script:InstanceLock = [System.IO.File]::Open($lockFile, 'OpenOrCreate', 'ReadWrite', 'None')
    } catch {
        if ($_.Exception.InnerException -is [System.IO.IOException]) {
            Log "Autre instance en cours (verrou $lockFile) : run ignore." "WARN"
            exit 0
        }
        Log "Verrou d'instance impossible ($lockFile), run sans verrou : $($_.Exception.Message)" "WARN"
    }
}

Log "Run start (ForceDown=$ForceDown ForceUp=$ForceUp DryRun=$DryRun)"

$h = Probe-Http $HealthUrl
$engineUp = ($h.code -ge 200 -and $h.code -lt 300)
if ($ForceUp)   { $engineUp = $true;  $h = @{ code = 200; ms = 0 } }
if ($ForceDown) { $engineUp = $false; $h = @{ code = 000; ms = -1 } }
$script:EngineUp = $engineUp

if ($engineUp) {
    $stack = @{ present = $null; dockerOk = $true }
    $mode = ''; $exitCode = 0
} else {
    $stack = Test-StackPresent
    $mode = if (-not $stack.dockerOk) { 'docker-down' }
            elseif ($stack.present)   { 'stack-present' }
            else                      { 'stack-absent' }
    $exitCode = if ($mode -eq 'stack-present') { 1 } else { 2 }
}
Log ("Probe: health={0}/{1}ms stack={2} docker={3} mode={4} -> {5} (exit={6})" -f $h.code, $h.ms, $stack.present, $stack.dockerOk, $mode, $(if ($engineUp) {'UP'} else {'DOWN'}), $exitCode)

# ========== STATE MACHINE (aucune etape n'attend la livraison) ==========
$st = Read-State
$now = [DateTime]::UtcNow
$iso = $now.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')

if ($engineUp) {
    if ($st.state -eq 'down') {
        Log "Transition DOWN -> UP. Post recovery." "INFO"
        $downSince = Get-DateTimeValue $st.since
        $downMin = if ($downSince) { [Math]::Round((($now - $downSince).TotalMinutes)) } else { '?' }
        $sinceText = if ($downSince) { $downSince.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') } else { [string]$st.since }
        $body = @"
[DONE] **[WATCHDOG] vLLM :5002 RESTAURE (health $($h.code))**
- Probe: health=$($h.code)/$($h.ms)ms
- Down depuis $sinceText (mode $($st.mode)) — duree: $downMin min
— $MachineId vllm_watchdog.ps1
"@
        $messageId = "$(Get-IncidentId $st.since)-restored"
        Queue-Alert 'workspace:vllm' $body $messageId
        Queue-Alert 'global' $body $messageId
    }
    Write-State @{ state = 'up'; since = ''; lastAlert = ''; mode = '' }
    Log "State UP." "INFO"
} else {
    $sinceStr = if ($st.since) { $st.since } else { $iso }
    $downSince = Get-DateTimeValue $sinceStr
    $downMin = if ($downSince) { ($now - $downSince).TotalMinutes } else { 0 }
    $sinceText = if ($downSince) { $downSince.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') } else { [string]$sinceStr }
    $grace = if ($mode -eq 'stack-present') { $BootGraceMinutes } else { $AbsentGraceMinutes }

    if ($st.state -ne 'down') {
        Write-State @{ state = 'down'; since = $iso; lastAlert = ''; mode = $mode }
        Log "DOWN (mode=$mode). Grace $grace min avant alerte (depuis $iso)." "WARN"
    } else {
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
[ERROR] **[WATCHDOG] vLLM :5002 DOWN (health $($h.code)) — mode $mode**
- Probe: health=$($h.code)/$($h.ms)ms · $ctx
- Down depuis: $sinceText ($([Math]::Round($downMin)) min)
- Action RECOMMANDEE (ce watcher n'execute RIEN) : verifier `docker ps -a --filter name=myia_vllm-` puis si absent `docker compose -f d:\vllm\myia_vllm\configs\docker\profiles\medium-qwen36-stock-tq.yml --env-file d:\vllm\myia_vllm\.env up -d` (prod). Si GPU 0/1 a 0 MiB + erreurs CUDA : voir pattern 08-31 (MAJ driver + reboot).
- Re-alerte auto dans $ReAlertMinutes min si persiste
— $MachineId vllm_watchdog.ps1
"@
            $incidentId = Get-IncidentId $sinceStr
            # L'identifiant d'une re-alerte derive de l'alerte PRECEDENTE (etat persiste) :
            # un retry apres crash rejoue le meme id au lieu de creer un doublon. Si cet
            # etat a ete perdu sur une panne deja ancienne, l'indice de re-alerte derive
            # de la date de debut : l'id reste distinct de celui de la premiere alerte,
            # sinon la deduplication de la CLI avalerait la re-alerte.
            $alertKind = 'down'
            if ($st.lastAlert) {
                $previousAlert = Get-DateTimeValue $st.lastAlert
                if ($previousAlert) { $alertKind = "down-r$(([DateTimeOffset]$previousAlert).ToUnixTimeSeconds())" }
            } elseif ($downMin -ge ($grace + $ReAlertMinutes)) {
                $alertKind = 'down-k' + [Math]::Floor(($downMin - $grace) / $ReAlertMinutes)
            }
            Queue-Alert 'workspace:vllm' $body "$incidentId-$alertKind"
            Queue-Alert 'global' $body "$incidentId-$alertKind"
            Write-State @{ state = 'down'; since = $sinceStr; lastAlert = $iso; mode = $mode }
            Log "ALERT queued (exit=$exitCode, mode=$mode)." "ERROR"
        } else {
            Write-State @{ state = 'down'; since = $sinceStr; lastAlert = $st.lastAlert; mode = $mode }
            Log "DOWN persistant (mode=$mode, $([Math]::Round($downMin)) min), grace $grace min passee=$($downMin -ge $grace), cooldown actif. Silence." "WARN"
        }
    }
}

# ========== DELIVERY ==========
if (Invoke-AlertDelivery) {
    if (-not $engineUp) { exit 5 }
    # Une re-alerte dont l'une des deux destinations a ete acceptee EST une alerte
    # emise : exit 0 masquerait une panne moteur aux consommateurs du code de sortie.
    $realertEmitted = @($script:PostDelivered.Keys | Where-Object { $_ -match '-down(-k\d+)?\|' }).Count -gt 0
    if (-not $realertEmitted) { exit 0 }
}
exit $exitCode
