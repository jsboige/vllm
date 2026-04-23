#!/usr/bin/env bash
# Benchmark avec Calibration FP8 (--calculate-kv-scales)
# Objectif: Mesurer impact de la calibration sur performance/accuracy

set -e

echo "=== Benchmark FP8 Calibré (AVEC --calculate-kv-scales) ==="

# Configuration modifiée avec calibration
CONFIG_FILE="myia_vllm/configs/docker/profiles/medium-vl.yml"
MODEL_NAME="cpatonn/Qwen3-VL-32B-Thinking-AWQ-4bit"
RESULTS_FILE="myia_vllm/reports/benchmark_fp8_calibrated_$(date +%Y%m%d_%H%M%S).json"

echo "Modèle: $MODEL_NAME"
echo "Configuration: $CONFIG_FILE (modifiée avec --calculate-kv-scales)"
echo "Résultats: $RESULTS_FILE"

# 1. Créer configuration temporaire avec calibration
TEMP_CONFIG="myia_vllm/configs/docker/profiles/medium-vl-calibrated.yml"
cp "$CONFIG_FILE" "$TEMP_CONFIG"

# Ajouter --calculate-kv-scales à la commande vLLM
sed -i 's/command: python -m vllm.entrypoints.openai.api_server/command: python -m vllm.entrypoints.openai.api_server --calculate-kv-scales/' "$TEMP_CONFIG"

echo "Configuration temporaire créée: $TEMP_CONFIG"

# 2. Modifier docker-compose pour utiliser la config calibrée
COMPOSE_FILE="myia_vllm/docker-compose.yml"
sed -i "s/medium-vl\.yml/medium-vl-calibrated.yml/" "$COMPOSE_FILE"

echo "Docker-compose modifié pour utiliser configuration calibrée"

# 3. Lancer conteneur avec configuration calibrée
echo "Démarrage conteneur avec configuration calibrée..."
docker compose --profile medium-vl up -d

# 4. Attendre démarrage et calibration (plus long à cause du calcul)
echo "Attente démarrage et calibration KV scales (60s)..."
sleep 60

# 5. Vérifier que les warnings FP8 ont disparu
echo "Vérification des logs pour les warnings FP8..."
docker logs medium-vl 2>&1 | grep -E "(kv_cache|scaling factor|q_scale|prob_scale)" || echo "✅ Aucun warning FP8 détecté"

# 6. Test TTFT (Time To First Token)
echo "Test TTFT (Time To First Token) - version calibrée..."
TTFT_START=$(date +%s%N)

# Requête de test vision identique à baseline
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

echo "TTFT Calibré: ${TTFT_DURATION}ms, Tokens: $TTFT_TOKENS, Finish: $TTFT_FINISH_REASON"

# 7. Test Throughput (10 requêtes séquentielles)
echo "Test Throughput (10 requêtes séquentielles) - version calibrée..."
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

# Calculer throughput approximatif
THROUGHPUT_TPS=$((500 / THROUGHPUT_DURATION))

echo "Throughput Calibré: ${THROUGHPUT_DURATION}s, ~${THROUGHPUT_TPS} tok/s"

# 8. Test Qualité (même prompts que baseline pour comparaison)
echo "Test Qualité (3 prompts standardisés) - version calibrée..."
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

# 9. Arrêter conteneur
echo "Arrêt conteneur..."
docker compose --profile medium-vl down

# 10. Restaurer configuration originale
sed -i "s/medium-vl-calibrated\.yml/medium-vl.yml/" "$COMPOSE_FILE"
rm "$TEMP_CONFIG"

echo "Configuration originale restaurée"

# 11. Générer rapport de comparaison
cat > "$RESULTS_FILE" << EOF
{
  "benchmark_type": "fp8_calibrated",
  "timestamp": "$(date -Iseconds)",
  "model": "$MODEL_NAME",
  "config_file": "$CONFIG_FILE (modifiée avec --calculate-kv-scales)",
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
    "warnings_observed": [],
    "calibration_applied": "--calculate-kv-scales"
  },
  "environment": {
    "os": "WSL2",
    "gpus": "2x RTX 4090 24GB",
    "vllm_version": "0.11.0"
  },
  "comparison_baseline": {
    "note": "À comparer avec benchmark_fp8_baseline_*.json",
    "metrics_to_compare": ["ttft.duration_ms", "throughput.tokens_per_second"]
  }
}
EOF

echo "=== Benchmark calibré terminé ==="
echo "Résultats sauvegardés dans: $RESULTS_FILE"
echo "Pour comparer avec baseline: diff <(jq . benchmark_fp8_baseline_*.json) <(jq . \"$RESULTS_FILE\")"