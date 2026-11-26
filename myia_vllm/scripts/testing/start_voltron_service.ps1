# Service harnais voltron — moteur persistant + serveur HTTP (po-2028, mandat adoption 18/11).
# Usage : pwsh -File start_voltron_service.ps1 [-NoEngine] [-Python <interpréteur>]
#   -NoEngine : serveur seul ; -Python : interpréteur explicite (défaut : `python` du PATH —
#   le serveur n'a besoin que de la bibliothèque standard).
# Rollback complet : arrêter D'ABORD le serveur (process python :5029), puis
#   docker stop voltron-harness — dans cet ordre : tant que le serveur vit, il
#   relance un moteur muet (docker start).
#
# Le moteur est le CONTENEUR d'éval validé (fp8 KV, SANS tier RAM depuis le 24/11 :
# mesuré inerte — 0 octet relu sur ~24 h, 4 Gio de shm inutiles dans la VM WSL 24 Gio)
# passé en régime permanent : --restart unless-stopped. Le serveur bind 127.0.0.1:5029.
# La clé hub (ZAI_API_KEY) est résolue en MÉMOIRE depuis ~/.claude.json — jamais écrite.

param([switch]$NoEngine, [string]$Python = 'python')

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
            --max-num-seqs 64
            # Tier RAM retiré 24/11 : --kv-offloading-size 4 --kv-offloading-backend native
            # = 4 Gio de shm pour 0 octet relu sur ~24 h (métriques kv_offload_*). Rollback :
            # rajouter les deux drapeaux à la ligne ci-dessus et recréer le conteneur.
        if ($LASTEXITCODE -ne 0) { throw "docker run a échoué" }
    }
    Write-Host "[engine] boot en cours (115-150 s mesuré) — le serveur l'attend de lui-même"
}

# ---- 2. clé hub : mémoire uniquement ---------------------------------------
$claudeCfg = Get-Content "$env:USERPROFILE\.claude.json" -Raw | ConvertFrom-Json
$key = $claudeCfg.mcpServers.'sk-agent'.env.ZAI_API_KEY
if (-not $key) { Write-Warning "ZAI_API_KEY introuvable — phase C (coordinateur) désactivée" }

# ---- 2b. config locale (hors dépôt) : hub URL + chemins de données ----------
# CHANGES_REQUESTED §7-8 : plus aucune adresse LAN ni chemin machine versionné
# dans le code — le serveur lit VOLTRON_HUB_URL / VOLTRON_JOBS_DIR /
# VOLTRON_USAGE_PATH, ce fichier les fournit (KEY=VALUE, une par ligne).
$envFile = 'D:\vllm-data\bench\v2_service.env'
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_]+)\s*=\s*(.+?)\s*$') { Set-Item "env:$($Matches[1])" $Matches[2] }
    }
    Write-Host "[config] $envFile chargé (VOLTRON_HUB_URL=$env:VOLTRON_HUB_URL)"
} else {
    Write-Warning "$envFile absent — hub/chemins par défaut du serveur (~/.voltron_harness, phase C désactivée sans VOLTRON_HUB_URL)"
}

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
    $p = Start-Process $Python -ArgumentList "`"$root\voltron_harness_server.py`"" `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $log -RedirectStandardError $err
    Write-Host "[serveur] PID $($p.Id) -> 127.0.0.1:5029 (log $log)"
}
