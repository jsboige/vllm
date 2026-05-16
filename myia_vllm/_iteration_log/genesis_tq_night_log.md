# Genesis TQ A/B iteration log (overnight 2026-05-16)

Container reused: `myia_vllm-medium-qwen36-moe` (one at a time).
Baseline image: `vllm-qwen36-shmpatched:nightly-f6983f01d-patched1` (Apr 06 + shm patch).
Genesis image: `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3` (already built local).

Rule between attempts: rollback to baseline + wait 20 min (dashboards condense + GPU/cache settle) before next try.

## v1 — 2026-05-16 ~00:50 UTC — FAILED
Commit profile state: `43eaae62f` (genesis-tq Dockerfile + profile committed).
Settings: dtype auto, vision ON, max_num_batched_tokens=8192, max_num_seqs=16, gpu_util=0.85, OMP=4.
Failure: `RuntimeError ... <built-in function mul>(*(FakeTensor(size=(65536, 128)), FakeTensor(size=(16*s59, 128))) ... tensor a (65536) must match tensor b (16*s59)` during `profile_run → _dummy_run → qwen3_5.py:695 forward → aot_compile`. Worker exited, container ping-ponged. Rolled back instant.
Hypothesis: `16` in `16*s59` = `--max-num-seqs 16`. Dynamic-shape trace fails at the larger graph + vision encoder mixed BF16/fp16.

## v2a — Genesis canonical 1:1 (no vision)
Changes from v1:
- `--dtype auto` → `--dtype float16`
- Add `--language-model-only` (disables vision encoder)
- `--max-num-batched-tokens 8192` → `4096`
- `--max-num-seqs 16` → `2`
- `--gpu-memory-utilization 0.85` → `0.92`
- Add `--performance-mode interactivity`
- Remove `--limit-mm-per-prompt`, `--mm-processor-kwargs`, `--skip-mm-profiling` (no MM in LM-only)
- Env `OMP_NUM_THREADS=4` → `1`
- Add env: `VLLM_FLOAT32_MATMUL_PRECISION=high`, `NCCL_P2P_DISABLE=1`, `VLLM_USE_FLASHINFER_SAMPLER=1`, `CUDA_DEVICE_MAX_CONNECTIONS=8`, `VLLM_MARLIN_MOE_BLOCK_SIZE_M=8`, `VLLM_MOE_USE_DEEP_GEMM=0`, `VLLM_USE_FLASHINFER_MOE_FP8=0`

