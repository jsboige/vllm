# gpu-thermal-logger-po2025.ps1 - surveillance thermique MONITOR-ONLY, sans UAC (siège po-2025:vllm)
# Comble la mort de la télémétrie thermique (31/08) en attendant le gouverneur SYSTEM
# (gpu-thermal-governor-po2025.ps1, fenêtre UAC unique - cf. registre Q2).
# Tâche : vllm-po2025-thermal-logger (user-level, /5 min, SANS élévation)
# Logs   : myia_vllm/_logs/gpu-thermal.log (+ état json pour hysteresis futur)
# Leçons codées : P0 05/10 - croiser temp x charge (incident avril = 85C a VIDE
# par apps desktop ; jamais la temp seule). Heartbeat horaire = preuve de vie.

$ErrorActionPreference = 'Continue'
$base   = 'D:\dev\vllm\myia_vllm\_logs'
$logDir = $base
$log    = Join-Path $logDir 'gpu-thermal.log'
$stateF = Join-Path $logDir 'gpu-thermal-state.json'
$nsmi   = 'C:\Windows\System32\nvidia-smi.exe'
$engine = 'http://localhost:5003/health'

function Log([string]$m) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"
    Add-Content -Path $log -Value $line -Encoding ASCII
    try {
        if ((Get-Item $log).Length -gt 500KB) {
            Get-Content $log -Tail 2000 | Set-Content -Path "$log.tmp" -Encoding ASCII
            Move-Item "$log.tmp" $log -Force
        }
    } catch {}
}

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

# --- état (heartbeat) ---
$hour = (Get-Date).ToString('yyyyMMddHH')
$st = [pscustomobject]@{ hb = ''; maxTemp24h = 0; engineBoots = 0 }
if (Test-Path $stateF) {
    try { $prev = Get-Content $stateF -Raw | ConvertFrom-Json; if ($prev.hb) { $st = $prev } } catch {}
}

# --- mesures GPU + RAM (aucune action, lecture seule) ---
$temp = -1; $util = -1; $vramUsed = -1; $vramTotal = -1
try {
    $q = & $nsmi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1
    if ($q -match '^(\d+),\s*(\d+),\s*(\d+),\s*(\d+)') {
        $temp = [int]$Matches[1]; $util = [int]$Matches[2]; $vramUsed = [int]$Matches[3]; $vramTotal = [int]$Matches[4]
    }
} catch {}
$os = Get-CimInstance Win32_OperatingSystem
$freeMB = [math]::Round($os.FreePhysicalMemory / 1KB)

# --- sonde moteur (silence = moteur éteint, normal hors service) ---
$engineState = 'off'
try {
    $r = Invoke-WebRequest -Uri $engine -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    if ($r.StatusCode -eq 200) { $engineState = 'up' }
} catch { if (Test-NetConnection -ComputerName localhost -Port 5003 -InformationLevel Quiet -WarningAction SilentlyContinue) { $engineState = 'unhealthy' } }

# --- heartbeat horaire ---
if ($st.hb -ne $hour) {
    Log "HEARTBEAT temp=${temp}C util=${util}% vram=${vramUsed}/${vramTotal}MiB ram_free=${freeMB}MB engine=${engineState} max24h=$($st.maxTemp24h)C"
    $st.hb = $hour
    $st.maxTemp24h = 0
}

# --- seuils (temp x charge, P0 05/10) ---
if ($temp -gt $st.maxTemp24h) { $st.maxTemp24h = $temp }
if ($temp -ge 85) {
    Log "WARN HOT temp=${temp}C util=${util}% vram=${vramUsed}MiB engine=${engineState} - seuil 85C depasse (throttle GPU = 96C)"
} elseif ($temp -ge 75 -and $util -lt 10) {
    Log "WARN DESKTOP-HEAT temp=${temp}C util=${util}% - chaleur sans charge vLLM (signature apps desktop, incident avril) - engine=${engineState}"
}
if ($freeMB -lt 4000) {
    Log "WARN RAM free=${freeMB}MB temp=${temp}C engine=${engineState} - marge hôte aminee (hub claudish prioritaire)"
}
if ($engineState -eq 'unhealthy') {
    Log "WARN ENGINE port 5003 ouvert mais /health != 200"
}

[System.IO.File]::WriteAllText($stateF, ($st | ConvertTo-Json -Compress), [System.Text.UTF8Encoding]::new($false))
