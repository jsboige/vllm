#!/bin/bash
# Boot DaisyRose-27B-W4A16-HGPTQ on GPU 2 ONLY, for a quality-only bench against Swift.
# Needs a CoursIA GPU 2 slot (GPU 2 is theirs). Never GPUs 0,1 (prod :5002 untouched).
#
# Why these flags (see NOTES.md):
# - TP=1 on one 4090: 16.14 GiB of weights + the 2.02 GiB WSL2/DXG tax leave about
#   0.2 GiB of KV with CUDA graphs, about 3.3 GiB without -> --enforce-eager, 32K context.
#   Throughput measured here is worthless (eager costs 3-4x); this run answers QUALITY only.
# - --trust-remote-code loads the repo's vllm_warp_quant.py through config.json auto_map.
#   Stock v0.34.0 cannot load this checkpoint: transform/linear.py:161 asserts bias is None
#   and transform/module.py:47 refuses TP>1. The plugin hot-patches vLLM in every process;
#   it was read at revision 9aef1a7d, not executed before this bench.
# - Sampling/template flags mirror prod Swift (reasoning_effort medium, preserve_thinking,
#   same override-generation-config, nvfp4 KV, fp16 mamba state) so the pairs compare models.
# - No MTP (TP=1 VRAM), no images (quality_27b.py is text: GSM8K + IFEval).
# - VLLM_WSL2_ENABLE_PIN_MEMORY=1 is safe here: no KV offload region to register (the
#   falsified pin=1 crash is cudaHostRegister of the offload region; v0.34 V2 runner needs UVA).
# ISOLATION (measured 2026-10-30): under WSL2 `--gpus device=2` does NOT isolate; the
# container sees all 3 GPUs and CUDA index 0 is PROD GPU 0. CUDA_DEVICE_ORDER=PCI_BUS_ID +
# CUDA_VISIBLE_DEVICES=2 pin pci 72:00.0.
# Weights live on C: (the WSL disk holds the prod fs tier): mounted read-only below.
#
# Run from Git Bash in d:/vllm:
#   MSYS_NO_PATHCONV=1 bash myia_vllm/_iteration_log/daisyrose_eval/serve_daisyrose.sh
# Then check isolation and the mount BEFORE trusting anything:
#   MSYS_NO_PATHCONV=1 docker exec daisyrose-eval du -sb /models/daisyrose   # 17.3 GB expected
#   nvidia-smi --query-gpu=index,memory.used --format=csv,noheader          # only GPU 2 grows
set -e
docker rm -f daisyrose-eval 2>/dev/null || true
sleep 10  # let a killed engine's CUDA context release VRAM before the free-memory check
MSYS_NO_PATHCONV=1 docker run -d --name daisyrose-eval \
  --gpus '"device=2"' \
  -p 127.0.0.1:5022:5022 \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e CUDA_VISIBLE_DEVICES=2 \
  -e HF_HUB_OFFLINE=1 \
  -e VLLM_WSL2_ENABLE_PIN_MEMORY=1 \
  -e VLLM_USE_FLASHINFER_SAMPLER=0 \
  -v 'C:\vllm_models\DaisyRose-27B-W4A16-HGPTQ:/models/daisyrose:ro' \
  vllm-openai-v0340-tierpin:v1 \
  --model /models/daisyrose \
  --served-model-name daisyrose-27b \
  --trust-remote-code \
  --enforce-eager \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --max-num-seqs 8 \
  --max-num-batched-tokens 8192 \
  --kv-cache-dtype nvfp4 \
  --dtype auto \
  --limit-mm-per-prompt '{"image":0,"video":0}' \
  --skip-mm-profiling \
  --enable-prefix-caching \
  --prefix-caching-hash-algo sha256 \
  --mamba-ssm-cache-dtype float16 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"preserve_thinking":true,"reasoning_effort":"medium"}' \
  --override-generation-config '{"temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.0,"repetition_penalty":1.0}' \
  --no-enable-flashinfer-autotune \
  --port 5022
echo "daisyrose-eval started. Watch: docker logs -f daisyrose-eval (wait: Application startup complete)"
echo "Quality, same window, paired (from d:/vllm):"
echo "  python myia_vllm/_iteration_log/qwen38_27b_gpu2/quality_27b.py --model daisyrose-27b \\"
echo "    --output-dir myia_vllm/_iteration_log/daisyrose_eval/results/daisyrose"
echo "  VLLM_API_KEY_MEDIUM=<from .env> python myia_vllm/_iteration_log/qwen38_27b_gpu2/quality_27b.py \\"
echo "    --model swift-1.5-27b --base-url http://localhost:5002/v1 --workers 4 \\"
echo "    --output-dir myia_vllm/_iteration_log/daisyrose_eval/results/swift-ref"
echo "  then paired_27b.py --new <daisyrose jsonl> --ref <swift jsonl> --label DaisyRose"
