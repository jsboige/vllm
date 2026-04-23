# Benchmark avec Calibration FP8 (--calculate-kv-scales)
# Objectif: Mesurer impact de la calibration sur performance/accuracy

Write-Host "=== Benchmark FP8 Calibré (AVEC --calculate-kv-scales) ==="

# Configuration
$CONFIG_FILE = "myia_vllm/configs/docker/profiles/medium-vl.yml"
$MODEL_NAME = "cpatonn/Qwen3-VL-32B-Thinking-AWQ-4bit"
$RESULTS_FILE = "myia_vllm/reports/benchmark_fp8_calibrated_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"

Write-Host "Modèle: $MODEL_NAME"
Write-Host "Configuration: $CONFIG_FILE (modifiée avec --calculate-kv-scales)"
Write-Host "Résultats: $RESULTS_FILE"

# 1. Créer configuration temporaire avec calibration
$TEMP_CONFIG = "myia_vllm/configs/docker/profiles/medium-vl-calibrated.yml"
Copy-Item "$CONFIG_FILE" "$TEMP_CONFIG" -Force

# Ajouter --calculate-kv-scales à la commande vLLM
(Get-Content "$TEMP_CONFIG") -replace 'command: python -m vllm.entrypoints.openai.api_server', 'command: python -m vllm.entrypoints.openai.api_server --calculate-kv-scales' | Set-Content "$TEMP_CONFIG"

Write-Host "Configuration temporaire créée: $TEMP_CONFIG"

# 2. Modifier docker-compose pour utiliser la config calibrée
$COMPOSE_FILE = "myia_vllm/docker-compose.yml"
(Get-Content "$COMPOSE_FILE") -replace 'medium-vl\.yml', 'medium-vl-calibrated.yml' | Set-Content "$COMPOSE_FILE"

Write-Host "Docker-compose modifié pour utiliser configuration calibrée"

# 3. Lancer conteneur avec configuration calibrée
Write-Host "Démarrage conteneur avec configuration calibrée..."
docker compose --profile medium-vl up -d

# 4. Attendre démarrage et calibration (plus long à cause du calcul)
Write-Host "Attente démarrage et calibration KV scales (90s)..."
Start-Sleep -Seconds 90

# 5. Vérifier que les warnings FP8 ont disparu
Write-Host "Vérification des logs pour les warnings FP8..."
$logs = docker logs medium-vl 2>&1
if ($logs -match "kv_cache|scaling factor|q_scale|prob_scale") {
    Write-Host "⚠️ Warnings FP8 encore présents"
} else {
    Write-Host "✅ Aucun warning FP8 détecté"
}

# 6. Test TTFT (Time To First Token)
Write-Host "Test TTFT (Time To First Token) - version calibrée..."
$TTFT_START = Get-Date

# Requête de test vision identique à baseline
$TTFT_RESPONSE = curl -s -X POST http://localhost:8000/v1/completions `
  -H "Content-Type: application/json" `
  -d "{
    `"model`": `"$MODEL_NAME`",
    `"prompt`": `"Describe this image in detail.`",
    `"max_tokens`": 100,
    `"temperature`": 0.7,
    `"stream`": false
  }" `
  2>$null

$TTFT_END = Get-Date
$TTFT_DURATION = [math]::Round((($TTFT_END - $TTFT_START).TotalMilliseconds))

# Extraire métriques
$TTFT_TOKENS = ($TTFT_RESPONSE | ConvertFrom-Json).usage.prompt_tokens
if (-not $TTFT_TOKENS) { $TTFT_TOKENS = 0 }
$TTFT_FINISH_REASON = ($TTFT_RESPONSE | ConvertFrom-Json).choices[0].finish_reason
if (-not $TTFT_FINISH_REASON) { $TTFT_FINISH_REASON = "unknown" }

Write-Host "TTFT Calibré: ${TTFT_DURATION}ms, Tokens: $TTFT_TOKENS, Finish: $TTFT_FINISH_REASON"

# 7. Test Throughput (10 requêtes séquentielles)
Write-Host "Test Throughput (10 requêtes séquentielles) - version calibrée..."
$THROUGHPUT_START = Get-Date

for ($i = 1; $i -le 10; $i++) {
    Write-Host "Requête $i/10..."
    curl -s -X POST http://localhost:8000/v1/completions `
      -H "Content-Type: application/json" `
      -d "{
        `"model`": `"$MODEL_NAME`",
        `"prompt`": `"What do you see in this image?`",
        `"max_tokens`": 50,
        `"temperature`": 0.7,
        `"stream`": false
      }" `
      2>$null
}

$THROUGHPUT_END = Get-Date
$THROUGHPUT_DURATION = [math]::Round(($THROUGHPUT_END - $THROUGHPUT_START).TotalSeconds)

# Calculer throughput approximatif
$THROUGHPUT_TPS = [math]::Round(500 / $THROUGHPUT_DURATION)

Write-Host "Throughput Calibré: ${THROUGHPUT_DURATION}s, ~${THROUGHPUT_TPS} tok/s"

# 8. Test Qualité (même prompts que baseline pour comparaison)
Write-Host "Test Qualité (3 prompts standardisés) - version calibrée..."
$QUALITY_PROMPTS = @(
    "Describe this image: [URL_IMAGE_TEST]",
    "What objects do you see in this picture?",
    "Explain the main action happening in this scene."
)

foreach ($prompt in $QUALITY_PROMPTS) {
    Write-Host "Prompt: $prompt"
    curl -s -X POST http://localhost:8000/v1/completions `
      -H "Content-Type: application/json" `
      -d "{
        `"model`": `"$MODEL_NAME`",
        `"prompt`": `"$prompt`",
        `"max_tokens`": 100,
        `"temperature`": 0.7,
        `"stream`": false
      }" `
      2>$null
    Write-Host "---"
}

# 9. Arrêter conteneur
Write-Host "Arrêt conteneur..."
docker compose --profile medium-vl down

# 10. Restaurer configuration originale
(Get-Content "$COMPOSE_FILE") -replace 'medium-vl-calibrated\.yml', 'medium-vl.yml' | Set-Content "$COMPOSE_FILE"
Remove-Item "$TEMP_CONFIG" -Force

Write-Host "Configuration originale restaurée"

# 11. Générer rapport de comparaison
$report = @{
    benchmark_type = "fp8_calibrated"
    timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    model = $MODEL_NAME
    config_file = "$CONFIG_FILE (modifiée avec --calculate-kv-scales)"
    results = @{
        ttft = @{
            duration_ms = $TTFT_DURATION
            tokens = $TTFT_TOKENS
            finish_reason = $TTFT_FINISH_REASON
        }
        throughput = @{
            duration_s = $THROUGHPUT_DURATION
            tokens_per_second = $THROUGHPUT_TPS
        }
        warnings_observed = @()
        calibration_applied = "--calculate-kv-scales"
    }
    environment = @{
        os = "WSL2"
        gpus = "2x RTX 4090 24GB"
        vllm_version = "0.11.0"
    }
    comparison_baseline = @{
        note = "À comparer avec benchmark_fp8_baseline_*.json"
        metrics_to_compare = @("ttft.duration_ms", "throughput.tokens_per_second")
    }
}

$report | ConvertTo-Json -Depth 4 | Set-Content "$RESULTS_FILE"

Write-Host "=== Benchmark calibré terminé ==="
Write-Host "Résultats sauvegardés dans: $RESULTS_FILE"
Write-Host "Pour comparer avec baseline: Compare les fichiers JSON manuellement"