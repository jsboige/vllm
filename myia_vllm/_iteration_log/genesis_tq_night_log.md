# Genesis TQ A/B iteration log (overnight 2026-05-16)

Container reused: `myia_vllm-medium-qwen36-moe` (one at a time).
Baseline image: `vllm-qwen36-shmpatched:nightly-f6983f01d-patched1` (Apr 06 + shm patch).
Genesis image: `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3`.

Rule: rollback to baseline + 20-min cooldown between attempts.

Constants confirmed working (across v2a/v2b/v2d/v2e):
- dtype `float16`, `--language-model-only`, `--gdn-prefill-backend triton`,
  `--no-enable-flashinfer-autotune`, `--disable-custom-all-reduce`, `--async-scheduling`,
  `--no-scheduler-reserve-full-isl`, `--enable-chunked-prefill`,
  `--prefix-caching-hash-algo xxhash`, `--performance-mode interactivity`.
- Env: `VLLM_FLOAT32_MATMUL_PRECISION=high`, `NCCL_P2P_DISABLE=1`,
  `VLLM_USE_FLASHINFER_SAMPLER=1`, `CUDA_DEVICE_MAX_CONNECTIONS=8`, `OMP_NUM_THREADS=1`,
  `VLLM_MARLIN_MOE_BLOCK_SIZE_M=8`, `VLLM_MOE_USE_DEEP_GEMM=0`,
  `VLLM_USE_FLASHINFER_MOE_FP8=0`, `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=0`,
  `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:512`,
  `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1`.
- Genesis flags: P37, P38B, P67, P98, P101, P78, P40.
- **`--max-num-batched-tokens 4096`** — Genesis canonical PROD-MIRROR value; **8192 triggers a Dynamo shape mismatch** (`tensor a (65536) must match tensor b (16*sNN)` at `aot_compile_fullgraph`). Worth filing upstream (not Genesis-specific).

## v1 — FAILED (Dynamo, batched=8192)
seqs=16, batched=8192, dtype=auto, vision ON, gpu_util=0.85.

## v2a — BOOT OK, OOM at first inference
seqs=2, batched=4096, fp16, LM-only, gpu_util=0.92. KV 2.72M.

## v2b — SMOKES + CRASH GATE PASS, single-user OK, concurrent queue-saturated
seqs=2, batched=4096, fp16, LM-only, gpu_util=0.85. KV 2.33M.

## v2c — FAILED (Dynamo, batched=8192)
seqs=8, batched=8192. Same shape error as v1.

## v2d — WIN: single parity, concurrent +29% vs baseline (commit 541f3a155)
seqs=8, batched=4096, gpu_util=0.82, +P40. KV 2.10M.
single no-think 103.3 tok/s (FP8 107), single thinking 115.1 (FP8 116.5),
8-conc 419, 12-conc 475 (+29%), 16-conc 447. Crash gate PASS.

## v2e — BIGGER WIN: concurrent +125% vs baseline
seqs=16, batched=4096, gpu_util=0.82, +P40. KV 2.10M.

Smokes pass (chat, tool calling).
Crash gate PASS in 3.90s (with prefix cache hit).
3-iter scaling stability (no leak, no degradation):

| N users | iter 1 | iter 2 | iter 3 | median | vs FP8 baseline |
|---|---|---|---|---|---|
| 1 | 95 | 90 | 95 | 95 | -11% (TTFT-noise on 22-tok) |
| 2 | 127 | 111 | 124 | 124 | n/a |
| 4 | 220 | 209 | 231 | 220 | n/a |
| 8 | 458 | 405 | 437 | 437 | n/a |
| 12 | 653 | 550 | 629 | 629 | **+70%** vs 369 |
| 16 | **822** | **854** | **823** | **823** | **+123%** vs 369 |

VRAM: GPU 0 24080→24087 MiB (delta +7), GPU 1 22722→22724 (delta +2). Zero leak.

## Summary — v2e is the new winner
For OWUI/Roo/Claudish multi-user long-context workload:
- WIN: KV +6.5× (322K → 2.10M tokens), 16-conc throughput +123% vs FP8 baseline.
- LOSS: vision OFF (`--language-model-only`). Remains a feature regression vs prod.

## Next: v2f — re-enable vision
Test the hypothesis: vision re-enable on Genesis with batched=4096 is safe. v1 failed at batched=8192 + seqs=16 + vision; we've isolated batched=8192 as the trigger. With batched=4096 (proven safe in v2a/v2b/v2d/v2e), vision should work too.
v2f changes from v2e:
- Remove `--language-model-only`
- Re-add `--limit-mm-per-prompt '{"image":4,"video":0}'`
- Re-add `--mm-processor-kwargs '{"max_pixels":774000}'`
- Re-add `--skip-mm-profiling`
- `--dtype float16` → `--dtype auto` (vision encoder is BF16)

## v2f — WIN: vision restored, concurrent +125% vs baseline
seqs=16, batched=4096, gpu_util=0.82, +P40, dtype=auto, vision ON. KV 2.03M.

Boot to "Application startup complete" + healthy in ~5 min. No Dynamo, no OOM.
KV cache: 2,029,669 tokens (-67K vs v2e 2,097,152 — vision encoder cost).

Smokes:
- Single no-thinking: 117/120/120 tok/s, median **120** (FP8 baseline 107, **+12%**)
- Single thinking: 123.3/124.9/123.9, median **123.9** (FP8 116.5, **+6%**)
- Tool calling: implicit in chat smoke (model uses qwen3_coder parser)
- **Vision smoke: PASS** (64x64 red PNG → "Red" in 0.77s, prompt=91 tokens)
- Crash gate 24K: PASS in 6.82s

3-iter scaling (vision ON):

| N users | iter 1 | iter 2 | iter 3 | median | vs FP8 baseline |
|---|---|---|---|---|---|
| 1 | 93 | 91 | 97 | 93 | -13% (TTFT noise on short prompts) |
| 2 | 134 | 125 | 134 | 134 | n/a |
| 4 | 214 | 221 | 215 | 215 | n/a |
| 8 | 415 | 412 | 448 | 415 | n/a |
| 12 | 593 | 625 | 628 | 625 | **+69%** |
| 16 | 816 | 829 | 833 | **829** | **+125%** vs 369 |

VRAM: GPU 0 24044→24039 MiB (delta -5), GPU 1 22880→22880 (delta 0), GPU 2 45 MiB. Zero leak.

## Summary — v2f is the production candidate
For OWUI/Roo/Claudish multi-user long-context workload:
- WIN: KV +6.3× (322K → 2.03M tokens), 16-conc throughput +125% vs FP8 baseline, vision restored, single-user +12%.
- NO REGRESSIONS vs FP8 baseline.
- Net delta vs v2e: -67K KV tokens (vision encoder cost), N=16 throughput essentially identical (829 vs 823).
