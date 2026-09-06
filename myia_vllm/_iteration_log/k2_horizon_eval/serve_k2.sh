#!/bin/bash
# Boot the home-quantized K2-Horizon W4A16 on GPU 2 for validation + tests.
# CoursIA slot window; STRICT GPU 2 pinning — never GPUs 0,1 (prod).
# Run from Git Bash in d:/vllm:  MSYS_NO_PATHCONV=1 bash myia_vllm/_iteration_log/k2_horizon_eval/serve_k2.sh
set -e
docker rm -f k2-eval 2>/dev/null || true
MSYS_NO_PATHCONV=1 docker run -d --name k2-eval \
  --gpus '"device=2"' \
  -p 127.0.0.1:5022:5022 \
  -v '\\wsl.localhost\Ubuntu\home\jesse\k2-quant-out:/m:ro' \
  vllm/vllm-openai:nightly-e962733e08d10f7ca65dac4df99e116460b8b174 \
  --model /m --served-model-name k2-horizon-36b \
  --max-model-len 8192 --gpu-memory-utilization 0.90 \
  --max-num-seqs 16 \
  --trust-remote-code \
  --reasoning-parser k2_horizon --tool-call-parser k2_horizon \
  --port 5022
echo "k2-eval started. Cold boot ~5-10 min (torch.compile, ephemeral cache)."
echo "watch: docker logs -f k2-eval   (wait for: Application startup complete)"
