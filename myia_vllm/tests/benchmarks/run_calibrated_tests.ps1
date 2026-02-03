# Script simplifié pour benchmark calibré FP8
Write-Host "=== Lancement Benchmark Calibré FP8 ==="

# Configuration
$MODEL_NAME = "cpatonn/Qwen3-VL-32B-Thinking-AWQ-4bit"
$RESULTS_FILE = "myia_vllm/reports/benchmark_fp8_calibrated_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"

Write-Host "Modèle: $MODEL_NAME"
Write-Host "Résultats: $RESULTS_FILE"

# 1. Lancer conteneur avec configuration calibrée
Write-Host "Démarrage conteneur avec configuration calibrée..."
docker compose --env-file myia_vllm/.env -f myia_vllm/configs/docker/profiles/medium-vl-calibrated.yml up -d

# 2. Attendre démarrage et calibration (plus long à cause du calcul)
Write-Host "Attente démarrage et calibration KV scales (120s)..."
Start-Sleep -Seconds 120

# 3. Vérifier que le service est prêt
Write-Host "Vérification du service..."
$healthCheck = 0
for ($i = 1; $i -le 10; $i++) {
    try {
        $response = curl -s http://localhost:5003/health 2>$null
        if ($response -and $response.Contains('"status": "healthy"')) {
            Write-Host "✅ Service prêt après $($i * 10) secondes"
            $healthCheck = 1
            break
        }
    } catch {
        Write-Host "Tentative $($i * 10)/100s..."
    }
    Start-Sleep -Seconds 10
}

if ($healthCheck -eq 0) {
    Write-Host "❌ Service non prêt après 100s, poursuite quand même..."
}

# 4. Test TTFT (Time To First Token)
Write-Host "Test TTFT (Time To First Token) - version calibrée..."
$TTFT_START = Get-Date

try {
    $TTFT_RESPONSE = curl -s -X POST http://localhost:5003/v1/completions `
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
    if ($TTFT_RESPONSE) {
        $jsonData = $TTFT_RESPONSE | ConvertFrom-Json
        $TTFT_TOKENS = $jsonData.usage.prompt_tokens
        if (-not $TTFT_TOKENS) { $TTFT_TOKENS = 0 }
        $TTFT_FINISH_REASON = $jsonData.choices[0].finish_reason
        if (-not $TTFT_FINISH_REASON) { $TTFT_FINISH_REASON = "unknown" }
    } else {
        $TTFT_TOKENS = 0
        $TTFT_FINISH_REASON = "no_response"
    }
    
    Write-Host "TTFT Calibré: ${TTFT_DURATION}ms, Tokens: $TTFT_TOKENS, Finish: $TTFT_FINISH_REASON"
} catch {
    Write-Host "❌ Erreur TTFT: $_"
    $TTFT_DURATION = 0
    $TTFT_TOKENS = 0
    $TTFT_FINISH_REASON = "error"
}

# 5. Test Throughput (5 requêtes séquentielles)
Write-Host "Test Throughput (5 requêtes séquentielles) - version calibrée..."
$THROUGHPUT_START = Get-Date
$successCount = 0

for ($i = 1; $i -le 5; $i++) {
    Write-Host "Requête $i/5..."
    try {
        $response = curl -s -X POST http://localhost:5003/v1/completions `
          -H "Content-Type: application/json" `
          -d "{
            `"model`": `"$MODEL_NAME`",
            `"prompt`": `"What do you see in this image?`",
            `"max_tokens`": 50,
            `"temperature`": 0.7,
            `"stream`": false
          }" `
          2>$null
        
        if ($response) {
            $successCount++
        }
    } catch {
        Write-Host "❌ Erreur requête $i : $_"
    }
}

$THROUGHPUT_END = Get-Date
$THROUGHPUT_DURATION = [math]::Round(($THROUGHPUT_END - $THROUGHPUT_START).TotalSeconds)

# Calculer throughput approximatif
$THROUGHPUT_TPS = if ($THROUGHPUT_DURATION -gt 0) { [math]::Round(($successCount * 50) / $THROUGHPUT_DURATION) } else { 0 }

Write-Host "Throughput Calibré: ${THROUGHPUT_DURATION}s, ${THROUGHPUT_TPS} tok/s (${successCount}/5 succès)"

# 6. Test Qualité (3 prompts standardisés)
Write-Host "Test Qualité (3 prompts standardisés) - version calibrée..."
$QUALITY_PROMPTS = @(
    "Describe this image: [URL_IMAGE_TEST]",
    "What objects do you see in this picture?",
    "Explain the main action happening in this scene."
)

$qualityResults = @()
foreach ($prompt in $QUALITY_PROMPTS) {
    Write-Host "Prompt: $prompt"
    try {
        $response = curl -s -X POST http://localhost:5003/v1/completions `
          -H "Content-Type: application/json" `
          -d "{
            `"model`": `"$MODEL_NAME`",
            `"prompt`": `"$prompt`",
            `"max_tokens`": 100,
            `"temperature`": 0.7,
            `"stream`": false
          }" `
          2>$null
        
        if ($response) {
            $qualityResults += @{
                prompt = $prompt
                success = $true
                response_length = if ($response) { ($response | ConvertFrom-Json).choices[0].text.Length } else { 0 }
            }
        } else {
            $qualityResults += @{
                prompt = $prompt
                success = $false
                response_length = 0
            }
        }
    } catch {
        Write-Host "❌ Erreur prompt: $_"
        $qualityResults += @{
            prompt = $prompt
            success = $false
            response_length = 0
        }
    }
    Write-Host "---"
}

# 7. Arrêter conteneur
Write-Host "Arrêt conteneur..."
docker compose --env-file myia_vllm/.env -f myia_vllm/configs/docker/profiles/medium-vl-calibrated.yml down

# 8. Générer rapport
$report = @{
    benchmark_type = "fp8_calibrated"
    timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    model = $MODEL_NAME
    config_file = "myia_vllm/configs/docker/profiles/medium-vl-calibrated.yml (avec --calculate-kv-scales)"
    results = @{
        ttft = @{
            duration_ms = $TTFT_DURATION
            tokens = $TTFT_TOKENS
            finish_reason = $TTFT_FINISH_REASON
        }
        throughput = @{
            duration_s = $THROUGHPUT_DURATION
            tokens_per_second = $THROUGHPUT_TPS
            success_rate = "$successCount/5"
        }
        quality = @{
            total_prompts = $qualityResults.Count
            successful_prompts = ($qualityResults | Where-Object { $_.success }).Count
            avg_response_length = if ($qualityResults.Count -gt 0) { [math]::Round(($qualityResults | Measure-Object -Property response_length -Average).response_length) } else { 0 }
        }
        warnings_observed = @()
        calibration_applied = "--calculate-kv-scales"
    }
    environment = @{
        os = "WSL2"
        gpus = "2x RTX 4090 24GB"
        vllm_version = "0.11.0"
    }
}

try {
    $report | ConvertTo-Json -Depth 4 | Set-Content "$RESULTS_FILE"
    Write-Host "=== Benchmark calibré terminé ==="
    Write-Host "Résultats sauvegardés dans: $RESULTS_FILE"
} catch {
    Write-Host "❌ Erreur sauvegarde résultats: $_"
}