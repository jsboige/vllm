# Service harnais voltron — moteur persistant + serveur HTTP (po-2028, mandat adoption 18/11).
# Usage : pwsh -File start_voltron_service.ps1 [-NoEngine]   (-NoEngine : serveur seul)
# Rollback complet : docker stop voltron-harness ; puis tuer le process python du serveur.
#
# Le moteur est le CONTENEUR d'éval validé (fp8 KV, tier RAM 4 Gio) passé en régime
# permanent : --restart unless-stopped. Le serveur bind 127.0.0.1:5029.
# La clé hub (ZAI_API_KEY) est résolue en MÉMOIRE depuis ~/.claude.json — jamais écrite.

param([switch]$NoEngine)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# ---- 1. moteur persistant --------------------------------------------------
if (-not $NoEngine) {
    $exists = docker ps -a --filter "name=^voltron-harness$" --format '{{.Names}}'
    if ($exists -eq 'voltron-harness') {
        Write-Host "[engine] conteneur présent -> docker start"
        docker start voltron-harness | Out-Null
    } else {
        Write-Host "[engine] docker run -d --restart unless-stopped (config fp8 validée)"
        docker run -d --name voltron-harness --restart unless-stopped `
            --gpus all --shm-size 6g `
            -p 127.0.0.1:5028:8000 `
            -v D:\vllm-data\models\voltron-1-mini:/model:ro `
            vllm/vllm-openai@sha256:b6d1cfc60cce1f6405d37ea77645a36a46065230fb643abc2eeb93a5dc8fb79b `
            --model /model --served-model-name voltron-1-mini `
            --max-model-len 32768 --gpu-memory-utilization 0.85 --dtype auto `
            --kv-cache-dtype fp8 --kv-cache-memory 1750432666 `
            --max-num-seqs 64 --kv-offloading-size 4 --kv-offloading-backend native
        if ($LASTEXITCODE -ne 0) { throw "docker run a échoué" }
    }
    Write-Host "[engine] boot en cours (115-150 s mesuré) — le serveur l'attend de lui-même"
}

# ---- 2. clé hub : mémoire uniquement ---------------------------------------
$claudeCfg = Get-Content "$env:USERPROFILE\.claude.json" -Raw | ConvertFrom-Json
$key = $claudeCfg.mcpServers.'sk-agent'.env.ZAI_API_KEY
if (-not $key) { Write-Warning "ZAI_API_KEY introuvable — phase C (coordinateur) désactivée" }

# ---- 3. serveur (arrière-plan, log sur disque) ------------------------------
$log = 'D:\vllm-data\bench\v2_server.log'
$err = 'D:\vllm-data\bench\v2_server.err.log'
$env:ZAI_API_KEY = $key   # process env du Start-Process uniquement
$existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*voltron_harness_server.py*' }
if ($existing) {
    Write-Host "[serveur] déjà actif (PID $($existing.ProcessId)) — rien à faire"
} else {
    New-Item -ItemType Directory -Force (Split-Path -Parent $log) | Out-Null
    $p = Start-Process python -ArgumentList "`"$root\voltron_harness_server.py`"" `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $log -RedirectStandardError $err
    Write-Host "[serveur] PID $($p.Id) -> 127.0.0.1:5029 (log $log)"
}
