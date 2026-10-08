# install-governor-po2025.ps1 — pose du combo thermique twin po-2025 (siège po-2025:vllm)
# FENÊTRE UAC UNIQUE (batch, règle flotte) — mandat user GO 06/10 17:14 (registre Q2).
# Pose : GPU-Thermal-Governor-po2025 (SYSTEM /5 min) + GPU-Undervolt-Cap-po2025
# (boot task nvidia-smi -lgc 210,1800, combo éprouvé twin po-2026). Exécute ensuite
# chacun une fois (preuve heartbeat/cap), écrit le résultat dans _logs/governor-install-result.txt
# que la session non-élevée relit (la fenêtre élevée se ferme d'elle-même).
# Rollback : schtasks /Delete /TN GPU-Thermal-Governor-po2025 /F ; /TN GPU-Undervolt-Cap-po2025 /F
$ErrorActionPreference = 'Continue'
$logs = 'D:\dev\vllm\myia_vllm\_logs'
$result = Join-Path $logs 'governor-install-result.txt'
$gov = 'D:\dev\vllm\myia_vllm\scripts\gpu-thermal-governor-po2025.ps1'
$out = @()

# --- auto-élévation : UNE seule fenêtre UAC ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -WindowStyle Hidden
    return
}

try {
    # 1) Gouverneur /5 min SYSTEM
    schtasks /Create /TN GPU-Thermal-Governor-po2025 /TR "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$gov`"" /SC MINUTE /MO 5 /RU SYSTEM /RL HIGHEST /F | Out-Null
    $out += "governor_task=" + $(if ($LASTEXITCODE -eq 0) { 'OK' } else { "FAIL($LASTEXITCODE)" })

    # 2) Boot task undervolt (combo twin) + application immédiate
    schtasks /Create /TN GPU-Undervolt-Cap-po2025 /TR "nvidia-smi -lgc 210,1800" /SC ONSTART /RU SYSTEM /RL HIGHEST /F | Out-Null
    $out += "boottask_task=" + $(if ($LASTEXITCODE -eq 0) { 'OK' } else { "FAIL($LASTEXITCODE)" })
    $cap = & nvidia-smi -lgc 210,1800 2>&1 | Out-String
    $out += "cap_applied=" + $(if ($LASTEXITCODE -eq 0) { 'OK (210,1800)' } else { "FAIL: $($cap.Trim())" })

    # 3) Preuves : exécution immédiate du gouverneur + lancement de la task
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $gov
    Start-ScheduledTask -TaskName GPU-Thermal-Governor-po2025
    $out += "governor_first_run=OK"
    $t = Get-ScheduledTask -TaskName GPU-Thermal-Governor-po2025
    $out += "governor_state=$($t.State)"
    $b = Get-ScheduledTask -TaskName GPU-Undervolt-Cap-po2025
    $out += "boottask_state=$($b.State)"
} catch {
    $out += "ERROR: $($_.Exception.Message)"
}
[System.IO.File]::WriteAllText($result, ($out -join "`n"), [System.Text.UTF8Encoding]::new($false))
