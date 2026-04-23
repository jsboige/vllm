#!/usr/bin/env bash
# Benchmark Baseline Actuelle (SANS --calculate-kv-scales)
# Objectif: Établir référence performance/accuracy pour comparaison

set -e

echo "=== Benchmark FP8 Baseline (AVANT calibration) ==="

# Configuration de référence
CONFIG_FILE="myia_vllm/configs/docker/profiles/medium-vl.yml"
MODEL_NAME="cpatonn/Qwen3-VL-32B-Thinking-AWQ-4bit"
RESULTS_FILE="myia_vllm/reports/benchmark_fp8_baseline_$(date +%Y%m%d_%H%M%S).json"

echo "Modèle: $MODEL_NAME"
echo "Configuration: $CONFIG_FILE"
echo "Résultats: $RESULTS_FILE"

# 1. Lancer conteneur medium-vl (config actuelle)
echo "Démarrage conteneur avec configuration actuelle..."
docker compose -f myia_vllm/docker-compose-qwen3-medium.yml up -d

# 2. Attendre démarrage vLLM
echo "Attente démarrage vLLM (30s)..."
sleep 30

# 3. Test TTFT (Time To First Token)
echo "Test TTFT (Time To First Token)..."
TTFT_START=$(date +%s%N)

# Requête de test vision
TTFT_RESPONSE=$(curl -s -X POST http://localhost:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'$MODEL_NAME'",
    "prompt": "Describe this image in detail.",
    "max_tokens": 100,
    "temperature": 0.7,
    "stream": false
  }' \
  2>/dev/null)

TTFT_END=$(date +%s%N)
TTFT_DURATION=$((TTFT_END - TTFT_START))

# Extraire métriques
TTFT_TOKENS=$(echo "$TTFT_RESPONSE" | jq -r '.usage.prompt_tokens // 0')
TTFT_FINISH_REASON=$(echo "$TTFT_RESPONSE" | jq -r '.choices[0].finish_reason // "unknown"')

echo "TTFT: ${TTFT_DURATION}ms, Tokens: $TTFT_TOKENS, Finish: $TTFT_FINISH_REASON"

# 4. Test Throughput (10 requêtes séquentielles)
echo "Test Throughput (10 requêtes séquentielles)..."
THROUGHPUT_START=$(date +%s%N)

for i in {1..10}; do
    echo "Requête $i/10..."
    curl -s -X POST http://localhost:8000/v1/completions \
      -H "Content-Type: application/json" \
      -d '{
        "model": "'$MODEL_NAME'",
        "prompt": "What do you see in this image?",
        "max_tokens": 50,
        "temperature": 0.7,
        "stream": false
      }' \
      2>/dev/null
done

THROUGHPUT_END=$(date +%s%N)
THROUGHPUT_DURATION=$((THROUGHPUT_END - THROUGHPUT_START))

# Calculer throughput approximatif (tokens/seconde)
THROUGHPUT_TPS=$((500 / THROUGHPUT_DURATION))  # 500 tokens générés sur 10 requêtes

echo "Throughput: ${THROUGHPUT_DURATION}s, ~${THROUGHPUT_TPS} tok/s"

# 5. Test Qualité (réponses qualitatives)
echo "Test Qualité (3 prompts standardisés)..."
QUALITY_PROMPTS=(
    "Describe this image: [URL_IMAGE_TEST]"
    "What objects do you see in this picture?"
    "Explain the main action happening in this scene."
)

for prompt in "${QUALITY_PROMPTS[@]}"; do
    echo "Prompt: $prompt"
    curl -s -X POST http://localhost:8000/v1/completions \
      -H "Content-Type: application/json" \
      -d '{
        "model": "'$MODEL_NAME'",
        "prompt": "'$prompt'",
        "max_tokens": 100,
        "temperature": 0.7,
        "stream": false
      }' \
      2>/dev/null
    echo "---"
done

# 6. Arrêter conteneur
echo "Arrêt conteneur..."
docker compose -f myia_vllm/docker-compose-qwen3-medium.yml down

# 7. Générer rapport
cat > "$RESULTS_FILE" << EOF
{
  "benchmark_type": "fp8_baseline",
  "timestamp": "$(date -Iseconds)",
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
EOF

echo "=== Benchmark terminé ==="
echo "Résultats sauvegardés dans: $RESULTS_FILE"
echo "Pour comparer avec la version calibrée, exécuter: benchmark_fp8_calibrated.sh"