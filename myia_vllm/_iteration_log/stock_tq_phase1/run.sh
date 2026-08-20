#!/usr/bin/env bash
# Phase 1 : vLLM upstream STOCK (sans Genesis) + TurboQuant k8v4, GPU 2 uniquement.
#
#   ./run.sh fp8              # controle : doit passer
#   ./run.sh turboquant_k8v4  # le test
#
# N'utilise QUE la GPU 2. La prod (GPUs 0,1, port 5002) n'est jamais touchee.
# Cache HF dedie sur D: -> le bind WSL de la prod reste hors de portee
# (cf. incident phantom mount 2026-08-06).
set -euo pipefail

KV="${1:-turboquant_k8v4}"
IMAGE="${IMAGE:-vllm/vllm-openai:nightly-b22afe45ac797ae58e67a7a3ad79ee5714024420}"
MODEL="${MODEL:-cyankiwi/Qwen3.5-9B-AWQ-4bit}"
NAME="phase1-stock-tq"
PORT=5003
CACHE="/d/vllm/_phase1_cache/hf"

# garde-fou : ne jamais demarrer si GPU 2 n'est pas a sa baseline (job CoursIA en cours)
USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 2)
if [ "$USED" -gt 500 ]; then
  echo "STOP: GPU 2 occupee (${USED} MiB) -- un entrainement CoursIA tourne. Abandon."
  exit 3
fi
echo "GPU 2 libre (${USED} MiB), demarrage avec --kv-cache-dtype ${KV}"

mkdir -p "$CACHE"
docker rm -f "$NAME" >/dev/null 2>&1 || true

# token HF depuis le .env de la prod (jamais affiche)
HF_TOKEN=$(grep -E '^HUGGING_FACE_HUB_TOKEN=' /d/vllm/myia_vllm/.env | cut -d= -f2- | tr -d '\r"')

MSYS_NO_PATHCONV=1 docker run -d --name "$NAME" \
  --gpus '"device=2"' \
  --ipc=host \
  -p ${PORT}:8000 \
  -v "$(cygpath -w "$CACHE" 2>/dev/null || echo "$CACHE")":/root/.cache/huggingface \
  -e HUGGING_FACE_HUB_TOKEN="$HF_TOKEN" \
  "$IMAGE" \
  --model "$MODEL" \
  --served-model-name qwen35-9b \
  --tensor-parallel-size 1 \
  --kv-cache-dtype "$KV" \
  --max-model-len 40960 \
  --max-num-batched-tokens 4096 \
  --gpu-memory-utilization 0.85 \
  --dtype auto \
  --skip-mm-profiling \
  --enable-prefix-caching \
  --trust-remote-code

echo "conteneur ${NAME} lance -> port ${PORT}"
echo "  docker logs -f ${NAME}"
echo "  python probe.py --port ${PORT}"
