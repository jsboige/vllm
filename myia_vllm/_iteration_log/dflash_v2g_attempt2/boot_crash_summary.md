# DFlash-v2g cold boot attempt 2 — CRASH (torch.compile fake tensor mismatch)

**Date**: 2026-05-17 ~19:31Z
**Profile**: `medium-qwen36-genesis-tq-dflash.yml` (after Attempt 1 retry plan applied)
**Image**: `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3`
**Container outcome**: restart loop until manual rollback to v2g at 19:34Z.

## Diff vs Attempt 1

Applied "Attempt 2" retry plan from [../dflash_v2g_attempt1/boot_crash_summary.md](../dflash_v2g_attempt1/boot_crash_summary.md):
1. **Dropped** `--default-chat-template-kwargs '{"preserve_thinking":true}'` (hypothesis: poisons processor `init_kwargs` with a code object → deepcopy fails on spec-dec second processor load).
2. `num_speculative_tokens` 15 → **7**.
3. `--max-num-batched-tokens` 4096 → **8192** (to accommodate K+1 verify under the K=7 budget).
4. Enabled DFlash opt-in patches: `GENESIS_ENABLE_PN21_DFLASH_SWA=1`, `GENESIS_ENABLE_PN23_DFLASH_DTYPE_FIX=1`, `GENESIS_ENABLE_PN24_DFLASH_AUX_LAYER_FIX=1`.

## What got further than Attempt 1

Boot progressed past the tokenizer deepcopy/segfault (the Attempt 1 failure mode):
- All Genesis patches applied: PN21/PN23/PN24 confirmed in patch log.
- PN9 self-retired (upstream #39930 already merged in base nightly `01d4d1ad3`).
- TurboQuant kernels built clean: P67 (multi-query for K+1), P67b (spec-verify forward routing), P78 (tolist capture-guard), P101 (continuation 64-token slicing).
- DFlash drafter `z-lab/Qwen3.6-35B-A3B-DFlash` loaded (11.84 GiB) in 42 s.
- Aux layer indexing confirmed `(2, 11, 20, 29, 38)` — PN24 fix active (was `(1, 10, 19, 28, 37)` pre-patch).

## What crashed

`determine_available_memory` → `profile_run` → `_dummy_run` → model forward → torch.compile dynamo tracing:

```
torch._dynamo.exc.TorchRuntimeError: RuntimeError when making fake tensor call
Explanation: Dynamo failed to run FX node with fake tensors: call_function <built-in function mul>(
  *(FakeTensor(..., device='cuda:0', size=(65536, 128)),
    FakeTensor(..., device='cuda:0', size=(16*s59, 128))),
  **{}):
got RuntimeError('The size of tensor a (65536) must match the size of tensor b (16*s59)
                  at non-singleton dimension 0')
```

Symbolic shape `16*s59` ≠ static `65536` at non-singleton dimension 0.

## Hypothesis

`65536 = 8192 (max-num-batched-tokens) × 8 (some K-related factor, possibly K+1=8 or num_attention_heads-derived)`.

The torch.compile FX graph was specialized on a static shape from the K=7 + max-num-batched-tokens=8192 combination, but a downstream op produced a symbolic shape `16*s59` that doesn't match. This is consistent with the **spec-dec K+1 verify pattern** producing intermediate tensors whose first dim is `batch * (K+1)` (here `K+1 = 8`), and a downstream Triton kernel expecting the dynamic version.

Note: vLLM warning earlier said K=15 + max-num-batched=4096 → 3928 scheduled. Bumping to K=7 + max-num-batched=8192 created a budget the model wasn't compiled for.

## Retry plan (Attempt 3)

Cheapest first:
1. **Revert `max-num-batched-tokens` to 4096**, keep K=7. K=7 → 4096 - 7*16seq = 3984 scheduled (vLLM still happy).
2. If still crashes: **K=4** (vLLM DFlash default), max-num-batched=4096.
3. If still crashes: drop torch.compile via `--enforce-eager`. Will be slow but isolates whether the bug is in the compiled graph specialization or in the eager DFlash forward path itself.
4. If even eager crashes: pivot to **FP8 + MTP** (download complete at 19:33Z, model `Qwen/Qwen3.6-35B-A3B-FP8` preserves built-in MTP heads — no AWQ stripping issue).

## Rollback at 19:34Z

Rolled back to v2g (`medium-qwen36-genesis-tq.yml`). KV cache 2,045,242 tokens, max concurrency 7.80×, healthcheck HTTP 200 at 19:38Z. Production restored.

FP8 download finished in parallel during the crash investigation (`Qwen/Qwen3.6-35B-A3B-FP8`, 56 files, 7m37s).
