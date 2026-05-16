# Genesis TQ A/B iteration log (overnight 2026-05-16)

Container reused: `myia_vllm-medium-qwen36-moe` (one at a time).
Baseline image: `vllm-qwen36-shmpatched:nightly-f6983f01d-patched1` (Apr 06 + shm patch).
Genesis image: `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3` (already built local).

Rule: rollback to baseline + 20-min cooldown between attempts.

Constants confirmed working:
- `--dtype float16` (not auto)
- `--language-model-only` (no vision yet — separate ramp later)
- `--gdn-prefill-backend triton`, `--no-enable-flashinfer-autotune`, `--disable-custom-all-reduce`, `--async-scheduling`, `--no-scheduler-reserve-full-isl`, `--enable-chunked-prefill`, `--prefix-caching-hash-algo xxhash`
- Env: `VLLM_FLOAT32_MATMUL_PRECISION=high`, `NCCL_P2P_DISABLE=1`, `VLLM_USE_FLASHINFER_SAMPLER=1`, `CUDA_DEVICE_MAX_CONNECTIONS=8`, `OMP_NUM_THREADS=1`, `VLLM_MARLIN_MOE_BLOCK_SIZE_M=8`, `VLLM_MOE_USE_DEEP_GEMM=0`, `VLLM_USE_FLASHINFER_MOE_FP8=0`, `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=0`, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:512`, `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1`
- Genesis flags: P37, P38B, P67, P98, P101, P78, +P40 (added v2d from RTX-4090 dispatcher reco)

## v1 — FAILED (Dynamo shape mismatch)
seqs=16, batched=8192, dtype=auto, vision ON, gpu_util=0.85.
`tensor a (65536) must match tensor b (16*s59)` at aot_compile_fullgraph.

## v2a — BOOT OK, OOM at first inference
seqs=2, batched=4096, dtype=float16, +LM-only, gpu_util=0.92, +perf-mode interactivity.
KV: 2,720,068 tokens. Smokes 1+2 pass. Smoke 3 OOM at FLA `chunk_gated_delta_rule_fwd_h`. 0.92 too high for 4090 24GB FLA transients.

## v2b — SMOKES + CRASH GATE PASS, perf regression
seqs=2, batched=4096, gpu_util=0.85.
KV: 2,333,341 (+7.24× FP8). All smokes pass. **🎯 30K-prefix crash gate PASS** (Genesis P22+P38 confirmed fix the 2026-05-06 failure mode).
Bench shows -29% single, -58% concurrent (concurrent regression is `seqs=2` queue saturation).

## v2c — FAILED (Dynamo shape mismatch — SAME AS v1)
seqs=8, batched=8192, gpu_util=0.82.
SAME error as v1: `tensor a (65536) must match tensor b (16*s72)`.
**Learning**: the "16" in the error is NOT max-num-seqs — it's a kernel tiling constant.
**`batched=8192` is the trigger** (v1 had it, v2c has it). v2a/v2b with batched=4096 worked.
65536 = 8192 × 8 = `max-num-batched-tokens × head_dim_per_tile` (likely).

## v2d — planned 2026-05-16 ~02:50 UTC
seqs=8, **batched=4096** (revert to known-working), gpu_util=0.82, +`GENESIS_ENABLE_P40=1` (Genesis dispatcher recommended for RTX 4090 SM 128 L2 72MB mixed-regime, +5-15% on TQ k8v4 from vllm#40792).
Goal: validate seqs ramp 2→8 (concurrent throughput) WITHOUT triggering the batched=8192 Dynamo bug.
If seqs=8 boots + benches better → v2e tries seqs=16 (still batched=4096).

## Open question — the batched=8192 Dynamo bug
This is upstream, not Genesis-specific. The Dynamo trace cannot unify a fixed 65536-element tensor with a `16*s72` symbolic-dim tensor when batched-tokens grows. Worth filing upstream; for now we work around by keeping batched=4096 (Genesis canonical PROD-MIRROR value).
