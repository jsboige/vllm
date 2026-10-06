# gpu-thermal-governor.ps1 - garde-fou automatique host po-2026 (mandat user 2026-09-06)
# 1) Thermique GPU : temp >= 88C sur 2 runs consecutifs -> cap horloges 210,1600 (protect)
#    temp <= 78C sur 3 runs consecutifs           -> restaure 210,1800 (normal)
# 2) Watchdog RAM : free < 2500MB -> WARN log ; free < 1500MB ET pire instance
#    roo-state-manager > 4GB -> kill de cette instance (urgence anti-freeze, cause
#    racine 09-06 : N instances RSM x 1.5GB+ = 25GB+, pagefile thrash = host gele)
# Tache : GPU-Thermal-Governor (SYSTEM, toutes les 5 min, creee avec le boot task GPU-Undervolt-Cap)
# Logs   : logs/gpu-governor.log (rotation 200KB) ; etat : logs/gpu-governor-state.json
# Rollback complet : schtasks /Delete /TN GPU-Thermal-Governor /F  (le boot task 1800 reste seul)

$ErrorActionPreference = 'Continue'
$base   = 'C:\Production\Embeddings'
$logDir = Join-Path $base 'logs'
$log    = Join-Path $logDir 'gpu-governor.log'
$stateF = Join-Path $logDir 'gpu-governor-state.json'
$nsmi   = 'C:\Windows\System32\nvidia-smi.exe'
$capNormal  = '210,1800'
$capProtect = '210,1600'

function Log([string]$m) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"
    Add-Content -Path $log -Value $line -Encoding ASCII
    try {
        if ((Get-Item $log).Length -gt 200KB) {
            Get-Content $log -Tail 2000 | Set-Content -Path "$log.tmp" -Encoding ASCII
            Move-Item "$log.tmp" $log -Force
        }
    } catch {}
}

# --- etat (reset au changement de boot : le boot task GPU-Undervolt-Cap remet 1800) ---
$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('s')
$st = [pscustomobject]@{ boot = $boot; mode = 'normal'; hot = 0; cool = 0; hb = '' }
if (Test-Path $stateF) {
    try {
        $prev = Get-Content $stateF -Raw | ConvertFrom-Json
        if ($prev.boot -eq $boot -and $prev.mode) { $st = $prev }
        else { Log "INFO boot change -> state reset (mode=normal, boot task applique $capNormal)" }
    } catch { Log "WARN state file illisible -> reset" }
}

# --- mesure GPU + RAM ---
$temp = -1
try { $temp = [int](& $nsmi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>$null | Where-Object { $_ -match '\d' } | Select-Object -First 1) } catch {}
$os = Get-CimInstance Win32_OperatingSystem
$freeMB = [math]::Round($os.FreePhysicalMemory / 1KB)

# --- heartbeat horaire (preuve de vie : silence 1h+ = tache morte) ---
$hour = (Get-Date).ToString('yyyyMMddHH')
if ($st.hb -ne $hour) {
    Log "HEARTBEAT temp=${temp}C free=${freeMB}MB mode=$($st.mode)"
    $st.hb = $hour
}

# --- gouverneur thermique (hysteresis) ---
if ($temp -ge 88) {
    $st.hot++; $st.cool = 0
    if ($st.mode -eq 'normal' -and $st.hot -ge 2) {
        & $nsmi -lgc $capProtect | Out-Null
        $st.mode = 'protect'
        Log "ACTION thermal PROTECT: temp=${temp}C (2x >=88) -> cap horloges $capProtect"
    }
}
elseif ($temp -gt 0 -and $temp -le 78) {
    $st.cool++; $st.hot = 0
    if ($st.mode -eq 'protect' -and $st.cool -ge 3) {
        & $nsmi -lgc $capNormal | Out-Null
        $st.mode = 'normal'
        Log "ACTION thermal RESTORE: temp=${temp}C (3x <=78) -> cap horloges $capNormal"
    }
}
else { $st.hot = 0; $st.cool = 0 }

# --- watchdog RAM (cause racine freeze 09-06 : multiplicateur instances RSM) ---
if ($freeMB -lt 1500) {
    $worst = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
        Where-Object { $_.CommandLine -match 'roo-state-manager\\build' } |
        Sort-Object WorkingSetSize -Descending | Select-Object -First 1
    if ($worst -and $worst.WorkingSetSize -gt 4GB) {
        Log "ACTION RAM CRITIQUE: free=${freeMB}MB -> kill RSM PID $($worst.ProcessId) ($([math]::Round($worst.WorkingSetSize/1GB,1))GB, fuite >4GB)"
        try { Stop-Process -Id $worst.ProcessId -Force -ErrorAction Stop; Log "ACTION kill OK PID $($worst.ProcessId)" }
        catch { Log "ERROR kill echoue PID $($worst.ProcessId): $($_.Exception.Message)" }
    }
    else {
        $wgb = 0; if ($worst) { $wgb = [math]::Round($worst.WorkingSetSize / 1GB, 1) }
        Log "WARN RAM CRITIQUE free=${freeMB}MB mais pire RSM=${wgb}GB (< barre 4GB, pas de kill) - escalader au dashboard Maintenance (doctrine 09-07 : ne pas fermer de fenetres)"
    }
}
elseif ($freeMB -lt 2500) {
    Log "WARN RAM basse free=${freeMB}MB temp=${temp}C mode=$($st.mode)"
}

[System.IO.File]::WriteAllText($stateF, ($st | ConvertTo-Json -Compress), [System.Text.UTF8Encoding]::new($false))
