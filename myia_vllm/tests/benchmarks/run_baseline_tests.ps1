# Tests de benchmark baseline manuels
$ErrorActionPreference = "Stop"

Write-Host "=== Tests Benchmark Baseline (MANUEL) ==="

$MODEL_NAME = "cpatonn/Qwen3-VL-32B-Thinking-AWQ-4bit"
$RESULTS_FILE = "myia_vllm/reports/benchmark_fp8_baseline_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"

Write-Host "Modèle: $MODEL_NAME"
Write-Host "Résultats: $RESULTS_FILE"

# Attendre que le service soit prêt
Write-Host "Attente service vLLM prêt..."
Start-Sleep -Seconds 30

# Test TTFT (Time To First Token)
Write-Host "Test TTFT (Time To First Token)..."
$TTFT_START = (Get-Date).Millisecond

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
try {
    $RESPONSE_JSON = $TTFT_RESPONSE | ConvertFrom-Json
    $TTFT_TOKENS = $RESPONSE_JSON.usage.prompt_tokens
    if (-not $TTFT_TOKENS) { $TTFT_TOKENS = 0 }
    $TTFT_FINISH_REASON = $RESPONSE_JSON.choices[0].finish_reason
    if (-not $TTFT_FINISH_REASON) { $TTFT_FINISH_REASON = "unknown" }
    
    Write-Host "TTFT: ${TTFT_DURATION}ms, Tokens: $TTFT_TOKENS, Finish: $TTFT_FINISH_REASON"
} catch {
    Write-Host "Erreur TTFT: $($_.Exception.Message)"
}

# Test Throughput (10 requêtes séquentielles)
Write-Host "Test Throughput (10 requêtes séquentielles)..."
$THROUGHPUT_START = (Get-Date).Millisecond

for ($i = 1; $i -le 10; $i++) {
    Write-Host "Requête $i/10..."
    try {
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
    } catch {
        Write-Host "Erreur requête $i`: $($_.Exception.Message)"
    }
}

$THROUGHPUT_END = (Get-Date).Millisecond
$THROUGHPUT_DURATION = $THROUGHPUT_END - $THROUGHPUT_START

# Calculer throughput approximatif (tokens/seconde)
$THROUGHPUT_TPS = [math]::Round(500 / $THROUGHPUT_DURATION)  # 500 tokens générés sur 10 requêtes

Write-Host "Throughput: ${THROUGHPUT_DURATION}s, ~${THROUGHPUT_TPS} tok/s"

# Test Qualité (3 prompts standardisés)
Write-Host "Test Qualité (3 prompts standardisés)..."
$QUALITY_PROMPTS = @(
    "Describe this image: [URL_IMAGE_TEST]",
    "What objects do you see in this picture?",
    "Explain main action happening in this scene."
)

foreach ($prompt in $QUALITY_PROMPTS) {
    Write-Host "Prompt: $prompt"
    try {
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
    } catch {
        Write-Host "Erreur prompt '$prompt': $($_.Exception.Message)"
    }
}

# Générer rapport
$REPORT_JSON = @"
{
  "benchmark_type": "fp8_baseline",
  "timestamp": "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')",
  "model": "$MODEL_NAME",
  "config_file": "myia_vllm/configs/docker/profiles/medium-vl.yml",
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