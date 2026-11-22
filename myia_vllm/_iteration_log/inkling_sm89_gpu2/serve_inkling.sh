#!/bin/bash
# Boot Inkling 2 Mini (thinkingmachines/Inkling-2-Mini @ b85c3cfa, original NVFP4/MXFP8 checkpoint)
# on GPU 2 ONLY, TP=1, for an SM89 feasibility test. Needs a CoursIA GPU 2 slot (GPU 2 is theirs).
# Never GPUs 0,1 (prod :5002 untouched).
#
# Image: inkling-sm89-test:v1 = nightly 647a76866b + upstream PR vllm#69165 (SM80/86/89 path)
# + one env-gated line opening fp8 KV on sm_89 (overlay source in .tmp/inkling/overlay/, record
# in NOTES.md). The PR says itself: "SM89 takes native e4m3 without PDL, a combination that
# nothing above executed or compiled" -> this run is that first execution.
#
# Modes (env):
#   KV=bf16 (default) | fp8   fp8 sets MYIA_INKLING_FP8_KV_SM89=1 + --kv-cache-dtype fp8
#   MAXLEN=4096               one 4090 at TP=1: 17.64 GiB of weights (peaster, text only, no
#                             drafter) + the 2.02 GiB WSL2/DXG tax leave ~4 GiB for activations,
#                             graphs and KV; peaster's 3090 at 0.95 got an 8,639-token pool.
#   EAGER=0 | 1               1 = --enforce-eager if CUDA graphs leave no KV (throughput then void)
#   EXTKV=1 | 0               0 = --no-enable-extensible-kv-cache (KV sized at profiling, as prod
#                             runs since 19/11 with --disable-extensible-kv-cache on v0.34.0).
#                             Window 22/11, runs 2-3: the extensible cache kept 1.88 GiB "for
#                             transient activations" after warmup and left 1.5-1.59 GiB of KV out
#                             of the 3.64 GiB profiled; eager mode won back only 0.09 GiB.
# Text only (--limit-mm-per-prompt image 0), no drafter (no --speculative-config): the two levers
# peaster measured as the largest KV pools. max-num-batched-tokens 1024: the sliding-window
# reservation (40 caches) scales with it (peaster: 8192 does not boot at 196K).
#
# ISOLATION (measured 2026-10-30): under WSL2 `--gpus device=2` NO LONGER isolates; the
# CUDA_DEVICE_ORDER=PCI_BUS_ID + CUDA_VISIBLE_DEVICES=2 pair below is what pins pci 72:00.0.
# Run from Git Bash in the repo root (main or a worktree):  MSYS_NO_PATHCONV=1 KV=bf16 bash myia_vllm/_iteration_log/inkling_sm89_gpu2/serve_inkling.sh
set -e
KV=${KV:-bf16}
MAXLEN=${MAXLEN:-4096}
EAGER=${EAGER:-0}
EXTKV=${EXTKV:-1}
NAME=inkling-eval
EXTRA_ENV=()
EXTRA_ARGS=()
if [ "$KV" = "fp8" ]; then
  EXTRA_ENV+=(-e MYIA_INKLING_FP8_KV_SM89=1)
  EXTRA_ARGS+=(--kv-cache-dtype fp8)
fi
[ "$EAGER" = "1" ] && EXTRA_ARGS+=(--enforce-eager)
[ "$EXTKV" = "0" ] && EXTRA_ARGS+=(--no-enable-extensible-kv-cache)
docker rm -f "$NAME" 2>/dev/null || true
sleep 10  # let a killed engine's CUDA context release VRAM before the free-memory check
MSYS_NO_PATHCONV=1 docker run -d --name "$NAME" \
  --gpus '"device=2"' \
  --label autoheal=False \
  -p 127.0.0.1:5022:5022 \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e CUDA_VISIBLE_DEVICES=2 \
  -e HF_HUB_OFFLINE=1 \
  -e NCCL_CUMEM_ENABLE=0 \
  -e VLLM_USE_FLASHINFER_SAMPLER=0 \
  "${EXTRA_ENV[@]}" \
  -v 'C:/vllm_models/Inkling-2-Mini:/models/inkling:ro' \
  -v vllm-cache-inkling-sm89-test:/root/.cache \
  inkling-sm89-test:v1 \
  --model /models/inkling \
  --served-model-name inkling-2-mini \
  --tensor-parallel-size 1 \
  --max-model-len "$MAXLEN" \
  --max-num-batched-tokens 1024 \
  --max-num-seqs 2 \
  --gpu-memory-utilization 0.90 \
  --limit-mm-per-prompt '{"image":0}' \
  --reasoning-parser inkling \
  --no-enable-flashinfer-autotune \
  --port 5022 \
  "${EXTRA_ARGS[@]}"
echo "$NAME started (KV=$KV MAXLEN=$MAXLEN EAGER=$EAGER EXTKV=$EXTKV). Cold boot = Triton/Humming JIT, minutes."
