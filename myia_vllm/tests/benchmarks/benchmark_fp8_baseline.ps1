# Benchmark Baseline Actuelle (SANS --calculate-kv-scales)
# Objectif: Établir référence performance/accuracy pour comparaison

$ErrorActionPreference = "Stop"

Write-Host "=== Benchmark FP8 Baseline (AVANT calibration) ==="

# Configuration de référence
$CONFIG_FILE = "myia_vllm/configs/docker/profiles/medium-vl.yml"
$MODEL_NAME = "cpatonn/Qwen3-VL-32B-Thinking-AWQ-4bit"
$RESULTS_FILE = "myia_vllm/reports/benchmark_fp8_baseline_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"

Write-Host "Modèle: $MODEL_NAME"
Write-Host "Configuration: $CONFIG_FILE"
Write-Host "Résultats: $RESULTS_FILE"

# 1. Lancer conteneur medium-vl (config actuelle)
Write-Host "Démarrage conteneur avec configuration actuelle..."
docker compose -f myia_vllm/docker-compose-qwen3-medium.yml up -d

# 2. Attendre démarrage vLLM
Write-Host "Attente démarrage vLLM (30s)..."
Start-Sleep -Seconds 30

# 3. Test TTFT (Time To First Token)
Write-Host "Test TTFT (Time To First Token)..."
$TTFT_START = (Get-Date).Millisecond

# Requête de test vision
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

$TTFT_END = (Get-Date).Millisecond
$TTFT_DURATION = $TTFT_END - $TTFT_START

# Extraire métriques
$TTFT_TOKENS = ($TTFT_RESPONSE | ConvertFrom-Json).usage.prompt_tokens
if (-not $TTFT_TOKENS) { $TTFT_TOKENS = 0 }
$TTFT_FINISH_REASON = ($TTFT_RESPONSE | ConvertFrom-Json).choices[0].finish_reason
if (-not $TTFT_FINISH_REASON) { $TTFT_FINISH_REASON = "unknown" }

Write-Host "TTFT: ${TTFT_DURATION}ms, Tokens: $TTFT_TOKENS, Finish: $TTFT_FINISH_REASON"

# 4. Test Throughput (10 requêtes séquentielles)
Write-Host "Test Throughput (10 requêtes séquentielles)..."
$THROUGHPUT_START = (Get-Date).Millisecond

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

$THROUGHPUT_END = (Get-Date).Millisecond
$THROUGHPUT_DURATION = $THROUGHPUT_END - $THROUGHPUT_START

# Calculer throughput approximatif (tokens/seconde)
$THROUGHPUT_TPS = [math]::Round(500 / $THROUGHPUT_DURATION)  # 500 tokens générés sur 10 requêtes

Write-Host "Throughput: ${THROUGHPUT_DURATION}s, ~${THROUGHPUT_TPS} tok/s"

# 5. Test Qualité (réponses qualitatives)
Write-Host "Test Qualité (3 prompts standardisés)..."
$QUALITY_PROMPTS = @(
    "Describe this image: [URL_IMAGE_TEST]",
    "What objects do you see in this picture?",
    "Explain main action happening in this scene."
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

# 6. Arrêter conteneur
Write-Host "Arrêt conteneur..."
docker compose -f myia_vllm/docker-compose-qwen3-medium.yml down

# 7. Générer rapport
$REPORT_JSON = @"
{
  "benchmark_type": "fp8_baseline",
  "timestamp": "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')",
  "model": "$MODEL_NAME",
  "config_file": "$CONFIG_FILE",
  "results": {
    "ttft": {
      "duration_ms": $TTFT_DURATION,
      "tokens": $TTFT_TOKENS,
      "finish_reason": "$TTFT_FINISH_REASON"
    },
    "throughput": {
      "duration_s": $THROUGHPUT_DURATION,
      "tokens_per_second": $THROUGHPUT_TPS
    },
    "warnings_observed": [
      "Using KV cache scaling factor 1.0 for fp8_e4m3",
      "Using uncalibrated q_scale 1.0 and/or prob_scale 1.0 with fp8 attention",
      "Checkpoint does not provide a q scaling factor",
      "Using 'pin_memory=False' as WSL is detected",
      "Custom allreduce is disabled because your platform lacks GPU P2P capability"
    ]
  },
  "environment": {
    "os": "WSL2",
    "gpus": "2x RTX 4090 24GB",
    "vllm_version": "0.11.0"
  }
}
"@

Set-Content -Path $RESULTS_FILE -Value $REPORT_JSON -Encoding UTF8

Write-Host "=== Benchmark terminé ==="
Write-Host "Résultats sauvegardés dans: $RESULTS_FILE"
Write-Host "Pour comparer avec la version calibrée, exécuter: benchmark_fp8_calibrated.ps1"